# Standard Library
import os
from typing import Optional, List

# Third-Party
from aws_cdk import (
    aws_lambda as _lambda,
    aws_iam as iam,
    Duration,
)
from constructs import Construct


class CustomLambda(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        src_folder_path: str,
        stack_suffix: Optional[str] = "",
        memory_size: Optional[int] = 512,
        timeout: Optional[Duration] = Duration.seconds(30),
        environment: Optional[dict] = None,
        layers: Optional[List[_lambda.ILayerVersion]] = None,
        initial_policy: Optional[List[iam.PolicyStatement]] = None,
        **kwargs,
    ) -> None:
        """Custom Lambda Construct for AWS CDK.

        Parameters
        ----------
        scope : Construct
            The scope in which this construct is defined.
        id : str
            The ID of the construct.
        src_folder_path : str
            Path to the source folder containing the Lambda function code.
        stack_suffix : Optional[str], optional
            Suffix to append to the Lambda function name, by default ""
        memory_size : Optional[int], optional
            Memory size for the Lambda function in MB, by default 512
        timeout : Optional[Duration], optional
            Timeout for the Lambda function, by default Duration.seconds(30)
        environment : Optional[dict], optional
            Environment variables for the Lambda function, by default None
        layers : Optional[List[_lambda.ILayerVersion]], optional
            List of Lambda layers to attach to the function, by default None
        initial_policy : Optional[List[iam.PolicyStatement]], optional
            Initial IAM policy statements to attach to the Lambda function,
            by default None
        """
        super().__init__(scope, id, **kwargs)

        # Set variables for Lambda function
        name = os.path.basename(src_folder_path)
        code_path = os.path.join(os.getcwd(), "src", src_folder_path)

        # Append stack suffix to name if provided
        if stack_suffix:
            name = f"{name}-{stack_suffix}"

        # Default environment variables for Powertools for AWS Lambda
        powertools_env_vars = {
            "POWERTOOLS_SERVICE_NAME": name,
            "LOG_LEVEL": "INFO",
            "POWERTOOLS_LOGGER_SAMPLE_RATE": "0.1",
            "POWERTOOLS_LOGGER_LOG_EVENT": "true",
            "POWERTOOLS_METRICS_NAMESPACE": "ArcaneScribeApp",
            "POWERTOOLS_TRACER_CAPTURE_RESPONSE": "true",
            "POWERTOOLS_TRACER_CAPTURE_ERROR": "true",
        }

        # Merge provided environment variables with Powertools defaults
        if environment:
            powertools_env_vars.update(environment)

        # Build Lambda package using Docker
        self.function = _lambda.Function(
            self,
            "DefaultFunction",
            function_name=name,
            runtime=_lambda.Runtime.FROM_IMAGE,
            handler=_lambda.Handler.FROM_IMAGE,
            code=_lambda.Code.from_asset_image(
                directory=code_path,
                # This assumes a Dockerfile is present in the src folder
            ),
            memory_size=memory_size,
            timeout=timeout,
            environment=powertools_env_vars,
            layers=layers,
            initial_policy=initial_policy,
            tracing=_lambda.Tracing.ACTIVE,
            insights_version=_lambda.LambdaInsightsVersion.VERSION_1_0_229_0,
        )
