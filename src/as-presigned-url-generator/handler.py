# Standard Library
import os
import typing as t

# Third-Party
import boto3
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.typing import LambdaContext

# Initialize the tracer and logger
tracer = Tracer()
logger = Logger()
app = APIGatewayHttpResolver()


@app.post("/srd/upload-url")
@tracer.capture_method
def get_presigned_url() -> t.Union[dict, tuple]:
    """Endpoint to generate a presigned URL for uploading files to S3.

    Returns
    -------
    dict or tuple
        A dictionary containing the presigned URL and the S3 bucket name,
        or an error message if the file name is not provided or if an error
        occurs during URL generation.
    """
    # Get the S3 client and bucket name from environment variables
    s3_client = boto3.client("s3")
    bucket_name = os.environ.get("DOCUMENTS_BUCKET_NAME")
    file_name = app.current_event.json_body.get("file_name")

    # Validate the file name
    if not file_name:
        return {"error": "File name is required"}, 400

    # Generate the presigned URL or handle any exceptions
    try:
        presigned_url = s3_client.generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket_name, "Key": file_name},
            ExpiresIn=3600,  # URL valid for 1 hour
        )
        return {"presigned_url": presigned_url, "bucket_name": bucket_name}
    except Exception as e:
        logger.error(f"Error generating presigned URL: {e}")
        return {"error": str(e)}, 500


@logger.inject_lambda_context(
    log_event=True, correlation_id_path=correlation_paths.API_GATEWAY_HTTP
)
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """Lambda function handler to process API Gateway events for generating
    presigned URLs for S3 uploads.

    Parameters
    ----------
    event : dict
        The event data containing information about the API Gateway request.
    context : LambdaContext
        The context object containing runtime information about the Lambda
        function.

    Returns
    -------
    dict
        The response from the API Gateway resolver, which includes the
        presigned URL.
    """
    return app.resolve(event, context)
