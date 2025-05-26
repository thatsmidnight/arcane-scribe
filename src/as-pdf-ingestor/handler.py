# Third-Party
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.utilities.data_classes import S3Event

# Initialize the logger
logger = Logger()


@logger.inject_lambda_context(log_event=True)
def lambda_handler(event: S3Event, context: LambdaContext) -> None:
    """Lambda function handler to process S3 events for PDF ingestion.

    Parameters
    ----------
    event : S3Event
        The S3 event data containing information about the uploaded PDF files.
    context : LambdaContext
        The context object containing runtime information about the Lambda
        function.
    """
    # Log the received event
    logger.info("Received S3 event", extra={"event": event})

    # Process the S3 event
    for record in event.records:
        bucket_name = record.s3.bucket.name
        object_key = record.s3.get_object.key
        logger.info(f"Processing file {object_key} from bucket {bucket_name}")

        # Here you would add your logic to handle the PDF ingestion
        # For example, downloading the file, processing it, etc.

    logger.info("PDF ingestion completed")
