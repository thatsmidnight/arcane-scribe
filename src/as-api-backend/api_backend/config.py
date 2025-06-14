"""Configuration for the API backend.

This module sets up environment variables for the API backend,
including the S3 bucket name, DynamoDB table name, and Bedrock model ID.
"""

# Standard Library
import os

# Environment variables for configuration
API_PREFIX = os.environ["API_PREFIX"]
DOCUMENTS_BUCKET_NAME = os.environ["DOCUMENTS_BUCKET_NAME"]
VECTOR_STORE_BUCKET_NAME = os.environ["VECTOR_STORE_BUCKET_NAME"]
QUERY_CACHE_TABLE_NAME = os.environ["QUERY_CACHE_TABLE_NAME"]
BEDROCK_EMBEDDING_MODEL_ID = os.environ["BEDROCK_EMBEDDING_MODEL_ID"]
BEDROCK_TEXT_GENERATION_MODEL_ID = os.environ[
    "BEDROCK_TEXT_GENERATION_MODEL_ID"
]
