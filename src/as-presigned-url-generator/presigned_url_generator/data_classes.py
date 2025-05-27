# Standard Library
from typing import Optional
from dataclasses import dataclass, field


# Define a dataclass for request body validation
@dataclass
class PresignedUrlRequest:
    file_name: str = field(
        metadata={"description": "The name of the file to upload."}
    )
    content_type: Optional[str] = field(
        default=None,
        metadata={"description": "Optional content type for the file."},
    )
