# Standard Library
from typing import Union

# Third Party
from fastapi import APIRouter, status, Body
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger

# Local Modules
from api_backend.utils import (
    generate_presigned_url,
    AllowedMethod,
)
from api_backend.models import (
    PresignedUrlRequest,
    PresignedUrlResponse,
    PresignedUrlErrorResponse,
)
from api_backend.utils.config import DOCUMENTS_BUCKET_NAME

# Initialize logger
logger = Logger(service="srd")

# Initialize router for asset management
router = APIRouter(prefix="/srd", tags=["SRD"])


@router.post(
    "/upload-url",
    response_model=Union[PresignedUrlResponse, PresignedUrlErrorResponse],
    status_code=status.HTTP_200_OK,
)
def get_presigned_upload_url(
    request: PresignedUrlRequest = Body(...),
) -> JSONResponse:
    """Generate a presigned URL for uploading a file to S3.

    **Parameters:**
    - **request**: PresignedUrlRequest
        The request body containing the file name and SRD ID, including:
        - `file_name`: The name of the file to upload.
        - `srd_id`: The ID of the SRD document.

    **Returns:**
    - **JSONResponse**: A JSON response containing the presigned URL and other
    details, or an error message if the request fails.
    """
    # Parse the request body
    try:
        file_name = str(request.file_name).strip()
        srd_id = request.srd_id.strip()
    except Exception as e:
        logger.exception(
            f"Error processing request input: {e}",
            extra={"raw_body": request.model_dump_json()},
        )
        status_code = status.HTTP_400_BAD_REQUEST
        content = {"error": f"Error processing request data: {e}"}

    # Generate the presigned URL
    expiration_seconds = 900  # 15 minutes
    try:
        logger.info(
            f"Generating presigned URL for bucket: {DOCUMENTS_BUCKET_NAME}, key: {file_name}"
        )
        presigned_url = generate_presigned_url(
            file_name=file_name,
            srd_id=srd_id,
            expiration=expiration_seconds,
        )
        logger.info(
            f"Successfully generated presigned URL for key: {file_name}"
        )
        status_code = status.HTTP_200_OK
        content = {
            "presigned_url": presigned_url,
            "bucket_name": DOCUMENTS_BUCKET_NAME,
            "key": file_name,
            "expires_in": expiration_seconds,
            "method": AllowedMethod.put.value,
        }
    except Exception as e:
        logger.exception(
            f"Unexpected error generating presigned URL for key {file_name}: {e}"
        )
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        content = {"error": f"Could not generate upload URL: {e}"}

    # Return the response
    return JSONResponse(
        status_code=status_code,
        content=content,
    )
