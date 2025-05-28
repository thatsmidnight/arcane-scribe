# Standard Library
import json
from typing import Any, Dict

# Third Party
# Third-Party
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.utilities.typing import LambdaContext

# Local Modules
# Local Folder
from presigned_url_generator import processor
from presigned_url_generator.data_classes import PresignedUrlRequest

# Initialize Powertools
logger = Logger()
app = APIGatewayHttpResolver()


@app.post("/srd/upload-url")
def get_presigned_url() -> Dict[str, Any]:
    """
    Endpoint to generate a presigned URL for uploading files to S3.

    The request body should be a JSON object adhering to the
    PresignedUrlRequest schema.

    - Required: `{"file_name": "my_document.pdf"}`
    - Optional: `{"file_name": "my_document.pdf", "content_type": "application/pdf"}`

    Returns
    -------
    dict
        A dictionary suitable for an API Gateway HTTP API response.
    """
    content_type = None

    # Check if the global S3 client is initialized
    if not processor.s3_client:
        logger.error("S3 client is not initialized.")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {"error": "Internal server error: S3 client not available"}
            ),
        }

    # Check if the DOCUMENTS_BUCKET_NAME global variable is set
    if not processor.DOCUMENTS_BUCKET_NAME:
        logger.error("DOCUMENTS_BUCKET_NAME is not configured.")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {"error": "Internal server error: Bucket not configured"}
            ),
        }

    try:
        # Parse the request body as JSON
        request_body = app.current_event.json_body

        # Ensure the request body is a valid JSON object
        if not isinstance(request_body, dict):
            # This case handles if the body is not JSON or is malformed before parsing
            logger.warning(
                "Request body is not a valid JSON object.",
                extra={"body": app.current_event.body},
            )
            raise ValueError("Request body must be a JSON object.")

        # Attempt to instantiate the dataclass
        try:
            validated_data = PresignedUrlRequest(**request_body)
        except TypeError as e:
            logger.warning(
                f"Request body validation failed against dataclass schema: {e}",
                extra={"body": request_body},
            )
            # Provide a clearer message for missing file_name
            if "required positional argument: 'file_name'" in str(
                e
            ) or "'file_name' was not found" in str(e):
                error_message = (
                    "Invalid request payload: 'file_name' is a required field."
                )
            else:
                error_message = f"Invalid request payload: {e}. Ensure only 'file_name' and optional 'content_type' are provided."
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": error_message}),
            }

        # Manual type checks for fields, as dataclasses don't enforce types at runtime by default
        if (
            not isinstance(validated_data.file_name, str)
            or len(validated_data.file_name.strip()) == 0
        ):
            logger.warning(
                "Validation failed: 'file_name' must be a non-empty string.",
                extra={"file_name": validated_data.file_name},
            )
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(
                    {
                        "error": (
                            "'file_name' is required and must be a non-empty string."
                        )
                    }
                ),
            }

        if validated_data.content_type is not None and not isinstance(
            validated_data.content_type, str
        ):
            logger.warning(
                "Validation failed: 'content_type' must be a string if provided.",
                extra={"content_type": validated_data.content_type},
            )
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(
                    {"error": "'content_type' must be a string if provided."}
                ),
            }

        file_name = validated_data.file_name.strip()
        # This will be None if not provided, or a string
        content_type = validated_data.content_type

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
    except Exception as e:
        logger.exception(
            f"Error processing request input: {e}",
            extra={"raw_body": app.current_event.body},
        )
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Error processing request data."}),
        }

    # Generate the presigned URL
    content_type = (
        content_type or "application/pdf"
    )  # Default to PDF if not provided
    expiration_seconds = 900  # 15 minutes
    try:
        logger.info(
            f"Generating presigned URL for bucket: {processor.DOCUMENTS_BUCKET_NAME}, key: {file_name}"
        )
        presigned_url = processor.generate_presigned_url(
            file_name=file_name,
            content_type=content_type,
            expiration=expiration_seconds,
        )
        logger.info(
            f"Successfully generated presigned URL for key: {file_name}"
        )
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {
                    "presigned_url": presigned_url,
                    "bucket_name": processor.DOCUMENTS_BUCKET_NAME,
                    "key": file_name,
                    "expires_in": expiration_seconds,
                    "method": "PUT",
                }
            ),
        }
    except ClientError as e:
        logger.exception(
            f"Boto3 ClientError generating presigned URL for key {file_name}: {e}"
        )
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Could not generate upload URL."}),
        }
    except Exception as e:
        logger.exception(
            f"Unexpected error generating presigned URL for key {file_name}: {e}"
        )
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "An unexpected error occurred."}),
        }


@logger.inject_lambda_context(
    log_event=True, correlation_id_path=correlation_paths.API_GATEWAY_HTTP
)
def lambda_handler(
    event: Dict[str, Any], context: LambdaContext
) -> Dict[str, Any]:
    """
    Lambda function handler to process API Gateway HTTP API events for
    generating presigned URLs for S3 uploads.

    Parameters
    ----------
    event : Dict[str, Any]
        The event data from API Gateway, containing the HTTP request details.
    context : LambdaContext
        The context object providing runtime information about the Lambda
        function.

    Returns
    -------
    Dict[str, Any]
        A dictionary containing the HTTP response with a presigned URL or an
        error message.
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
