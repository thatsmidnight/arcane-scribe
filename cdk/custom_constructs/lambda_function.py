# Standard Library
import os
from typing import Optional, List, Dict

# Third Party
from aws_cdk import (
    Duration,
    aws_iam as iam,
    aws_lambda as lambda_,
)
from constructs import Construct


class CustomLambdaFromDockerImage(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        src_folder_path: str,
        runtime: lambda_.Runtime = lambda_.Runtime.FROM_IMAGE,
        stack_suffix: Optional[str] = "",
        memory_size: Optional[int] = 512,
        timeout: Optional[Duration] = Duration.seconds(30),
        environment: Optional[Dict[str, str]] = None,
        layers: Optional[List[lambda_.ILayerVersion]] = None,
        initial_policy: Optional[List[iam.PolicyStatement]] = None,
        role: Optional[iam.IRole] = None,
        description: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Custom Lambda Construct for AWS CDK from a Docker image.

        Parameters
        ----------
        scope : Construct
            The scope in which this construct is defined.
        id : str
            The ID of the construct.
        src_folder_path : str
            Path to the source folder containing the Lambda function code.
        runtime : lambda_.Runtime, optional
            The runtime for the Lambda function, by default lambda_.Runtime.FROM_IMAGE
        stack_suffix : Optional[str], optional
            Suffix to append to the Lambda function name, by default ""
        memory_size : Optional[int], optional
            Memory size for the Lambda function in MB, by default 512
        timeout : Optional[Duration], optional
            Timeout for the Lambda function, by default Duration.seconds(30)
        environment : Optional[Dict[str, str]], optional
            Environment variables for the Lambda function, by default None
        layers : Optional[List[lambda_.ILayerVersion]], optional
            List of Lambda layers to attach to the function, by default None
        initial_policy : Optional[List[iam.PolicyStatement]], optional
            Initial IAM policy statements to attach to the Lambda function,
            by default None
        role : Optional[iam.IRole], optional
            IAM role to attach to the Lambda function, by default None
        description : Optional[str], optional
            Description for the Lambda function, by default None
        """
        super().__init__(scope, id, **kwargs)

        # Set variables for Lambda function
        name = os.path.basename(src_folder_path)
        code_path = os.path.join(os.getcwd(), "src", src_folder_path)

        # Append stack suffix to name if provided
        if stack_suffix:
            name = f"{name}{stack_suffix}"

        # Default environment variables for Powertools for AWS Lambda
        powertools_env_vars = {
            "POWERTOOLS_SERVICE_NAME": name,
            "LOG_LEVEL": "INFO",
            "POWERTOOLS_LOGGER_SAMPLE_RATE": "0.1",
            "POWERTOOLS_LOGGER_LOG_EVENT": "true",
            "POWERTOOLS_TRACER_CAPTURE_RESPONSE": "true",
            "POWERTOOLS_TRACER_CAPTURE_ERROR": "true",
        }

        # Merge provided environment variables with Powertools defaults
        if environment:
            powertools_env_vars.update(environment)

        # Build Lambda package using Docker
        self.function = lambda_.Function(
            self,
            f"{name}-function",
            function_name=name,
            runtime=lambda_.Runtime.FROM_IMAGE,
            handler=lambda_.Handler.FROM_IMAGE,
            code=lambda_.Code.from_asset_image(
                directory=code_path,
                # This assumes a Dockerfile is present in the src folder
            ),
            memory_size=memory_size,
            timeout=timeout,
            environment=powertools_env_vars,
            layers=layers,
            initial_policy=initial_policy,
            role=role,
            description=description
            or f"Lambda function for {name}{stack_suffix}",
        )
