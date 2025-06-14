# Standard Library
import os
import time
import json
import shutil
import hashlib
from typing import Optional, Dict, Any

# Third Party
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger
from langchain_aws import ChatBedrock
from langchain_community.vectorstores import FAISS
from langchain.chains.retrieval_qa.base import RetrievalQA
from langchain.prompts import PromptTemplate

# Local Modules
from api_backend import (
    BEDROCK_EMBEDDING_MODEL_ID,
    BEDROCK_TEXT_GENERATION_MODEL_ID,
    VECTOR_STORE_BUCKET_NAME,
    QUERY_CACHE_TABLE_NAME,
)
from api_backend.aws import S3Client, DynamoDb, BedrockRuntimeClient

# Initialize logger
logger = Logger(service="rag-query-processor")

# Default cache settings
CACHE_TTL_SECONDS = 3600  # Cache responses for 1 hour, adjust as needed

# Settings for the FAISS index cache
FAISS_INDEX_CACHE: dict[str, FAISS] = {}
MAX_CACHE_SIZE = 3

# Initialize default LLM instance
DEFAULT_LLM_INSTANCE: Optional[ChatBedrock] = None


def get_llm_instance(
    generation_config: Dict[str, Any],
) -> Optional[ChatBedrock]:
    """Get a ChatBedrock instance configured with the provided generation
    config. This function validates the generation_config parameters and
    applies them to the ChatBedrock instance. If the configuration is invalid
    or if the ChatBedrock instance cannot be created, it will return the
    default instance if available, or None if no default instance is set.

    Parameters
    ----------
    generation_config : Dict[str, Any]
        The generation configuration parameters, which may include:
        - temperature (float): Controls randomness in generation.
        - topP (float): Controls diversity via nucleus sampling.
        - maxTokenCount (int): Maximum number of tokens to generate.
        - stopSequences (list of str): Sequences that will stop generation.

    Returns
    -------
    Optional[ChatBedrock]
        A ChatBedrock instance configured with the provided generation config,
        or None if the configuration is invalid or if no default instance is
        set.
    """
    global DEFAULT_LLM_INSTANCE  # Can be used if no dynamic config provided

    # Initialize the Bedrock runtime client
    bedrock_runtime_client = BedrockRuntimeClient()

    # Initialize the model kwargs as an empty dictionary
    effective_model_kwargs = {}

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
        current_llm = bedrock_runtime_client.get_chat_model(
            model_id=BEDROCK_TEXT_GENERATION_MODEL_ID,
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
        DEFAULT_LLM_INSTANCE = bedrock_runtime_client.get_chat_model(
            model_id=BEDROCK_TEXT_GENERATION_MODEL_ID,
            model_kwargs={
                "temperature": 0.1,
                "maxTokenCount": 1024,
            },
        )
        return DEFAULT_LLM_INSTANCE  # Return default instance if dynamic config fails


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
    # Initialize the Bedrock runtime client
    bedrock_runtime_client = BedrockRuntimeClient()

    # Initialize the S3 client
    s3_client = S3Client(bucket_name=VECTOR_STORE_BUCKET_NAME)

    # Check if the FAISS index is already in cache
    if srd_id in FAISS_INDEX_CACHE:
        lambda_logger.info(f"FAISS index for '{srd_id}' found in cache.")
        return FAISS_INDEX_CACHE[srd_id]

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
            download_file_success = s3_client.download_file(
                object_key=s3_key, download_path=local_file_path
            )
            logger.info(
                f"Result of S3 download for {s3_key}: "
                f"{'SUCCESS' if download_file_success else 'FAILURE'}"
            )

        # Load the FAISS index from the local directory
        vector_store = FAISS.load_local(
            folder_path=local_faiss_dir,
            embeddings=bedrock_runtime_client.get_embedding_model(
                model_id=BEDROCK_EMBEDDING_MODEL_ID
            ),  # Uses BedrockEmbeddings
            allow_dangerous_deserialization=True,
        )

        # Check if the vector store was loaded successfully
        if len(FAISS_INDEX_CACHE) >= MAX_CACHE_SIZE:
            oldest_key = next(iter(FAISS_INDEX_CACHE))
            FAISS_INDEX_CACHE.pop(oldest_key)
        FAISS_INDEX_CACHE[srd_id] = vector_store
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
    lambda_logger: Optional[Logger] = None,
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
    lambda_logger : Optional[Logger]
        The logger instance to use for logging. If None, a default logger
        will be used.

    Returns
    -------
    Dict[str, Any]
        The response containing the answer and source information, or an error
        message.
    """
    # Initialize the DynamoDB client
    dynamodb_client = DynamoDb(table_name=QUERY_CACHE_TABLE_NAME)

    # Use the provided logger or create a new one if not provided
    if lambda_logger is None:
        lambda_logger = logger

    # Cache table is only relevant if LLM is invoked
    if invoke_generative_llm:
        lambda_logger.warning(
            "Invoking generative LLM, cache table will be used for caching responses."
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
                key={"query_hash": query_hash},
            )

            # TODO: REMOVE THIS LINE AFTER TESTING
            lambda_logger.info(
                f"Cache response for query_hash {query_hash}: {response}"
            )

            # Check if the item exists and is still valid (TTL)
            if (
                response
                and "Item" in response
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
                    item={
                        "query_hash": query_hash,
                        "answer": answer,
                        "srd_id": srd_id,
                        "query_text": query_text,
                        "source_documents_summary": (
                            "; ".join(source_docs_content)
                        )[:1000],
                        "timestamp": str(time.time()),
                        "ttl": str(ttl_value),
                        "generation_config_used": json.dumps(
                            generation_config_payload
                        ),
                        "was_conversational": use_conversational_style,
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
