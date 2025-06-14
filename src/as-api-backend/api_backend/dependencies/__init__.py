"""This module provides dependencies for the API backend.

It includes functions to verify the source IP address of incoming requests
and ensure it matches a whitelisted IP address stored in AWS Systems Manager
(SSM).
"""

# Local Modules
from api_backend.dependencies.dependencies import verify_source_ip

__all__ = [
    "verify_source_ip",
]
