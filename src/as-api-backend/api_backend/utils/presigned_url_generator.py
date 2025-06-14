# Third Party
from aws_lambda_powertools import Logger

# Local Modules
from api_backend import DOCUMENTS_BUCKET_NAME
from api_backend.aws import S3Client

# Initialize logger
logger = Logger(service="presigned-url-generator")


def generate_presigned_url(
    file_name: str,
    srd_id: str,
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

    # Initialize S3 client
    s3_client = S3Client(bucket_name=DOCUMENTS_BUCKET_NAME)

    # Generate presigned URL with content type
    try:
        presigned_url = s3_client.generate_presigned_upload_url(
            object_key=object_key,
            expiration=expiration,
        )

        if not presigned_url:
            raise ValueError("Failed to generate presigned URL.")
    except Exception as e:
        logger.error(f"Failed to generate presigned URL: {e}")
        raise e
    else:
        logger.info(
            f"Presigned URL generated successfully for {object_key} with "
            f"expiration {expiration} seconds."
        )
        return presigned_url
