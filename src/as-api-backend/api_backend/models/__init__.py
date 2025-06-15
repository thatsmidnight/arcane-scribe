"""This module initializes the models package for the API backend.

It imports and exposes the necessary Pydantic models for handling
Retrieval-Augmented Generation (RAG) queries and presigned URL requests.
"""

# Local Modules
from api_backend.models.srd import (
    PresignedUrlRequest,
    PresignedUrlResponse,
    PresignedUrlErrorResponse,
)
from api_backend.models.query import (
    RagQueryRequest,
    GenerationConfig,
    RagQueryResponse,
    RagQueryErrorResponse,
)

__all__ = [
    "PresignedUrlRequest",
    "PresignedUrlResponse",
    "PresignedUrlErrorResponse",
    "RagQueryRequest",
    "GenerationConfig",
    "RagQueryResponse",
    "RagQueryErrorResponse",
]
