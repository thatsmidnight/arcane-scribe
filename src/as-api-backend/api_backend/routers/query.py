# Standard Library
from typing import Union

# Third Party
from aws_lambda_powertools import Logger
from fastapi import APIRouter, Body, status
from fastapi.responses import JSONResponse

# Local Modules
from api_backend.utils import get_answer_from_rag
from api_backend.models import (
    RagQueryRequest,
    RagQueryResponse,
    RagQueryErrorResponse,
)

# Initialize logger
logger = Logger(service="query")

# Initialize router for asset management
router = APIRouter(prefix="/query", tags=["Query"])


@router.post(
    "",
    response_model=Union[RagQueryResponse, RagQueryErrorResponse],
    status_code=status.HTTP_200_OK,
)
def query_endpoint(request: RagQueryRequest = Body(...)) -> JSONResponse:
    try:
        # Extract query text and SRD ID from the request body
        query_text = request.query_text.strip()
        srd_id = request.srd_id.strip()

        # Extract optional parameters for generative LLM configuration
        # Use generative LLM flag
        invoke_generative_llm = request.invoke_generative_llm

        # Use conversational style flag
        use_conversational_style = request.use_conversation_style

        # Generation config payload
        generation_config_payload = request.generation_config or {}

    # Parsing errors
    except Exception as e:
        logger.exception(
            f"Error processing query request input: {e}",
            extra={"raw_body": request.model_dump_json()},
        )
        status_code = status.HTTP_400_BAD_REQUEST
        content = {"error": f"Malformed request: {e}"}

    # Get the answer from the RAG processor
    try:
        logger.info(
            f"Processing query for SRD '{srd_id}': '{query_text}', Generative: {invoke_generative_llm}"
        )
        content = get_answer_from_rag(
            query_text=query_text,
            srd_id=srd_id,
            invoke_generative_llm=invoke_generative_llm,
            use_conversational_style=use_conversational_style,
            generation_config_payload=generation_config_payload,
            lambda_logger=logger,
        )

        # Check if the result contains an error
        status_code = 200
        if "error" in content:
            logger.warning(
                f"Query for '{query_text}' on '{srd_id}' resulted in error: {content['error']}"
            )
            if "Could not load SRD data" in content["error"]:
                status_code = 404
            elif "components not ready" in content["error"]:
                status_code = 503  # Service unavailable
            else:
                status_code = 500  # General internal error from processor

    # Handle specific errors from the RAG processor
    except Exception as e:
        logger.exception(
            f"Unhandled error in query_endpoint for SRD '{srd_id}': {e}"
        )
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        content = {"error": f"Internal server error: {e}"}

    # Return the response
    return JSONResponse(
        status_code=status_code,
        content=content,
    )
