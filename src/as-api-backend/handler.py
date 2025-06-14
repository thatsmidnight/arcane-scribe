# Standard Library
from typing import Dict, Any

# Third Party
from mangum import Mangum
from fastapi import FastAPI, Depends
from fastapi.responses import HTMLResponse
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from aws_lambda_powertools import Logger
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.typing import LambdaContext
from api_backend import router, API_PREFIX
from api_backend.dependencies import verify_source_ip

# Initialize a logger
logger = Logger()

# Create a FastAPI application instance
app = FastAPI(
    title="Arcane Scribe API",
    version="0.2.0",
    description="API for Arcane Scribe, a tool for managing and querying knowledge bases.",
    docs_url=f"{API_PREFIX}/docs",
    redoc_url=f"{API_PREFIX}/redoc",
    openapi_url=f"{API_PREFIX}/openapi.json",
    dependencies=[Depends(verify_source_ip)],
)


# region Define custom documentation routes
@app.get(f"{API_PREFIX}/openapi.json", include_in_schema=False)
async def custom_openapi_endpoint() -> Dict[str, Any]:
    """Custom OpenAPI endpoint to return the OpenAPI schema.

    Returns
    -------
    Dict[str, Any]
        The OpenAPI schema for the FastAPI application.
    """
    return get_openapi(title=app.title, version=app.version, routes=app.routes)


@app.get(f"{API_PREFIX}/docs", include_in_schema=False)
async def custom_swagger_ui_html() -> HTMLResponse:
    """Custom Swagger UI HTML endpoint.

    Returns
    -------
    HTMLResponse
        The HTML response for the Swagger UI documentation.
    """
    return get_swagger_ui_html(
        openapi_url=f"{API_PREFIX}/openapi.json",
        title=app.title + " - Swagger UI",
    )


@app.get(f"{API_PREFIX}/redoc", include_in_schema=False)
async def custom_redoc_html() -> HTMLResponse:
    """Custom ReDoc HTML endpoint.

    Returns
    -------
    HTMLResponse
        The HTML response for the ReDoc documentation.
    """
    return get_redoc_html(
        openapi_url=f"{API_PREFIX}/openapi.json", title=app.title + " - ReDoc"
    )


# endregion

# Add the API router to the FastAPI app
app.include_router(router, prefix=API_PREFIX)

# Initialize Mangum handler globally
# This instance will be reused across invocations in a warm Lambda environment.
lambda_asgi_handler = Mangum(app, lifespan="off")


@logger.inject_lambda_context(
    log_event=True, correlation_id_path=correlation_paths.API_GATEWAY_HTTP
)
def lambda_handler(
    event: Dict[str, Any], context: LambdaContext
) -> Dict[str, Any]:
    """Lambda handler function to adapt the FastAPI app for AWS Lambda.

    Parameters
    ----------
    event : Dict[str, Any]
        The event data passed to the Lambda function.
    context : LambdaContext
        The context object containing runtime information.

    Returns
    -------
    Dict[str, Any]
        The response from the FastAPI application.
    """
    # Return the response from the FastAPI application
    return lambda_asgi_handler(event, context)
