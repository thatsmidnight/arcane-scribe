"""
CCK API Authorizer

This module provides utilities for a custom Lambda authorizer that validates
API requests against AWS Cognito user pools. It includes functions to get the
Cognito client, generate IAM policies, and log events.
"""

# Local Modules
from .utils import (
    get_cognito_client,
    generate_policy,
    logger,
    USER_POOL_ID,
    USER_POOL_CLIENT_ID,
)

__all__ = [
    "get_cognito_client",
    "generate_policy",
    "logger",
    "USER_POOL_ID",
    "USER_POOL_CLIENT_ID",
]
