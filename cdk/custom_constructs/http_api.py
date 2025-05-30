# Standard Library
from typing import Dict, List, Optional

# Third Party
from aws_cdk import (
    Duration,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_apigatewayv2_authorizers as apigwv2_authorizers,
    aws_lambda as lambda_,
)
from constructs import Construct


class CustomHttpApiGateway(Construct):
    """Custom HTTP API Gateway Construct for AWS CDK.

    This construct creates an HTTP API Gateway with CORS configuration and
    provides methods for adding routes with Lambda integrations.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        name: str,
        stack_suffix: str = "",
        allow_origins: Optional[List[str]] = None,
        allow_methods: Optional[List[apigwv2.CorsHttpMethod]] = None,
        allow_headers: Optional[List[str]] = None,
        max_age: Optional[Duration] = None,
        default_authorizer: Optional[
            apigwv2_authorizers.HttpLambdaAuthorizer
        ] = None,
        **kwargs,
    ) -> None:
        """Initialize the Custom HTTP API Gateway Construct.

        Parameters
        ----------
        scope : Construct
            The scope in which this construct is defined.
        id : str
            The ID of the construct.
        name : str
            The name of the API Gateway.
        stack_suffix : str, optional
            Suffix to append to the API name, by default ""
        allow_origins : Optional[List[str]], optional
            List of allowed origins for CORS, by default ["*"]
        allow_methods : Optional[List[apigwv2.CorsHttpMethod]], optional
            List of allowed HTTP methods for CORS, by default
            [apigwv2.CorsHttpMethod.POST, apigwv2.CorsHttpMethod.GET,
            apigwv2.CorsHttpMethod.OPTIONS]
        allow_headers : Optional[List[str]], optional
            List of allowed headers for CORS, by default
            ["Content-Type", "Authorization
            "X-Amz-Date", "X-Api-Key", "X-Amz-Security-Token",
            "X-Amz-User-Agent"]
        max_age : Optional[Duration], optional
            Maximum age for CORS preflight requests, by default Duration.days(1)
        default_authorizer : Optional[apigwv2_authorizers.HttpLambdaAuthorizer], optional
            Default authorizer for the API Gateway, by default None
        """
        super().__init__(scope, id, **kwargs)

        # Apply stack suffix if provided
        self.name = f"{name}{stack_suffix}" if stack_suffix else name

        # Set default CORS values if not provided
        if allow_origins is None:
            allow_origins = ["*"]

        # Set default methods if not provided
        if allow_methods is None:
            allow_methods = [
                apigwv2.CorsHttpMethod.POST,
                apigwv2.CorsHttpMethod.GET,
                apigwv2.CorsHttpMethod.OPTIONS,
            ]

        # Set default headers if not provided
        if allow_headers is None:
            allow_headers = [
                "Content-Type",
                "Authorization",
                "X-Amz-Date",
                "X-Api-Key",
                "X-Amz-Security-Token",
                "X-Amz-User-Agent",
            ]

        # Set default max age if not provided
        if max_age is None:
            max_age = Duration.days(1)

        # Create CORS configuration
        cors_preflight = apigwv2.CorsPreflightOptions(
            allow_origins=allow_origins,
            allow_methods=allow_methods,
            allow_headers=allow_headers,
            max_age=max_age,
        )

        # Create the HTTP API Gateway
        self.http_api = apigwv2.HttpApi(
            self,
            "DefaultHttpApi",
            api_name=self.name,
            cors_preflight=cors_preflight,
            default_authorizer=default_authorizer,
        )

        # Store integrations and routes for reference
        self.integrations: Dict[
            str, apigwv2_integrations.HttpLambdaIntegration
        ] = {}
        self.routes: Dict[str, apigwv2.HttpRoute] = {}

    def add_lambda_route(
        self,
        path: str,
        lambda_function: lambda_.Function,
        methods: Optional[List[apigwv2.HttpMethod]] = None,
        authorizer: Optional[apigwv2_authorizers.HttpLambdaAuthorizer] = None,
        integration_id: Optional[str] = None,
    ) -> apigwv2.HttpRoute:
        """Add a route with a Lambda integration to the API Gateway.

        Parameters
        ----------
        path : str
            The path for the route (e.g., "/my/resource").
        lambda_function : lambda_.Function
            The Lambda function to integrate with the route.
        methods : Optional[List[apigwv2.HttpMethod]], optional
            List of HTTP methods for the route, by default [apigwv2.HttpMethod.POST]
        authorizer : Optional[apigwv2_authorizers.HttpLambdaAuthorizer], optional
            An authorizer for the route, by default None
        integration_id : Optional[str], optional
            An optional ID for the integration, by default None. If not provided,
            it will be generated based on the Lambda function name and path.
        """
        # Set default methods if not provided
        if methods is None:
            methods = [apigwv2.HttpMethod.GET]

        # Generate integration ID if not provided
        if not integration_id:
            # Create an ID from lambda name and path
            lambda_name = (
                lambda_function.function_name.replace("-", " ")
                .title()
                .replace(" ", "")
            )
            path_part = path.replace("/", "_").strip("_")  # /x/y -> x_y
            integration_id = f"{lambda_name}{path_part}integration"

        # Create Lambda integration
        integration = apigwv2_integrations.HttpLambdaIntegration(
            integration_id,
            handler=lambda_function,
        )

        # Store the integration
        self.integrations[path] = integration

        # Add route to API Gateway
        route_options = {
            "path": path,
            "methods": methods,
            "integration": integration,
        }

        # Add authorizer if provided
        if authorizer:
            route_options["authorizer"] = authorizer

        # Create the route
        route = self.http_api.add_routes(**route_options)

        # Store the route
        self.routes[path] = route[0]  # add_routes returns a list

        return self.routes[path]

    @property
    def api_endpoint(self) -> Optional[str]:
        """Get the API endpoint URL.

        Returns
        -------
        Optional[str]
            The URL of the API endpoint, or an empty string if not set.
        """
        return self.http_api.url or ""

    @property
    def default_stage(self) -> Optional[apigwv2.HttpStage]:
        """Get the default stage of the API.

        Returns
        -------
        Optional[apigwv2.HttpStage]
            The default stage of the API, or None if not set.
        """
        return self.http_api.default_stage
