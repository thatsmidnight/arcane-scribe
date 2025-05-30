# Standard Library
import os
import time
import json
import shutil
import hashlib
from typing import Optional, Dict, Any

# Third Party
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger
from langchain_aws import (
    BedrockEmbeddings,
    ChatBedrock,
)
from langchain_community.vectorstores import FAISS
from langchain.chains.retrieval_qa.base import RetrievalQA
from langchain.prompts import PromptTemplate

# Initialize logger
logger = Logger(service="rag_query_processor_bedrock")

# Initialize Boto3 clients for S3, DynamoDB (for caching), and Bedrock runtime
try:
    s3_client = boto3.client("s3")
    dynamodb_client = boto3.client("dynamodb")  # For caching
    # Initialize Bedrock runtime client. Region should be picked up from AWS_DEFAULT_REGION env var.
    bedrock_runtime_client = boto3.client(service_name="bedrock-runtime")
except Exception as e:
    logger.exception(
        f"Failed to initialize Boto3 clients in RAG processor: {e}"
    )
    s3_client = None
    dynamodb_client = None
    bedrock_runtime_client = None

# Get the Bedrock embedding and text generation model IDs from environment variables or use defaults
BEDROCK_EMBEDDING_MODEL_ID = os.environ.get(
    "BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0"
)
BEDROCK_TEXT_GENERATION_MODEL_ID = os.environ.get(
    "BEDROCK_TEXT_GENERATION_MODEL_ID", "amazon.titan-text-express-v1"
)

# Get the vector store bucket name and query cache table name from environment variables
VECTOR_STORE_BUCKET_NAME = os.environ.get("VECTOR_STORE_BUCKET_NAME")
QUERY_CACHE_TABLE_NAME = os.environ.get("QUERY_CACHE_TABLE_NAME")

# Default SRD ID for the System Reference Document (SRD) and cache settings
DEFAULT_SRD_ID = "dnd5e_srd"
CACHE_TTL_SECONDS = 3600  # Cache responses for 1 hour, adjust as needed

# Settings for the FAISS index cache
faiss_index_cache: dict[str, FAISS] = {}
MAX_CACHE_SIZE = 3

# Initialize the embedding model
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


# Initialize default LLM instance
_default_llm_instance = None


def get_llm_instance(
    generation_config: Dict[str, Any],
) -> Optional[ChatBedrock]:
    """Get a ChatBedrock instance configured with the provided generation config.
    This function validates the generation_config parameters and applies them
    to the ChatBedrock instance. If the configuration is invalid or if the
    ChatBedrock instance cannot be created, it will return the default instance
    if available, or None if no default instance is set.

    Parameters
    ----------
    generation_config : Dict[str, Any]
        _description_

    Returns
    -------
    Optional[ChatBedrock]
        _description_
    """
    global _default_llm_instance  # Can be used if no dynamic config provided

    # Set default model kwargs for LLM
    effective_model_kwargs = {
        "temperature": 0.1,
        "maxTokenCount": 1024,
        "topP": None,  # Default to Bedrock's internal default if not set
        "stopSequences": None,  # Default to Bedrock's internal default if not set
    }

    # Validate and merge client-provided generation_config
    if "temperature" in generation_config:
        temp = generation_config["temperature"]
        if isinstance(temp, (float, int)) and 0.0 <= temp <= 1.0:
            effective_model_kwargs["temperature"] = float(temp)
        else:
            logger.warning(
                f"Invalid temperature value: {temp}. Using default."
            )

    if "topP" in generation_config:
        top_p_val = generation_config["topP"]
        if isinstance(top_p_val, (float, int)) and 0.0 <= top_p_val <= 1.0:
            effective_model_kwargs["topP"] = float(top_p_val)
        else:
            logger.warning(f"Invalid topP value: {top_p_val}. Using default.")

    if (
        "maxTokenCount" in generation_config
    ):  # Note: Bedrock API uses "maxTokenCount"
        max_tokens = generation_config["maxTokenCount"]
        # Titan Text Express max is 8192, Lite is 4096
        # Assuming BEDROCK_TEXT_GENERATION_MODEL_ID is Express or Lite
        # Add more specific validation if needed based on the exact model.
        if isinstance(max_tokens, int) and 0 <= max_tokens <= 8192:
            effective_model_kwargs["maxTokenCount"] = max_tokens
        else:
            logger.warning(
                f"Invalid maxTokenCount: {max_tokens}. Using default or Bedrock's max."
            )
            # Do not set maxTokenCount if invalid to let Bedrock use its internal default or max.
            # Or, set to a known safe default like 1024 if you prefer explicit control.
            if "maxTokenCount" in effective_model_kwargs and not (
                isinstance(max_tokens, int) and 0 <= max_tokens <= 8192
            ):
                del effective_model_kwargs[
                    "maxTokenCount"
                ]  # remove if invalid, let model default

    if "stopSequences" in generation_config:
        stop_seqs = generation_config["stopSequences"]
        if isinstance(stop_seqs, list) and all(
            isinstance(s, str) for s in stop_seqs
        ):
            effective_model_kwargs["stopSequences"] = stop_seqs
        else:
            logger.warning(
                f"Invalid stopSequences: {stop_seqs}. Ignoring client value."
            )

    # Create ChatBedrock instance with effective model kwargs
    try:
        current_llm = ChatBedrock(
            client=bedrock_runtime_client,
            model=BEDROCK_TEXT_GENERATION_MODEL_ID,
            model_kwargs=effective_model_kwargs,
        )
        logger.info(
            f"ChatBedrock instance configured with: {effective_model_kwargs}"
        )
        return current_llm
    # Return the default instance if available
    except Exception as e_llm_init:
        logger.exception(
            f"Failed to initialize dynamic ChatBedrock instance: {e_llm_init}"
        )
        _default_llm_instance = ChatBedrock(
            client=bedrock_runtime_client,
            model=BEDROCK_TEXT_GENERATION_MODEL_ID,
            model_kwargs={
                "temperature": 0.1,
                "maxTokenCount": 1024,
            },
        )
        return _default_llm_instance  # Return the default instance if dynamic config fails


