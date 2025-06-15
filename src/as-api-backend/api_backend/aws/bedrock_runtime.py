"""Bedrock runtime client wrapper for AWS Bedrock services."""

# Standard Library
from typing import Dict, Any, Optional

# Third Party
import boto3
from aws_lambda_powertools import Logger
from langchain_aws import (
    BedrockEmbeddings,
    ChatBedrock,
)

# Initialize logger
logger = Logger(service="bedrock-runtime-client-wrapper")


class BedrockRuntimeClient:
    """
    A client wrapper for AWS Bedrock Runtime services.
    """

    def __init__(self, region_name: Optional[str] = None):
        """
        Initialize the BedrockRuntimeClient.

        Parameters
        ----------
        region_name : str
            The AWS region where the Bedrock service is hosted.
        """
        try:
            self.client = boto3.client(
                "bedrock-runtime", region_name=region_name
            )
        except Exception as e:
            logger.error(f"Failed to create Bedrock Runtime client: {e}")
            raise e

    def get_embedding_model(
        self,
        model_id: str,
    ) -> BedrockEmbeddings:
        """
        Get an embedding model from AWS Bedrock.

        Parameters
        ----------
        model_id : str
            The ID of the Bedrock model to use for embeddings.

        Returns
        -------
        BedrockEmbeddings
            An instance of BedrockEmbeddings configured with the specified model.
        """
        return BedrockEmbeddings(client=self.client, model_id=model_id)

    def get_chat_model(
        self,
        model_id: str,
        model_kwargs: Optional[Dict[str, Any]] = None,
    ) -> ChatBedrock:
        """
        Get a chat model from AWS Bedrock.

        Parameters
        ----------
        model_id : str
            The ID of the Bedrock model to use for chat.
        max_retries : int
            The maximum number of retries for the chat model.
        retry_delay : float
            The delay between retries in seconds.

        Returns
        -------
        ChatBedrock
            An instance of ChatBedrock configured with the specified model.
        """
        return ChatBedrock(
            client=self.client,
            model=model_id,
            model_kwargs=model_kwargs,
        )
