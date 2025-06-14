"""
This module initializes the API backend for the Arcane Scribe project.

It imports the main API router and configuration settings, and exposes them
for use in the application.
"""

# Local Modules
from api_backend.api import router
from api_backend.config import (
    API_PREFIX,
    DOCUMENTS_BUCKET_NAME,
    VECTOR_STORE_BUCKET_NAME,
    QUERY_CACHE_TABLE_NAME,
    BEDROCK_EMBEDDING_MODEL_ID,
    BEDROCK_TEXT_GENERATION_MODEL_ID,
    HOME_IP_SSM_PARAMETER_NAME,
)

__all__ = [
    "router",
    "API_PREFIX",
    "DOCUMENTS_BUCKET_NAME",
    "VECTOR_STORE_BUCKET_NAME",
    "QUERY_CACHE_TABLE_NAME",
    "BEDROCK_EMBEDDING_MODEL_ID",
    "BEDROCK_TEXT_GENERATION_MODEL_ID",
    "HOME_IP_SSM_PARAMETER_NAME",
]
