# Standard Library
from typing import Optional

# Third Party
from aws_cdk import (
    aws_lambda as lambda_,
    Duration,
    aws_apigateway as apigateway,
)
from constructs import Construct


class CustomTokenAuthorizer(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        name: str,
        handler: lambda_.IFunction,
        identity_source: Optional[str] = apigateway.IdentitySource.header(
            "Authorization"
        ),
        stack_suffix: Optional[str] = "",
        results_cache_ttl: Optional[Duration] = Duration.seconds(0),
        **kwargs,
    ) -> None:
        """Custom Token Authorizer Construct for AWS CDK.

        Parameters
        ----------
        scope : Construct
            The scope in which this construct is defined.
        id : str
            The ID of the construct.
        """
        super().__init__(scope, id, **kwargs)

        # Append stack suffix to name if provided
        self.stack_suffix = stack_suffix or ""
        name = f"{name}{self.stack_suffix}"

        # Create the Token Authorizer
        self.authorizer = apigateway.TokenAuthorizer(
            scope=self,
            id=id,
            authorizer_name=name,
            handler=handler,
            identity_source=identity_source,
            results_cache_ttl=results_cache_ttl or Duration.seconds(0),
        )