def _load_faiss_index_from_s3(
    srd_id: str, lambda_logger: Logger
) -> Optional[FAISS]:
    """Load FAISS index from S3 for the given SRD ID.

    Parameters
    ----------
    srd_id : str
        The SRD ID to load the FAISS index for.
    lambda_logger : Logger
        The logger instance to use for logging.

    Returns
    -------
    Optional[FAISS]
        The loaded FAISS index, or None if loading failed.
    """
    # Check if the required clients and embedding model are initialized
    if not s3_client or not embedding_model:  # Check new embedding_model
        lambda_logger.error(
            "S3 client or Bedrock embedding model not initialized."
        )
        return None

    # Check if the bucket name is configured
    if not VECTOR_STORE_BUCKET_NAME:
        lambda_logger.error("VECTOR_STORE_BUCKET_NAME not configured.")
        return None

    # Check if the FAISS index is already in cache
    if srd_id in faiss_index_cache:
        lambda_logger.info(f"FAISS index for '{srd_id}' found in cache.")
        return faiss_index_cache[srd_id]

    # Construct the S3 key for the FAISS index
    s3_index_prefix = f"{srd_id}/faiss_index"
    safe_srd_id = "".join(
        c if c.isalnum() or c in ["-", "_"] else "_" for c in srd_id
    )
    local_faiss_dir = f"/tmp/{safe_srd_id}_faiss_index_query"

    try:
        # Create local directory for FAISS index
        if os.path.exists(local_faiss_dir):
            shutil.rmtree(local_faiss_dir)
        os.makedirs(local_faiss_dir, exist_ok=True)

        # Download the required files from S3
        required_files = ["index.faiss", "index.pkl"]
        for file_name in required_files:
            s3_key = f"{s3_index_prefix}/{file_name}"
            local_file_path = os.path.join(local_faiss_dir, file_name)
            lambda_logger.info(
                f"Downloading s3://{VECTOR_STORE_BUCKET_NAME}/{s3_key} to {local_file_path}"
            )
            s3_client.download_file(
                VECTOR_STORE_BUCKET_NAME, s3_key, local_file_path
            )

        # Load the FAISS index from the local directory
        vector_store = FAISS.load_local(
            folder_path=local_faiss_dir,
            embeddings=embedding_model,  # Uses BedrockEmbeddings
            allow_dangerous_deserialization=True,
        )

        # Check if the vector store was loaded successfully
        if len(faiss_index_cache) >= MAX_CACHE_SIZE:
            oldest_key = next(iter(faiss_index_cache))
            faiss_index_cache.pop(oldest_key)
        faiss_index_cache[srd_id] = vector_store
        return vector_store
    except Exception as e:
        lambda_logger.exception(
            f"Error loading FAISS index for '{srd_id}': {e}"
        )
        return None
    finally:
        # Clean up the local FAISS directory
        if os.path.exists(local_faiss_dir):
            try:
                shutil.rmtree(local_faiss_dir)
            except Exception:
                pass


