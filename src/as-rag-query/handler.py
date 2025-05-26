# Standard Library
import typing as t

# Third-Party
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.typing import LambdaContext

# Initialize the tracer and logger
tracer = Tracer()
logger = Logger()
app = APIGatewayHttpResolver()


@app.post("/query")
@tracer.capture_method
def query() -> t.Union[dict, tuple]:
    """
    Endpoint to handle RAG queries.

    Returns
    -------
    dict or tuple
        A dictionary containing the query result or an error message if the
        query fails.
    """
    # Get the S3 client and bucket name from environment variables
    # s3_client = boto3.client("s3")
    # bucket_name = os.environ.get("VECTOR_STORE_BUCKET_NAME")
    query_text = app.current_event.json_body.get("query_text")

    # Validate the query text
    if not query_text:
        return {"error": "Query text is required"}, 400

    # Process the query or handle any exceptions
    try:
        # Placeholder for actual query processing logic
        result = {"message": f"Processed query: {query_text}"}
        return result
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        return {"error": str(e)}, 500


@logger.inject_lambda_context(
    log_event=True, correlation_id_path=correlation_paths.API_GATEWAY_HTTP
)
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """Lambda function handler to process API Gateway events for RAG queries.

    Parameters
    ----------
    event : dict
        The event data containing the query request.
    context : LambdaContext
        The context object containing runtime information about the Lambda
        function.

    Returns
    -------
    dict
        The response from the query endpoint, which may include the query
        result or an error message.
    """
    return app.resolve(event, context)
