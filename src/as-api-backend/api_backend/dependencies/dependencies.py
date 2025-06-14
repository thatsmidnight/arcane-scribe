# Standard Library
import os
from typing import Dict, Any, Optional

# Third Party
import boto3
from botocore.exceptions import ClientError
from fastapi import Request, HTTPException, status
from aws_lambda_powertools import Logger

# Initialize logger
logger = Logger(service="ip-whitelist-dependency")

# Set up in-memory cache for SSM parameter
_ssm_cache: Dict[str, Any] = {"ip_address": None, "last_fetch_time": 0}

# Refresh IP from SSM at most once every 60 seconds
CACHE_TTL_SECONDS = 60

# Get the SSM client from the environment variable
HOME_IP_SSM_PARAMETER_NAME = os.environ.get("HOME_IP_SSM_PARAMETER_NAME")

# Initialize the SSM client as a global variable
ssm_client: Optional[boto3.client] = None


def get_ssm_client() -> boto3.client:
    """Initializes and returns a Boto3 SSM client.

    This function uses a singleton pattern to ensure that the SSM client is
    created only once and reused across calls. It also handles exceptions
    during client initialization, logging the error and re-raising it.

    Returns
    -------
    boto3.client
        A Boto3 SSM client instance.

    Raises
    ------
    Exception
        If the SSM client cannot be initialized, an exception is raised.
    """
    # Use a global variable to store the SSM client
    global ssm_client

    # Check if the SSM client is already initialized
    if ssm_client is None:
        try:
            ssm_client = boto3.client("ssm")
        except Exception as e:
            logger.exception(f"Failed to initialize Boto3 SSM client: {e}")
            raise e
    return ssm_client


def get_allowed_ip_from_ssm() -> Optional[str]:
    """Fetches the allowed IP from SSM, using a short-lived in-memory cache.

    Returns
    -------
    Optional[str]
        The allowed IP address as a string if found, otherwise None.
    """
    try:
        # Get the SSM client
        ssm_client = get_ssm_client()

        # Get the SSM parameter value from the environment variable
        parameter = ssm_client.get_parameter(Name=HOME_IP_SSM_PARAMETER_NAME)
        ip_address = parameter.get("Parameter", {}).get("Value")

        # Return the IP address if it exists
        if ip_address:
            return ip_address
        else:
            # If the parameter value is empty, log an error and return None
            logger.error("SSM parameter value is empty or not found.")
            return None
    except ClientError as e:
        # Handle specific SSM client errors
        logger.exception(
            f"Error fetching IP from SSM parameter '{HOME_IP_SSM_PARAMETER_NAME}': {e}"
        )
    return None


def verify_source_ip(request: Request) -> None:
    """Verifies the source IP of the request against a whitelisted IP from SSM.

    Parameters
    ----------
    request : Request
        The FastAPI request object containing the source IP.

    Raises
    ------
    HTTPException
        If the source IP is not whitelisted or cannot be determined.
        - 403 Forbidden if the IP does not match the whitelist.
        - 503 Service Unavailable if the SSM parameter cannot be fetched.
    """
    # Initialize the source IP to None
    source_ip = None

    # For API Gateway with Lambda Proxy integration (works for both REST and HTTP APIs)
    if "requestContext" in request.scope.get("aws.event", {}):
        source_ip = request.scope["aws.event"]["requestContext"][
            "identity"
        ].get("sourceIp")

    # Fallback for local testing where Uvicorn sets `request.client`
    if not source_ip and request.client:
        source_ip = request.client.host

    # Log the source IP for debugging
    logger.append_keys(source_ip=source_ip)
    logger.info("Executing IP whitelist check.")

    # If source IP is still None, raise an error
    if not source_ip:
        logger.warning("Source IP could not be determined from the request.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not determine client IP address.",
        )

    # Fetch the allowed IP from SSM
    allowed_ip = get_allowed_ip_from_ssm()

    # If allowed IP is None, raise an error
    if not allowed_ip:
        logger.error(
            "Whitelist IP could not be loaded from configuration. Denying access by default."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Service is temporarily unavailable due to a configuration issue."
            ),
        )

    # If the source IP does not match the allowed IP, raise an error
    if source_ip != allowed_ip:
        logger.warning(
            f"Forbidden access for IP: {source_ip}. Whitelisted IP is {allowed_ip}."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access from your IP address is not permitted.",
        )

    # If the source IP matches the allowed IP, log success
    logger.info(
        f"IP address {source_ip} successfully verified against whitelist."
    )