def get_answer_from_rag(
    query_text: str,
    srd_id: str,
    invoke_generative_llm: bool,
    use_conversational_style: bool,
    generation_config_payload: Dict[str, Any],
    lambda_logger: Logger,
) -> Dict[str, Any]:
    """Process a query using RAG (Retrieval-Augmented Generation) with Bedrock.
    This function retrieves relevant documents from a FAISS index and
    optionally invokes a generative LLM to generate an answer based on the
    retrieved context.

    Parameters
    ----------
    query_text : str
        The query text to process.
    srd_id : str
        The SRD ID to use for the query.
    invoke_generative_llm : bool
        Whether to invoke the generative LLM for the query.
    use_conversational_style : bool
        Whether to use a conversational style for the LLM response.
    generation_config_payload : Dict[str, Any]
        Configuration payload for the LLM generation, including parameters
        like temperature, max tokens, etc.
    lambda_logger : Logger
        The logger instance to use for logging.

    Returns
    -------
    Dict[str, Any]
        The response containing the answer and source information, or an error
        message.
    """
    # Ensure the clients and models are initialized
    if not bedrock_runtime_client or not embedding_model:
        lambda_logger.error(
            "RAG components (Bedrock clients, models) not initialized."
        )
        return {
            "error": (
                "Internal server error: Query processing components not ready."
            )
        }

    # Check if the query cache table name is set
    if not QUERY_CACHE_TABLE_NAME and invoke_generative_llm:
        # Cache only relevant if LLM is invoked
        lambda_logger.warning(
            "QUERY_CACHE_TABLE_NAME not set; Bedrock LLM response caching will be disabled."
        )

    # Generate a cache key
    cache_key_string = f"{srd_id}-{query_text}-{invoke_generative_llm}"
    query_hash = hashlib.md5(cache_key_string.encode()).hexdigest()

    # 1. Check cache if invoking LLM and cache is configured
    if invoke_generative_llm and QUERY_CACHE_TABLE_NAME and dynamodb_client:
        try:
            lambda_logger.info(f"Checking cache for query_hash: {query_hash}")

            # Attempt to get the cached response from DynamoDB
            response = dynamodb_client.get_item(
                TableName=QUERY_CACHE_TABLE_NAME,
                Key={"query_hash": {"S": query_hash}},
            )

            # Check if the item exists and is still valid (TTL)
            if (
                "Item" in response
                and int(response["Item"].get("ttl", {"N": "0"})["N"])
                > time.time()
            ):
                # Return the cached answer if it exists
                lambda_logger.info(f"Cache hit for query_hash: {query_hash}")
                return {
                    "answer": response["Item"]["answer"]["S"],
                    "source": "cache",
                }
        except ClientError as e:
            # Handle DynamoDB client errors
            lambda_logger.warning(
                f"DynamoDB cache get_item error: {e}. Proceeding without cache."
            )
        except Exception as e:
            # Catch other potential errors like missing 'answer' or 'S'
            lambda_logger.warning(
                f"Error processing cache item: {e}. Proceeding without cache."
            )

    # 2. Load the FAISS index from S3
    vector_store = _load_faiss_index_from_s3(srd_id, lambda_logger)
    if not vector_store:
        return {"error": f"Could not load SRD data for '{srd_id}'."}

    # 3. Perform the similarity search
    lambda_logger.info(
        f"Performing similarity search for query: '{query_text}'"
    )
    try:
        # The retriever will fetch relevant documents.
        retriever = vector_store.as_retriever(
            search_kwargs={"k": 4}  # Retrieve top 4 docs
        )
    except Exception as e:
        lambda_logger.exception(f"Error creating retriever: {e}")
        return {"error": "Failed to prepare for information retrieval."}

    # Handle conversational style for the query text
    final_query_text = query_text
    if invoke_generative_llm and use_conversational_style:
        final_query_text = f"User: {query_text}\nBot:"
        lambda_logger.info(
            "Using conversational style for query input to LLM."
        )

    # If not invoking generative LLM, just return formatted retrieved chunks
    if not invoke_generative_llm:
        lambda_logger.info(
            "Generative LLM not invoked by client request. Returning retrieved context."
        )
        docs = retriever.invoke(query_text)  # Langchain 0.2.x uses invoke

        # Check if no documents were retrieved
        if not docs:
            return {
                "answer": (
                    "No specific information found to answer your query based on retrieval."
                ),
                "source": "retrieval_only",
            }

        # Format the retrieved documents into a string
        context_str = "\n\n---\n\n".join([doc.page_content for doc in docs])
        formatted_answer = f"Based on the retrieved SRD content for your query '{query_text}':\n{context_str}"
        return {"answer": formatted_answer, "source": "retrieval_only"}

    # Initialize LLM instance with dynamic config for this request
    current_llm_instance = get_llm_instance(generation_config_payload)
    if not current_llm_instance:
        lambda_logger.error(
            "Failed to initialize ChatBedrock instance with dynamic config."
        )
        return {
            "error": (
                "Internal server error: Generative LLM component could not be configured."
            )
        }

    # Define the prompt template for the generative LLM
    # This prompt template is crucial for guiding the LLM's response.
    prompt_template_str = """You are 'Arcane Scribe', a helpful TTRPG assistant.
Based *only* on the following context from the System Reference Document (SRD), provide a concise and direct answer to the question.
If the question (which might be formatted as 'User: ... Bot:') asks for advice, optimization (e.g., "min-max"), or creative ideas, you may synthesize or infer suggestions *grounded in the provided SRD context*.
Do not introduce rules, abilities, or concepts not present in or directly supported by the context.
If the context does not provide enough information for a comprehensive answer or suggestion, state that clearly.
Always be helpful and aim to directly address the user's intent.
If the question is not formatted as 'User: ... Bot:', you may assume it is a direct question and respond accordingly.

Context:
{context}

Question: {question}

Helpful Answer:"""

    # Create a PromptTemplate instance with the defined template
    PROMPT = PromptTemplate(
        template=prompt_template_str, input_variables=["context", "question"]
    )

    # Create a RetrievalQA chain. This chain will:
    #  1. Use the 'retriever' to fetch documents.
    #  2. Stuff them into the 'PROMPT'.
    #  3. Send that to the 'llm' (ChatBedrock).
    qa_chain = RetrievalQA.from_chain_type(
        llm=current_llm_instance,  # Use dynamically configured LLM
        chain_type="stuff",  # "stuff" is good for short contexts, ensure it fits model context window
        retriever=retriever,
        chain_type_kwargs={"prompt": PROMPT},
        return_source_documents=True,  # Optionally return source documents
    )

    # Invoke the RAG chain with the query text
    lambda_logger.info(
        f"Invoking RAG chain with Bedrock LLM for query: '{final_query_text}'"
    )
    try:
        # The 'query' key for invoke should contain what the {question} placeholder in PROMPT expects
        result = qa_chain.invoke(
            {"query": final_query_text}
        )  # Langchain 0.2.x uses invoke
        answer = result.get("result", "No answer generated.")
        source_docs_content = [
            doc.page_content for doc in result.get("source_documents", [])
        ]

        # Cache the successful Bedrock response
        if (
            QUERY_CACHE_TABLE_NAME
            and dynamodb_client
            and answer != "No answer generated."
        ):
            try:
                # Store the response in DynamoDB cache
                ttl_value = int(time.time() + CACHE_TTL_SECONDS)
                dynamodb_client.put_item(
                    TableName=QUERY_CACHE_TABLE_NAME,
                    Item={
                        "query_hash": {"S": query_hash},
                        "answer": {"S": answer},
                        "srd_id": {"S": srd_id},
                        "query_text": {"S": query_text},
                        "source_documents_summary": {
                            "S": ("; ".join(source_docs_content))[:1000]
                        },
                        "timestamp": {"S": str(time.time())},
                        "ttl": {"N": str(ttl_value)},
                        "generation_config_used": {
                            "S": json.dumps(generation_config_payload)
                        },
                        "was_conversational": {
                            "BOOL": use_conversational_style
                        },
                    },
                )
                lambda_logger.info(
                    f"Bedrock response cached for query_hash: {query_hash}"
                )
            # Catch DynamoDB client errors
            except ClientError as e:
                lambda_logger.warning(
                    f"DynamoDB cache put_item error: {e}. Response not cached."
                )

        # Return the answer and source documents
        lambda_logger.info(
            f"Successfully generated response from Bedrock LLM for query: '{query_text}'"
        )
        return {
            "answer": answer,
            "source_documents_retrieved": len(source_docs_content),
            "source": "bedrock_llm",
        }
    # Catch specific Bedrock client errors
    except ClientError as e:
        lambda_logger.exception(
            f"Bedrock API error during RAG chain execution: {e}"
        )
        return {
            "error": (
                "Error communicating with the AI model. Please try again."
            )
        }
    # Catch other exceptions that may occur during the chain execution
    except Exception as e:
        lambda_logger.exception(f"Error during RAG chain execution: {e}")
        return {"error": "Failed to generate an answer using the RAG chain."}
