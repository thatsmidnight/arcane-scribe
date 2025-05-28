# Standard Library
import os

# Third-Party
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

# Initialize Powertools
logger = Logger()

# Retrieve expected header name and value from environment variables
# Header names are case-insensitive in HTTP, so we'll normalize the lookup.
EXPECTED_HEADER_NAME_CONFIG = os.environ.get(
    "EXPECTED_AUTH_HEADER_NAME", ""
).lower()
EXPECTED_HEADER_VALUE = os.environ.get("EXPECTED_AUTH_HEADER_VALUE")

if not EXPECTED_HEADER_NAME_CONFIG or not EXPECTED_HEADER_VALUE:
    # Log this critical misconfiguration. The authorizer will deny all requests.
    logger.error(
        "CRITICAL: Authorizer environment variables EXPECTED_AUTH_HEADER_NAME or EXPECTED_AUTH_HEADER_VALUE are not set."
    )
    # We could raise an error here to make the Lambda fail on cold start if misconfigured,
    # but for an authorizer, simply denying access might be the desired behavior.


@logger.inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """
    Basic Lambda authorizer for API Gateway HTTP API.
    Checks for a custom header and validates its value.

    Parameters
    ----------
    event : dict
        The event payload from API Gateway. For HTTP API Lambda authorizers of type 'REQUEST',
        this contains headers, route information, etc.
    context : LambdaContext
        The Lambda runtime context.

    Returns
    -------
    dict
        An authorization response object.
        {"isAuthorized": True} if authorized,
        {"isAuthorized": False} if not.
        Optionally can include a 'context' dictionary.
    """
    logger.info(
        "Authorizer invoked.", extra={"route_arn": event.get("routeArn")}
    )

    if not EXPECTED_HEADER_NAME_CONFIG or not EXPECTED_HEADER_VALUE:
        logger.error(
            "Authorizer is misconfigured (missing env vars). Denying request."
        )
        return {"isAuthorized": False}

    # HTTP headers are case-insensitive. Normalize incoming header names to lowercase for comparison.
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}

    auth_header_value = headers.get(EXPECTED_HEADER_NAME_CONFIG)

    if auth_header_value and auth_header_value == EXPECTED_HEADER_VALUE:
        logger.info(
            f"Authorization successful for header: {EXPECTED_HEADER_NAME_CONFIG}"
        )
        return {"isAuthorized": True}
    else:
        if not auth_header_value:
            logger.warning(
                f"Authorization denied. Missing required header: {EXPECTED_HEADER_NAME_CONFIG}"
            )
        else:
            logger.warning(
                f"Authorization denied. Invalid value for header: {EXPECTED_HEADER_NAME_CONFIG}"
            )
        return {"isAuthorized": False}
