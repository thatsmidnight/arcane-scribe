# Standard Library
from typing import Dict, Any

# Third Party
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.utilities.data_classes import S3Event, event_source

# Local Modules
from pdf_ingestor import processor

# Initialize Powertools
logger = Logger()


@logger.inject_lambda_context(log_event=True)
@event_source(data_class=S3Event)
def lambda_handler(event: S3Event, context: LambdaContext) -> Dict[str, Any]:
    """
    Lambda function handler to process S3 events for PDF ingestion.
    Utilizes a separate processor module for the core logic.

    Parameters
    ----------
    event : S3Event
        The S3 event data automatically parsed by Powertools.
    context : LambdaContext
        The context object containing runtime information.
    """
    logger.info("PDF ingestion Lambda triggered.")

    # Initialize a list to collect results or errors for each record processed.
    results = []

    # The S3Event object can contain multiple records if batching occurs,
    # though typically for S3 triggers it's one object per event invocation unless configured otherwise.
    for record in event.records:
        bucket_name = record.s3.bucket.name
        # S3 object keys are URL-encoded (e.g., spaces become '+').
        # Powertools S3Event record.s3.get_object.key automatically decodes it.
        object_key = record.s3.get_object.key
        object_version_id = record.s3.get_object.version_id
        event_name = record.event_name
        event_time = record.event_time

        # Log the event details for debugging and traceability
        logger.info(
            "Processing S3 event record.",
            extra={
                "event_name": event_name,
                "event_time": str(
                    event_time
                ),  # str() for JSON serializable logging
                "bucket_name": bucket_name,
                "object_key": object_key,
                "object_version_id": object_version_id,
                "object_size": record.s3.get_object.size,  # Size in bytes
            },
        )

        # Basic check to avoid processing non-PDF files if the S3 trigger is too broad
        # (though our CDK config filters for .pdf suffix)
        if not object_key.lower().endswith(".pdf"):
            logger.warning(f"Object {object_key} is not a PDF file. Skipping.")
            continue

        try:
            # Call the main processing function from the local module
            # Pass the Powertools logger instance so the processor module can use the same contextual logging
            result = processor.process_s3_object(bucket_name, object_key, logger)

            # Append the result to the results list for further processing or logging
            results.append(result)
            logger.info(
                f"Successfully processed and vectorized: s3://{bucket_name}/{object_key}"
            )
        except Exception as e:
            # The processor module should log specifics, this is a catch-all for the record.
            logger.exception(
                f"Failed to process s3://{bucket_name}/{object_key}. Error: {e}"
            )

            # Append the error to the results list for further handling
            results.append(
                {
                    "error": str(e),
                    "bucket": bucket_name,
                    "key": object_key,
                }
            )

    logger.info(
        "PDF ingestion processing loop completed for all records in the event."
    )
    return {"results": results}
