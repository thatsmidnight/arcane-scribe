"""
This module initializes the API backend for the Arcane Scribe project.

It sets up the FastAPI application, includes the API router, and defines the
Lambda handler for AWS Lambda integration.
"""

# Local Modules
from api_backend.api import router

__all__ = ["router"]
