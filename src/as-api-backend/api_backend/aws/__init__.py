"""AWS module for the Arcane Scribe API Backend.

This module provides AWS-related functionality for the Arcane Scribe API
Backend, including clients for DynamoDB, SSM, S3, and Bedrock. It allows for
easy access to these services without needing to import them individually in
other parts of the codebase.
"""

# Local Modules
from api_backend.aws.s3 import S3Client
from api_backend.aws.ssm import SsmClient
from api_backend.aws.dynamodb import DynamoDb
from api_backend.aws.bedrock_runtime import BedrockRuntimeClient

__all__ = [
    "S3Client",
    "SsmClient",
    "DynamoDb",
    "BedrockRuntimeClient",
]
