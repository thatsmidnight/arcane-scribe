# Standard Library
from typing import Optional
from dataclasses import dataclass, field


# Define a dataclass for request body validation
@dataclass
class PresignedUrlRequest:
    """Data class for presigned URL generation requests.

    Attributes
    ----------
        file_name : str
            The name of the file to upload.
        srd_id : str
            The ID of the SRD document.
        content_type : Optional[str]
            Optional content type for the file.
    """

    file_name: str = field(
        metadata={"description": "The name of the file to upload."}
    )
    srd_id: str = field(
        metadata={"description": "The ID of the SRD document."}
    )
    content_type: Optional[str] = field(
        default=None,
        metadata={"description": "Optional content type for the file."},
    )
