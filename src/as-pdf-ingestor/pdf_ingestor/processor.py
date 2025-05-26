# Standard Library
import os
import shutil

# Third-Party
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger

# Langchain components
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

# Initialize clients and models
logger = Logger(service="pdf_ingestor_processor")

# Initialize Boto3 S3 client globally
try:
    s3_client = boto3.client("s3")
except Exception as e:
    logger.exception(
        f"Failed to initialize Boto3 S3 client in processor module: {e}"
    )
    raise e

try:
    # Using a relatively lightweight sentence transformer model.
    logger.info("Initializing HuggingFaceEmbeddings model...")
    embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    logger.info("HuggingFaceEmbeddings model initialized.")
except Exception as e:
    logger.exception(f"Failed to initialize HuggingFaceEmbeddings model: {e}")
    raise e

# Retrieve environment variables
VECTOR_STORE_BUCKET_NAME = os.environ.get("VECTOR_STORE_BUCKET_NAME")


def process_s3_object(
    bucket_name: str, object_key: str, lambda_logger: Logger
) -> None:
    """Processes a PDF file from S3: loads, chunks, embeds, and stores its
    vector representation.

    Parameters
    ----------
    bucket_name : str
        The name of the S3 bucket containing the PDF file.
    object_key : str
        The key of the PDF file in the S3 bucket.
    lambda_logger : Logger
        The logger instance for logging within the Lambda function.

    Raises
    -------
    RuntimeError
        If critical components (S3 client or embedding model) fail to initialize.
    EnvironmentError
        If the VECTOR_STORE_BUCKET_NAME environment variable is not set.
    ClientError
        If there is an error interacting with AWS services (e.g., S3).
    FileNotFoundError
        If the temporary PDF file cannot be found after download.
    Exception
        For any other unexpected errors during processing.
    """
    if not s3_client or not embedding_model:
        lambda_logger.error(
            "Processor dependencies (S3 client or embedding model) not initialized."
        )
        # This indicates a problem during the module's cold start.
        raise RuntimeError(
            "Critical components (S3 client or embedding model) failed to initialize."
        )

    if not VECTOR_STORE_BUCKET_NAME:
        lambda_logger.error(
            "VECTOR_STORE_BUCKET_NAME environment variable is not set."
        )
        raise EnvironmentError("VECTOR_STORE_BUCKET_NAME is not configured.")

    # Sanitize object_key to create a safe base for temp file names
    base_file_name = os.path.basename(object_key)
    safe_base_file_name = "".join(
        c if c.isalnum() or c in [".", "-"] else "_" for c in base_file_name
    )
    temp_pdf_path = f"/tmp/{safe_base_file_name}"

    # FAISS saves a directory, so we just need a base name for the directory in /tmp
    temp_faiss_index_name = (
        f"{os.path.splitext(safe_base_file_name)[0]}_faiss_index"
    )
    temp_faiss_index_path = f"/tmp/{temp_faiss_index_name}"

    try:
        # 1. Download PDF from source S3 to /tmp
        lambda_logger.info(
            f"Downloading s3://{bucket_name}/{object_key} to {temp_pdf_path}"
        )
        s3_client.download_file(bucket_name, object_key, temp_pdf_path)
        lambda_logger.info(f"Successfully downloaded PDF to {temp_pdf_path}")

        # 2. Load PDF with Langchain Document Loader
        lambda_logger.info(
            f"Loading PDF document from {temp_pdf_path} using PyPDFLoader."
        )
        loader = PyPDFLoader(temp_pdf_path)
        # Documents are loaded here. If PDF is password-protected or corrupted, this might fail.
        documents = loader.load()
        lambda_logger.info(
            f"Loaded {len(documents)} document pages/sections from PDF."
        )

        if not documents:
            lambda_logger.warning(
                f"No documents were loaded from PDF: {object_key}. Skipping further processing."
            )
            return

        # 3. Split documents into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )
        texts = text_splitter.split_documents(documents)
        lambda_logger.info(f"Split into {len(texts)} text chunks.")

        if not texts:
            lambda_logger.warning(
                f"No text chunks were generated after splitting: {object_key}. Skipping."
            )
            return

        # 4. Generate embeddings and create FAISS vector store
        lambda_logger.info(
            "Generating embeddings and creating FAISS index. This may take some time..."
        )
        vector_store = FAISS.from_documents(texts, embedding_model)
        lambda_logger.info("FAISS index created successfully in memory.")

        # 5. Save FAISS index locally to /tmp
        # FAISS.save_local saves two files (index.faiss, index.pkl) into the specified folder path.
        if os.path.exists(
            temp_faiss_index_path
        ):  # Clean up if it exists from a previous failed run within same container
            shutil.rmtree(temp_faiss_index_path)
        os.makedirs(
            temp_faiss_index_path, exist_ok=True
        )  # Ensure directory exists
        vector_store.save_local(folder_path=temp_faiss_index_path)
        lambda_logger.info(
            f"FAISS index saved locally to directory: {temp_faiss_index_path}"
        )

        # 6. Upload FAISS index (contents of the directory) to the vector_store_bucket
        # The S3 "key" for the index will be based on the original PDF's object key
        s3_index_prefix = f"{os.path.splitext(object_key)[0]}/faiss_index"  # Store in a "folder" named after the PDF

        for file_name_in_index_dir in os.listdir(temp_faiss_index_path):
            local_file_to_upload = os.path.join(
                temp_faiss_index_path, file_name_in_index_dir
            )
            s3_target_key = f"{s3_index_prefix}/{file_name_in_index_dir}"
            lambda_logger.info(
                f"Uploading {local_file_to_upload} to s3://{VECTOR_STORE_BUCKET_NAME}/{s3_target_key}"
            )
            s3_client.upload_file(
                local_file_to_upload, VECTOR_STORE_BUCKET_NAME, s3_target_key
            )
            lambda_logger.info(
                f"Successfully uploaded {file_name_in_index_dir}"
            )

        lambda_logger.info(
            f"FAISS index for {object_key} successfully uploaded to S3 bucket: "
            f"{VECTOR_STORE_BUCKET_NAME} under prefix: {s3_index_prefix}"
        )

    except ClientError as e:
        lambda_logger.exception(
            f"AWS ClientError during processing of {object_key}: {e}"
        )
        raise  # Re-raise to allow Lambda to handle retry or dead-letter queue based on its config
    except FileNotFoundError as e:  # e.g. if temp_pdf_path wasn't created
        lambda_logger.exception(
            f"FileNotFoundError during processing of {object_key}: {e}"
        )
        raise
    except Exception as e:
        lambda_logger.exception(
            f"Unexpected error during processing of {object_key}: {e}"
        )
        raise  # Re-raise for visibility and retries
    finally:
        # 7. Clean up /tmp
        if os.path.exists(temp_pdf_path):
            try:
                os.remove(temp_pdf_path)
                lambda_logger.info(
                    f"Cleaned up temporary PDF file: {temp_pdf_path}"
                )
            except Exception as e_clean_pdf:
                lambda_logger.error(
                    f"Error cleaning up PDF {temp_pdf_path}: {e_clean_pdf}"
                )
        if os.path.exists(temp_faiss_index_path):
            try:
                shutil.rmtree(
                    temp_faiss_index_path
                )  # Recursively remove directory
                lambda_logger.info(
                    f"Cleaned up temporary FAISS index directory: {temp_faiss_index_path}"
                )
            except Exception as e_clean_faiss:
                lambda_logger.error(
                    f"Error cleaning up FAISS index dir {temp_faiss_index_path}: {e_clean_faiss}"
                )
