# Standard Library
import os
import shutil
from pathlib import Path
from typing import Tuple

# Third Party
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_aws import BedrockEmbeddings
from langchain_community.vectorstores import FAISS

# Initialize logger
logger = Logger(service="pdf_ingestor_processor_bedrock")

# Initialize Bedrock runtime client
try:
    s3_client = boto3.client("s3")
    bedrock_runtime_client = boto3.client(service_name="bedrock-runtime")
except Exception as e:
    logger.exception(
        f"Failed to initialize Boto3 clients in processor module: {e}"
    )
    s3_client = None
    bedrock_runtime_client = None

# Get the Bedrock embedding model ID from environment variables or use a default
BEDROCK_EMBEDDING_MODEL_ID = os.environ.get(
    "BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0"
)

# Initialize the BedrockEmbeddings model
try:
    logger.info(
        f"Initializing BedrockEmbeddings model: {BEDROCK_EMBEDDING_MODEL_ID}"
    )
    embedding_model = BedrockEmbeddings(
        client=bedrock_runtime_client, model_id=BEDROCK_EMBEDDING_MODEL_ID
    )
    logger.info("BedrockEmbeddings model initialized.")
except Exception as e:
    logger.exception(f"Failed to initialize BedrockEmbeddings model: {e}")
    embedding_model = None

# Get the S3 bucket name for storing the FAISS index
VECTOR_STORE_BUCKET_NAME = os.environ.get("VECTOR_STORE_BUCKET_NAME")


def extract_srd_info(object_key: str) -> Tuple[str, str]:
    """Extract the SRD ID and filename from the S3 object key.

    The S3 object key is expected to be in the format:
    `<srd_id>/<filename>`, where `<srd_id>` is the SRD ID and
    `<filename>` is the name of the file.

    Parameters
    ----------
    object_key : str
        The S3 object key to extract the SRD ID and filename from.

    Returns
    -------
    Tuple[str, str]
        A tuple containing the SRD ID and the filename.
        If the object key does not contain a slash, the filename is returned
        as the second element, and the SRD ID is set to an empty string.
    """
    # Split the object key into parts to extract SRD ID and filename
    parts = object_key.split("/", 1)

    # No SRD ID in path, use the filename as both SRD ID and filename
    if len(parts) < 2:
        return Path(object_key).stem, object_key

    return parts[0], parts[1]


def process_s3_object(
    bucket_name: str, object_key: str, lambda_logger: Logger
) -> None:
    """Process a PDF file from S3, generate embeddings using Bedrock,
    and create a FAISS index. The FAISS index is then uploaded back to S3.

    Parameters
    ----------
    bucket_name : str
        The name of the S3 bucket containing the PDF file.
    object_key : str
        The key of the PDF file in the S3 bucket.
    lambda_logger : Logger
        The logger instance for logging messages.

    Raises
    -------
    RuntimeError
        If the S3 client, Bedrock client, or embedding model is not initialized.
    EnvironmentError
        If the VECTOR_STORE_BUCKET_NAME environment variable is not set.
    ClientError
        If there is an error interacting with AWS services.
    Exception
        For any other unexpected errors during processing.
    """
    # Extract SRD ID form object key
    srd_id, filename = extract_srd_info(object_key=object_key)

    # Validate the bucket name and object key
    base_file_name = os.path.basename(filename)
    safe_base_file_name = "".join(
        c if c.isalnum() or c in [".", "-"] else "_" for c in base_file_name
    )
    temp_pdf_path = f"/tmp/{safe_base_file_name}"
    temp_faiss_index_name = f"{srd_id}_faiss_index"
    temp_faiss_index_path = f"/tmp/{temp_faiss_index_name}"

    try:
        # Download the PDF file from S3
        lambda_logger.info(
            f"Downloading s3://{bucket_name}/{object_key} to {temp_pdf_path}"
        )
        s3_client.download_file(bucket_name, object_key, temp_pdf_path)
        lambda_logger.info(f"Successfully downloaded PDF to {temp_pdf_path}")

        # Load the PDF document using PyPDFLoader
        lambda_logger.info(
            f"Loading PDF document from {temp_pdf_path} using PyPDFLoader."
        )
        loader = PyPDFLoader(temp_pdf_path)
        documents = loader.load()
        lambda_logger.info(
            f"Loaded {len(documents)} document pages/sections from PDF."
        )
        if not documents:
            lambda_logger.warning(
                f"No documents loaded from PDF: {object_key}."
            )
            return

        # Split the document into manageable text chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )
        texts = text_splitter.split_documents(documents)
        lambda_logger.info(f"Split into {len(texts)} text chunks.")
        if not texts:
            lambda_logger.warning(f"No text chunks generated: {object_key}.")
            return

        # Generate embeddings for the text chunks using Bedrock
        lambda_logger.info(
            "Generating embeddings with Bedrock and creating FAISS index..."
        )
        vector_store = FAISS.from_documents(texts, embedding_model)
        lambda_logger.info("FAISS index created successfully in memory.")

        # Save the FAISS index to a temporary directory
        if os.path.exists(temp_faiss_index_path):
            shutil.rmtree(temp_faiss_index_path)
        os.makedirs(temp_faiss_index_path, exist_ok=True)
        vector_store.save_local(folder_path=temp_faiss_index_path)
        lambda_logger.info(
            f"FAISS index saved locally to directory: {temp_faiss_index_path}"
        )

        # Upload the FAISS index files to S3
        s3_index_prefix = f"{srd_id}/faiss_index"
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
            f"FAISS index for {object_key} uploaded to S3: {VECTOR_STORE_BUCKET_NAME}/{s3_index_prefix}"
        )

    # Handle specific AWS errors and log them
    except ClientError as e:
        lambda_logger.exception(
            f"AWS ClientError during processing of {object_key}: {e}"
        )
        raise
    except Exception as e:
        lambda_logger.exception(
            f"Unexpected error during processing of {object_key}: {e}"
        )
        raise
    finally:
        # Clean up temporary files and directories
        if os.path.exists(temp_pdf_path):
            try:
                os.remove(temp_pdf_path)
            except Exception as e_clean:
                lambda_logger.error(
                    f"Error cleaning temp PDF {temp_pdf_path}: {e_clean}"
                )
        # Clean up the FAISS index directory
        if os.path.exists(temp_faiss_index_path):
            try:
                shutil.rmtree(temp_faiss_index_path)
            except Exception as e_clean:
                lambda_logger.error(
                    f"Error cleaning temp FAISS dir {temp_faiss_index_path}: {e_clean}"
                )

    # Save metadata about the processed document
    metadata = {
        "srd_id": srd_id,
        "original_filename": filename,
        "chunk_count": len(texts),
        "source_bucket": bucket_name,
        "source_key": object_key,
        "vector_index_location": f"{s3_index_prefix}/",
    }

    return metadata
