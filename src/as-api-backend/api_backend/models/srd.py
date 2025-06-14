# Standard Library
from typing import Optional

# Third Party
from pydantic import BaseModel, Field, ConfigDict


class PresignedUrlRequest(BaseModel):
    """Pydantic model for presigned URL generation requests.

    Attributes:
        file_name: The name of the file to upload.
        srd_id: The ID of the SRD document.
        content_type: Optional content type for the file.
    """

    model_config = ConfigDict(populate_by_name=True)

    file_name: str = Field(
        ..., description="The name of the file to upload.", min_length=1
    )
    srd_id: str = Field(
        ..., description="The ID of the SRD document.", min_length=1
    )
    content_type: Optional[str] = Field(
        default=None, description="Optional content type for the file."
    )
