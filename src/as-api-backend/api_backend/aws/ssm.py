"""
SSM client wrapper for fetching parameters from AWS Systems Manager
Parameter Store.
"""

# Standard Library
from typing import Dict, List, Optional, Union

# Third Party
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger

# Initialize logger
logger = Logger(service="ssm-client-wrapper")


class SsmClient:
    """A client for interacting with AWS Systems Manager Parameter Store."""

    def __init__(self, region_name: Optional[str] = None) -> None:
        """Initialize the SSM client.

        Parameters
        ----------
        region_name : Optional[str]
            The AWS region name where the SSM Parameter Store is located.
            If not provided, the default region from the AWS configuration
            will be used.
        """
        try:
            self.client = boto3.client("ssm", region_name=region_name)
        except Exception as e:
            logger.error("Failed to create SSM client: %s", e)
            raise

    def get_parameter(
        self, name: str, with_decryption: bool = False
    ) -> Optional[Union[str, Dict[str, str]]]:
        """Fetch a parameter from SSM Parameter Store.

        Parameters
        ----------
        name : str
            The name of the parameter to fetch.
        with_decryption : bool, optional
            Whether to decrypt the parameter value if it is encrypted,
            defaults to False.

        Returns
        -------
        Optional[Union[str, Dict[str, str]]]
            The parameter value or None if not found.
        """
        try:
            response = self.client.get_parameter(
                Name=name, WithDecryption=with_decryption
            )
            return response.get("Parameter", {}).get("Value")
        except ClientError as e:
            logger.error(f"Failed to get parameter {name}: {e}")
            return None

    def get_parameters(
        self, names: List[str], with_decryption: bool = False
    ) -> Dict[str, Optional[str]]:
        """Fetch multiple parameters from SSM Parameter Store.

        Parameters
        ----------
        names : List[str]
            A list of parameter names to fetch.
        with_decryption : bool, optional
            Whether to decrypt the parameter values if they are encrypted,
            defaults to False.

        Returns
        -------
        Dict[str, Optional[str]]
            A dictionary mapping parameter names to their values or None if not found.
        """
        try:
            response = self.client.get_parameters(
                Names=names, WithDecryption=with_decryption
            )
            return {
                param["Name"]: param.get("Value")
                for param in response.get("Parameters", [])
            }
        except ClientError as e:
            logger.error(f"Failed to get parameters {names}: {e}")
            return {name: None for name in names}
