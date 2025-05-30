# Standard Library
import json
from typing import Any, Dict

# Third Party
from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.typing import LambdaContext

# Local Modules
from rag_query_processor import processor

# Initialize Powertools
logger = Logger()
app = APIGatewayHttpResolver()


@app.post("/query")
def query_endpoint() -> Dict[str, Any]:
    """
    Endpoint to process a query against the RAG processor.

    The request body should be a JSON object with the following structure:
    {
        "query_text": "Your query text here",
        "srd_id": "Optional SRD ID, defaults to processor.DEFAULT_SRD_ID",
        "invoke_generative_llm": true | false  # Optional, invokes the generative LLM, defaults to false
        "use_conversation_style": false | true  # Optional, uses conversation style, defaults to false
        "generation_config": {  # Optional, tuning parameters for the generative LLM
            "temperature": 0.1,  # Optional (0.0-1.0), controls randomness in generation
            "topP": 0.9,  # Optional (0.0-1.0), controls diversity in generation
            "maxTokenCount": 1024,  # Optional (0-8192), maximum number of tokens to generate
            "stopSequences": ["\n"]  # Optional, sequences that stop generation
        }
    }

    - Required: `{"query_text": "What is the capital of France?"}`
    - Optional: `{"query_text": "What is the capital of France?", "srd_id": "my_srd_id", "invoke_generative_llm": true}`

    Returns
    -------
    Dict[str, Any]
        A dictionary suitable for an API Gateway HTTP API response.

    Raises
    ------
    ValueError
        If the request body is not a valid JSON object or if required fields
        are missing or invalid.
    """
    try:
        # Initialize Boto3 clients and embedding model
        if (
            not processor.s3_client
            or not processor.embedding_model
            or not processor.bedrock_runtime_client
        ):
            logger.error(
                "CRITICAL: RAG Processor Boto3 clients or embedding model not initialized."
            )
            return {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(
                    {
                        "error": (
                            "Internal server error: RAG Processor not initialized."
                        )
                    }
                ),
            }

        # Parse the request body as JSON
        request_body = app.current_event.json_body
        if not isinstance(request_body, dict):
            raise ValueError("Request body must be a JSON object.")

        # Extract query text and SRD ID from the request body
        query_text = request_body.get("query_text")
        srd_id = request_body.get("srd_id", processor.DEFAULT_SRD_ID)

        # Extract optional parameters for generative LLM configuration
        # Use generative LLM flag
        invoke_generative_llm = request_body.get(
            "invoke_generative_llm", False
        )
        if not isinstance(invoke_generative_llm, bool):
            invoke_generative_llm = False

        # Use conversational style flag
        use_conversational_style = request_body.get(
            "use_conversational_style", False
        )
        if not isinstance(use_conversational_style, bool):
            use_conversational_style = False

        # Generation config payload
        generation_config_payload = request_body.get("generation_config", {})
        if not isinstance(generation_config_payload, dict):
            logger.warning(
                "generation_config, if provided, must be an object. Using defaults."
            )
            generation_config_payload = {}

        # Basic validation for required fields
        if (
            not query_text
            or not isinstance(query_text, str)
            or len(query_text.strip()) == 0
        ):
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Query text is required."}),
            }
        if (
            not srd_id
            or not isinstance(srd_id, str)
            or len(srd_id.strip()) == 0
        ):
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "SRD ID is required."}),
            }

        # Strip whitespace from query_text and srd_id
        query_text = query_text.strip()
        srd_id = srd_id.strip()

    # From isinstance check
    except ValueError as e:
        logger.warning(
            f"Invalid request body structure: {e}",
            extra={"raw_body": app.current_event.body},
        )
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e)}),
        }
    # Other parsing errors
    except Exception as e:
        logger.exception(
            f"Error processing query request input: {e}",
            extra={"raw_body": app.current_event.body},
        )
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Malformed request."}),
        }

    # Get the answer from the RAG processor
    try:
        logger.info(
            f"Processing query for SRD '{srd_id}': '{query_text}', Generative: {invoke_generative_llm}"
        )
        result = processor.get_answer_from_rag(
            query_text=query_text,
            srd_id=srd_id,
            invoke_generative_llm=invoke_generative_llm,
            use_conversational_style=use_conversational_style,
            generation_config_payload=generation_config_payload,
            lambda_logger=logger
        )

        # Check if the result contains an error
        status_code = 200
        if "error" in result:
            logger.warning(
                f"Query for '{query_text}' on '{srd_id}' resulted in error: {result['error']}"
            )
            if "Could not load SRD data" in result["error"]:
                status_code = 404
            elif "components not ready" in result["error"]:
                status_code = 503  # Service unavailable
            else:
                status_code = 500  # General internal error from processor

        return {
            "statusCode": status_code,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(result),
        }

    # Handle specific errors from the RAG processor
    except Exception as e:
        logger.exception(
            f"Unhandled error in query_endpoint for SRD '{srd_id}': {e}"
        )
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Internal server error."}),
        }


@logger.inject_lambda_context(
    log_event=True, correlation_id_path=correlation_paths.API_GATEWAY_HTTP
)
def lambda_handler(
    event: Dict[str, Any], context: LambdaContext
) -> Dict[str, Any]:
    """Lambda handler for the RAG query processor.

    Parameters
    ----------
    event : Dict[str, Any]
        The event data passed to the Lambda function, typically from API
        Gateway.
    context : LambdaContext
        The context object providing runtime information to the Lambda
        function.

    Returns
    -------
    Dict[str, Any]
        The response from the API Gateway HTTP resolver, which includes the
        status code, headers, and body of the response.
    """
    try:
        return app.resolve(event, context)
    except Exception as e:
        logger.exception(f"Unhandled exception in lambda_handler: {e}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {"error": "An internal server error occurred."}
            ),
        }
