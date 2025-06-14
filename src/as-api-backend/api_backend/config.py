"""Configuration for the API backend.

This module sets up environment variables for the API backend,
including the S3 bucket name, DynamoDB table name, and Bedrock model ID.
"""

# Standard Library
import os

# Environment variables for configuration
API_PREFIX = os.environ.get("API_PREFIX", "/api/v1")
DOCUMENTS_BUCKET = os.environ.get("DOCUMENTS_BUCKET_NAME")
VECTOR_STORE_BUCKET_NAME = os.environ.get("VECTOR_STORE_BUCKET_NAME")
QUERY_CACHE_TABLE_NAME = os.environ.get("QUERY_CACHE_TABLE_NAME")
BEDROCK_EMBEDDING_MODEL_ID = os.environ.get(
    "BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-text-express-v1"
)
BEDROCK_TEXT_GENERATION_MODEL_ID = os.environ.get(
    "BEDROCK_TEXT_GENERATION_MODEL_ID", "amazon.titan-text-express-v1"
)
