# Standard Library
import os
from typing import Dict, Any, Optional

# Third Party
import boto3
from aws_lambda_powertools import Logger

# Initialize logger
logger = Logger(service="cck-api-authorizer-utils")

# Retrieve configuration from environment variables
USER_POOL_ID = os.environ.get("USER_POOL_ID")
USER_POOL_CLIENT_ID = os.environ.get("USER_POOL_CLIENT_ID")

# Initialize Cognito client as None
cognito_client: Optional[boto3.client] = None


def get_cognito_client() -> boto3.client:
    """Get or create a Boto3 Cognito IDP client.

    Returns
    -------
    boto3.client
        A Boto3 Cognito IDP client.

    Raises
    ------
    Exception
        If the client cannot be initialized.
    """
    # Make the cognito_client global to ensure it can be reused
    global cognito_client

    # If the client is not initialized, create a new one
    if cognito_client is None:
        try:
            cognito_client = boto3.client("cognito-idp")
        except Exception as e:
            logger.exception(
                f"Failed to initialize Boto3 Cognito IDP client: {e}"
            )
            raise e
    return cognito_client


def generate_policy(
    principal_id: str,
    effect: str,
    resource: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate an IAM policy for the API Gateway authorizer.

    Parameters
    ----------
    principal_id : str
        The principal ID of the user or entity being authorized.
    effect : str
        The effect of the policy, either "Allow" or "Deny".
    resource : str
        The resource ARN that the policy applies to.
    context : Optional[Dict[str, Any]], optional
        Additional context to include in the policy, by default None

    Returns
    -------
    Dict[str, Any]
        A dictionary representing the IAM policy for the API Gateway
        authorizer.
    """
    # Generate an IAM policy for the API Gateway authorizer.
    policy = {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": effect,
                    "Resource": resource,
                }
            ],
        },
    }

    # Add context if provided
    if context is not None:
        policy["context"] = context
    return policy
