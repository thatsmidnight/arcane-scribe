# Standard Library
import os

# Third Party
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger

# Initialize logger
logger = Logger(service="presigned_url_generator_processor")

# Initialize Boto3 S3 client globally
try:
    s3_client = boto3.client("s3")
except Exception as e:
    logger.exception(f"Failed to initialize Boto3 S3 client globally: {e}")
    raise e

# Retrieve environment variables
DOCUMENTS_BUCKET_NAME = os.environ.get("DOCUMENTS_BUCKET_NAME")
if not DOCUMENTS_BUCKET_NAME:
    logger.error("DOCUMENTS_BUCKET_NAME environment variable is not set.")
    raise Exception(
        "Environment variable DOCUMENTS_BUCKET_NAME must be set for S3 operations."
    )


def generate_presigned_url(
    file_name: str,
    srd_id: str,
    content_type: str = "application/pdf",
    expiration: int = 3600,
) -> str:
    """
    Generate a presigned URL for uploading a file to S3.

    Parameters
    ----------
    file_name : str
        The name of the file to be uploaded.
    srd_id : str
        The client-specified SRD identifier.
    content_type : str, optional
        The content type of the file, defaults to "application/pdf".
    expiration : int, optional
        The number of seconds the presigned URL is valid for, defaults to
        3600 seconds (1 hour).

    Returns
    -------
    str
        A presigned URL for uploading the file to S3.

    Raises
    ------
    ClientError
        If there is an error generating the presigned URL.
    """
    # Construct object key using SRD ID as prefix
    object_key = f"{srd_id}/{file_name}"

    # Generate presigned URL with content type
    try:
        presigned_url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": DOCUMENTS_BUCKET_NAME,
                "Key": object_key,
                "ContentType": content_type,
            },
            ExpiresIn=expiration,
        )
        return presigned_url
    except ClientError as e:
        logger.error(f"Failed to generate presigned URL: {e}")
        raise e
