# Standard Library
from typing import Optional, List

# Third Party
from aws_cdk import aws_apigateway as apigateway
from constructs import Construct


class CustomRestApi(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        name: str,
        stack_suffix: Optional[str] = "",
        description: Optional[str] = None,
        stage_name: Optional[str] = None,
        tracing_enabled: Optional[bool] = False,
        logging_level: Optional[
            apigateway.MethodLoggingLevel
        ] = apigateway.MethodLoggingLevel.INFO,
        data_trace_enabled: Optional[bool] = False,
        metrics_enabled: Optional[bool] = True,
        allow_origins: Optional[List[str]] = None,
        allow_methods: Optional[List[str]] = None,
        allow_headers: Optional[List[str]] = None,
        additional_headers: Optional[List[str]] = None,
        authorizer: Optional[apigateway.IAuthorizer] = None,
        **kwargs,
    ) -> None:
        """Custom REST API Construct for AWS CDK.

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

        # Set additional headers to empty list if not provided
        additional_headers = additional_headers or []

        # Create the REST API
        self.api = apigateway.RestApi(
            scope=self,
            id=id,
            rest_api_name=name,
            description=description,
            deploy_options=apigateway.StageOptions(
                stage_name=stage_name or "prod",
                tracing_enabled=tracing_enabled,
                logging_level=logging_level,
                data_trace_enabled=data_trace_enabled,
                metrics_enabled=metrics_enabled,
            ),
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=allow_origins or apigateway.Cors.ALL_ORIGINS,
                allow_methods=allow_methods or apigateway.Cors.ALL_METHODS,
                allow_headers=allow_headers
                or (apigateway.Cors.DEFAULT_HEADERS + additional_headers),
            ),
            default_method_options=apigateway.MethodOptions(
                authorizer=authorizer
            ),
        )
