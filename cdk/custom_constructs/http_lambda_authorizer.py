# Standard Library
from typing import Optional, List

# Third Party
from aws_cdk import (
    aws_apigatewayv2_authorizers as apigwv2_authorizers,
    aws_lambda as lambda_,
    Duration,
)
from constructs import Construct


class CustomHttpLambdaAuthorizer(Construct):
    """Custom HTTP Lambda Authorizer Construct for AWS CDK.

    This construct creates a Lambda authorizer for an HTTP API Gateway.
    It allows you to define the authorizer function and its properties.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        name: str,
        authorizer_function: lambda_.IFunction,
        stack_suffix: str = "",
        response_types: Optional[
            List[apigwv2_authorizers.HttpLambdaResponseType]
        ] = None,
        identity_source: Optional[List[str]] = None,
        **kwargs,
    ) -> None:
        """Initialize the Custom HTTP Lambda Authorizer Construct.

        Parameters
        ----------
        scope : Construct
            The scope in which this construct is defined.
        id : str
            The ID of the construct.
        name : str
            The name of the authorizer.
        authorizer_function : lambda_.IFunction
            The Lambda function to be used as the authorizer.
        stack_suffix : str, optional
            Suffix to append to the authorizer name, by default ""
        response_types : Optional[List[apigwv2_authorizers.HttpLambdaResponseType]], optional
            List of response types for the authorizer,
            by default [apigwv2_authorizers.HttpLambdaResponseType.SIMPLE]
        identity_source : Optional[List[str]], optional
            List of identity sources for the authorizer, by default None
        """
        super().__init__(scope, id, **kwargs)

        self.authorizer = apigwv2_authorizers.HttpLambdaAuthorizer(
            "DefaultHttpLambdaAuthorizer",
            authorizer_name=f"{name}{stack_suffix}",
            handler=authorizer_function,
            response_types=(
                response_types
                or [apigwv2_authorizers.HttpLambdaResponseType.SIMPLE]
            ),
            identity_source=identity_source or [],
            results_cache_ttl=Duration.minutes(60),
        )
