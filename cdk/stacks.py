# Standard Library
from typing import Optional, List

# Third Party
from aws_cdk import (
    Fn,
    Stack,
    Duration,
    CfnOutput,
    aws_s3 as s3,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_route53 as route53,
    aws_dynamodb as dynamodb,
    aws_apigateway as apigw,
    aws_route53_targets as targets,
    aws_s3_notifications as s3n,
    aws_certificatemanager as acm,
)
from constructs import Construct

# Local Modules
from cdk.cognito_stack import CognitoStack
from cdk.custom_constructs import (
    CustomDynamoDBTable,
    CustomIAMPolicyStatement,
    CustomIamRole,
    CustomLambdaFromDockerImage,
    CustomS3Bucket,
    CustomRestApi,
    CustomTokenAuthorizer,
)


class ArcaneScribeStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        stack_suffix: Optional[str] = "",
        **kwargs,
    ) -> None:
        """Arcane Scribe Stack for AWS CDK.

        Parameters
        ----------
        scope : Construct
            The scope in which this construct is defined.
        construct_id : str
            The ID of the construct.
        stack_suffix : Optional[str], optional
            Suffix to append to resource names for this stack, by default ""
        """
        super().__init__(scope, construct_id, **kwargs)

        # region Stack Suffix and Subdomain Configuration
        self.stack_suffix = (stack_suffix if stack_suffix else "").lower()
        self.base_domain_name = self.node.try_get_context("domain_name")
        self.subdomain_part = self.node.try_get_context("subdomain_name")
        self.api_prefix = self.node.try_get_context("api_prefix")
        self.full_domain_name = (
            f"{self.subdomain_part}{self.stack_suffix}.{self.base_domain_name}"
        )
        self.bedrock_embedding_model_id = self.node.try_get_context(
            "bedrock_embedding_model_id"
        )
        self.bedrock_text_generation_model_id = self.node.try_get_context(
            "bedrock_text_generation_model_id"
        )
        self.auth_header_name = self.node.try_get_context(
            "authorizer_header_name"
        )
        self.admin_email = self.node.try_get_context("admin_email")
        self.admin_username = self.node.try_get_context("admin_username")
        self.admin_secret_name = self.node.try_get_context(
            "admin_secret_name"
        )
        # endregion

        # region Import CloudFormation Outputs
        # Import home IP SSM Parameter Name
        imported_home_ip_ssm_param_name = Fn.import_value(
            "home-ip-ssm-param-name"
        )
        # endregion

        # region Cognito User Pool for Authentication
        # Instantiate the self-contained Cognito stack
        cognito_nested_stack = CognitoStack(
            self,
            "ArcaneScribeCognitoNestedStack",
            name="arcane-scribe-cognito",
            admin_email=self.admin_email,
            admin_username=self.admin_username,
            admin_password_secret_name=self.admin_secret_name,
            stack_suffix=self.stack_suffix,
        )

        # Output user pool ID and client ID
        CfnOutput(
            self,
            "UserPoolIdOutput",
            value=cognito_nested_stack.user_pool_id,
            description="Cognito User Pool ID for Arcane Scribe",
            export_name=f"arcane-scribe-user-pool-id{self.stack_suffix}",
        )
        CfnOutput(
            self,
            "UserPoolClientIdOutput",
            value=cognito_nested_stack.user_pool_client_id,
            description="Cognito User Pool Client ID for Arcane Scribe",
            export_name=(
                f"arcane-scribe-user-pool-client-id{self.stack_suffix}"
            ),
        )
        # endregion

        # region S3 Buckets
        # Bucket for storing uploaded PDF documents
        self.documents_bucket = self.create_s3_bucket(
            construct_id="DocumentsBucket",
            name="arcane-scribe-documents",
            versioned=True,
        )

        # Bucket for storing the FAISS index and processed text
        self.vector_store_bucket = self.create_s3_bucket(
            construct_id="VectorStoreBucket",
            name="arcane-scribe-vector-store",
            versioned=True,
        )
        # endregion

        # region DynamoDB Tables
        # This table will store query hashes and their corresponding Bedrock-generated answers
        self.query_cache_table = self.create_dynamodb_table(
            construct_id="RagQueryCacheTable",
            name="arcane-scribe-rag-query-cache",
            partition_key_name="query_hash",
        )
        # endregion

        # region IAM Policies
        # Policy to allow Bedrock model invocation
        self.bedrock_invoke_policy = self.create_iam_policy_statement(
            construct_id="BedrockInvokePolicy",
            actions=["bedrock:InvokeModel"],
            resources=[
                f"arn:aws:bedrock:{self.region}::foundation-model/{self.bedrock_embedding_model_id}",
                f"arn:aws:bedrock:{self.region}::foundation-model/{self.bedrock_text_generation_model_id}",
            ],
        ).statement
        # endregion

        # region Lambda Functions
        # Create backend Lambda role
        backend_lambda_role = self.create_iam_role(
            construct_id="BackendLambdaRole",
            name="arcane-scribe-backend-role",
        ).role

        # Grant permission to get the home IP SSM parameter
        backend_lambda_role.add_to_policy(
            self.create_iam_policy_statement(
                construct_id="BackendLambdaSsmPolicy",
                actions=["ssm:GetParameter"],
                resources=[
                    Fn.join(
                        ":",
                        [
                            "arn",
                            "aws",
                            "ssm",
                            self.region,
                            self.account,
                            f"parameter{imported_home_ip_ssm_param_name}",
                        ]
                    )
                ],
            ).statement
        )

        # Backend API Lambda function
        self.as_backend_lambda = self.create_lambda_function(
            construct_id="ArcaneScribeApiLambda",
            src_folder_path="as-api-backend",
            environment={
                "API_PREFIX": self.api_prefix,
                "DOCUMENTS_BUCKET_NAME": self.documents_bucket.bucket_name,
                "VECTOR_STORE_BUCKET_NAME": (
                    self.vector_store_bucket.bucket_name
                ),
                "BEDROCK_TEXT_GENERATION_MODEL_ID": (
                    self.bedrock_text_generation_model_id
                ),
                "BEDROCK_EMBEDDING_MODEL_ID": (
                    self.bedrock_embedding_model_id
                ),  # For query embedding
                "QUERY_CACHE_TABLE_NAME": self.query_cache_table.table_name,
                "HOME_IP_SSM_PARAMETER_NAME": imported_home_ip_ssm_param_name,
            },
            memory_size=1024,
            timeout=Duration.seconds(30),
            role=backend_lambda_role,
            description="Arcane Scribe API backend Lambda function",
        )

        # Lambda for PDF ingestion and processing
        self.pdf_ingestor_lambda = self.create_lambda_function(
            construct_id="PdfIngestorLambda",
            src_folder_path="as-pdf-ingestor",
            environment={
                "VECTOR_STORE_BUCKET_NAME": (
                    self.vector_store_bucket.bucket_name
                ),
                "DOCUMENTS_BUCKET_NAME": self.documents_bucket.bucket_name,
                "BEDROCK_EMBEDDING_MODEL_ID": self.bedrock_embedding_model_id,
            },
            memory_size=1024,  # More memory for processing PDFs
            timeout=Duration.minutes(5),  # May take longer for large PDFs
            initial_policy=[self.bedrock_invoke_policy],
            description="Ingests PDF documents, extracts text, and stores embeddings in the vector store",
        )

        # Grant S3 permissions for the PDF ingestor Lambda
        self.documents_bucket.grant_read(self.pdf_ingestor_lambda)
        self.vector_store_bucket.grant_read_write(self.pdf_ingestor_lambda)

        # Add S3 event notification to trigger the PDF ingestor Lambda
        self.documents_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,  # Trigger any object creation
            s3n.LambdaDestination(self.pdf_ingestor_lambda),
            s3.NotificationKeyFilter(suffix=".pdf"),  # Only for PDFs
        )

        # Lambda for the custom authorizer
        # Create authorizer Lambda role
        authorizer_lambda_role = self.create_iam_role(
            construct_id="AuthorizerLambdaRole",
            name="arcane-scribe-authorizer-role",
        ).role

        # Grant permission to call AdminInitiateAuth on the user pool
        authorizer_lambda_role.add_to_policy(
            self.create_iam_policy_statement(
                construct_id="AuthorizerLambdaAdminAuthPolicy",
                actions=["cognito-idp:AdminInitiateAuth"],
                resources=[cognito_nested_stack.user_pool.user_pool_arn],
            ).statement
        )

        # Create the authorizer Lambda function
        self.authorizer_lambda = self.create_lambda_function(
            construct_id="ArcaneScribeAuthorizerLambda",
            src_folder_path="as-authorizer",
            environment={
                "USER_POOL_ID": cognito_nested_stack.user_pool.user_pool_id,
                "USER_POOL_CLIENT_ID": (
                    cognito_nested_stack.user_pool_client_id
                ),
            },
            role=authorizer_lambda_role,
            description="Custom authorizer for Arcane Scribe REST API",
        )
        # endregion

        # region API Gateway
        # Create an authorizer for the REST API
        api_authorizer = self.create_token_authorizer(
            construct_id="ArcaneScribeAuthorizer",
            name="arcane-scribe-api-authorizer",
            handler=self.authorizer_lambda,
            identity_source=apigw.IdentitySource.header(
                self.auth_header_name
            ),
        )

        # Create a custom REST API Gateway
        self.rest_api = self.create_rest_api_gateway(
            construct_id="ArcaneScribeRestApi",
            name="arcane-scribe-rest-api",
            allow_methods=["POST", "GET", "OPTIONS"],
            allow_headers=[
                "X-Amz-Date",
                "X-Api-Key",
                "X-Amz-Security-Token",
                "X-Amz-User-Agent",
                "X-File-Name",
                "X-File-Type",
            ],
        ).api

        # Define the Lambda integration for the REST API
        lambda_integration = apigw.LambdaIntegration(
            handler=self.as_backend_lambda,
            proxy=True,  # Enable proxy integration
            allow_test_invoke=(
                self.stack_suffix != ""
            ),  # Allow test invocations in the API Gateway console
        )

        # Get the base resource for the API
        api_base_resource = self.rest_api.root

        # Add the prefix to the API base resource
        if self.api_prefix:
            # Split prefix into parts
            path_parts = self.api_prefix.strip("/").split("/")
            current_resource = api_base_resource

            # Create nested resources for each part of the prefix
            for path_part in path_parts:
                # Check if resource already exists
                existing_resource = current_resource.get_resource(path_part)
                if existing_resource:
                    current_resource = existing_resource
                else:
                    current_resource = current_resource.add_resource(path_part)
            api_base_resource = current_resource  # This is now /api/v1 resource

        # Add specific documentation routes WITHOUT the authorizer
        docs_paths = ["docs", "redoc", "openapi.json"]
        for doc_path in docs_paths:
            doc_resource = api_base_resource.add_resource(doc_path)
            doc_resource.add_method(
                "GET",
                integration=lambda_integration,
                authorizer=None,  # No authorizer for documentation routes
            )

        # Add {proxy+} resource integration to the REST API
        api_proxy_resource = api_base_resource.add_resource("{proxy+}")
        api_proxy_resource.add_method(
            "ANY",
            integration=lambda_integration,
            authorizer=api_authorizer,  # Use the authorizer for all other routes
        )

        # Output the REST API URL
        CfnOutput(
            self,
            "RestApiUrlOutput",
            value=self.rest_api.url,
            description="REST API URL for Arcane Scribe",
            export_name=f"arcane-scribe-rest-api-url{self.stack_suffix}",
        )
        # endregion

        # region Custom Domain Setup for API Gateway
        # 1. Look up existing hosted zone for "thatsmidnight.com"
        hosted_zone = route53.HostedZone.from_lookup(
            self,
            "ArcaneScribeHostedZone",
            domain_name=self.base_domain_name,
        )

        # 2. Create an ACM certificate for subdomain with DNS validation
        api_certificate = acm.Certificate(
            self,
            "ApiCertificate",
            domain_name=self.full_domain_name,
            validation=acm.CertificateValidation.from_dns(hosted_zone),
        )

        # 3. Create the API Gateway Custom Domain Name resource (REST API v1)
        apigw_custom_domain = apigw.DomainName(
            self,
            "ApiCustomDomain",
            domain_name=self.full_domain_name,
            certificate=api_certificate,
            endpoint_type=apigw.EndpointType.REGIONAL,
        )

        # 4. Map REST API to this custom domain
        default_stage = self.rest_api.deployment_stage
        if not default_stage:
            raise ValueError(
                "Default stage could not be found for API mapping. Ensure API has a default stage or specify one."
            )

        # Create base path mapping for REST API
        apigw.BasePathMapping(
            self,
            "ApiBasePathMapping",
            domain_name=apigw_custom_domain,
            rest_api=self.rest_api,
            stage=default_stage,
        )

        # 5. Create the Route 53 Alias Record pointing to the API Gateway custom domain
        route53.ARecord(
            self,
            "ApiAliasRecord",
            zone=hosted_zone,
            record_name=f"{self.subdomain_part}{self.stack_suffix}",
            target=route53.RecordTarget.from_alias(
                targets.ApiGatewayDomain(apigw_custom_domain)
            ),
        )

        # 6. Output the custom API URL
        CfnOutput(
            self,
            "CustomApiUrlOutput",
            value=f"https://{self.full_domain_name}",
            description="Custom API URL for Arcane Scribe",
            export_name=f"arcane-scribe-custom-api-url{self.stack_suffix}",
        )
        # endregion

    def create_s3_bucket(
        self, construct_id: str, name: str, versioned: Optional[bool] = False
    ) -> s3.Bucket:
        """Helper method to create an S3 bucket with a specific name and versioning.

        Parameters
        ----------
        construct_id : str
            The ID of the construct.
        name : str
            The name of the S3 bucket.
        versioned : Optional[bool], optional
            Whether to enable versioning on the bucket, by default False

        Returns
        -------
        s3.Bucket
            The created S3 bucket instance.
        """
        custom_s3_bucket = CustomS3Bucket(
            scope=self,
            id=construct_id,
            name=name,
            stack_suffix=self.stack_suffix,
            versioned=versioned,
        )
        return custom_s3_bucket.bucket

    def create_dynamodb_table(
        self,
        construct_id: str,
        name: str,
        partition_key_name: str,
        partition_key_type: Optional[dynamodb.AttributeType] = None,
        time_to_live_attribute: Optional[str] = None,
    ) -> dynamodb.Table:
        """Helper method to create a DynamoDB table with a specific name and partition key.

        Parameters
        ----------
        construct_id : str
            The ID of the construct.
        name : str
            The name of the DynamoDB table.
        partition_key_name : str
            The name of the partition key for the table.
        partition_key_type : Optional[dynamodb.AttributeType], optional
            The type of the partition key, by default dynamodb.AttributeType.STRING
        time_to_live_attribute : Optional[str], optional
            The attribute name for time to live (TTL) settings, by default None

        Returns
        -------
        dynamodb.Table
            The created DynamoDB table instance.
        """
        custom_dynamodb_table = CustomDynamoDBTable(
            scope=self,
            id=construct_id,
            name=name,
            partition_key=dynamodb.Attribute(
                name=partition_key_name,
                type=partition_key_type or dynamodb.AttributeType.STRING,
            ),
            stack_suffix=self.stack_suffix,
            time_to_live_attribute=time_to_live_attribute or "ttl",
        )
        return custom_dynamodb_table.table

    def create_iam_role(
        self,
        construct_id: str,
        name: str,
        assumed_by: Optional[str] = "lambda.amazonaws.com",
        managed_policies: Optional[List[iam.IManagedPolicy]] = None,
        inline_policies: Optional[List[iam.Policy]] = None,
    ) -> CustomIamRole:
        """Helper method to create an IAM Role.

        Parameters
        ----------
        construct_id : str
            The ID of the construct.
        name : str
            The name of the IAM Role.
        assumed_by : Optional[str], optional
            The principal that can assume this role, by default
            "lambda.amazonaws.com"
        managed_policies : Optional[List[iam.IManagedPolicy]], optional
            List of managed policies to attach to the role, by default None
        inline_policies : Optional[List[iam.Policy]], optional
            List of inline policies to attach to the role, by default None

        Returns
        -------
        CustomIamRole
            The created IAM Role instance.
        """
        custom_iam_role = CustomIamRole(
            scope=self,
            id=construct_id,
            name=name,
            stack_suffix=self.stack_suffix,
            assumed_by=assumed_by,
            managed_policies=managed_policies,
            inline_policies=inline_policies,
        )
        return custom_iam_role

    def create_iam_policy_statement(
        self,
        construct_id: str,
        actions: List[str],
        resources: List[str],
        effect: Optional[iam.Effect] = iam.Effect.ALLOW,
        conditions: Optional[dict] = None,
    ) -> CustomIAMPolicyStatement:
        """Helper method to create an IAM Policy Statement.

        Parameters
        ----------
        construct_id : str
            The ID of the construct.
        actions : List[str]
            List of IAM actions to allow or deny.
        resources : List[str]
            List of resources the actions apply to.
        effect : Optional[iam.Effect], optional
            The effect of the policy statement, by default iam.Effect.ALLOW
        conditions : Optional[dict], optional
            Conditions for the policy statement, by default None

        Returns
        -------
        CustomIAMPolicyStatement
            The created IAM Policy Statement instance.
        """
        custom_iam_policy_statement = CustomIAMPolicyStatement(
            scope=self,
            id=construct_id,
            actions=actions,
            resources=resources,
            effect=effect,
            conditions=conditions or {},
        )
        return custom_iam_policy_statement

    def create_lambda_function(
        self,
        construct_id: str,
        src_folder_path: str,
        environment: Optional[dict] = None,
        memory_size: Optional[int] = 128,
        timeout: Optional[Duration] = Duration.seconds(10),
        initial_policy: Optional[List[iam.PolicyStatement]] = None,
        role: Optional[iam.IRole] = None,
        description: Optional[str] = None,
    ) -> lambda_.Function:
        """Helper method to create a Lambda function.

        Parameters
        ----------
        construct_id : str
            The ID of the construct.
        src_folder_path : str
            The path to the source folder for the Lambda function code.
        environment : Optional[dict], optional
            Environment variables for the Lambda function, by default None
        memory_size : Optional[int], optional
            Memory size for the Lambda function, by default 128
        timeout : Optional[Duration], optional
            Timeout for the Lambda function, by default Duration.seconds(10)
        initial_policy : Optional[List[iam.PolicyStatement]], optional
            Initial IAM policies to attach to the Lambda function, by default None
        role : Optional[iam.IRole], optional
            IAM role to attach to the Lambda function, by default None
        description : Optional[str], optional
            Description for the Lambda function, by default None

        Returns
        -------
        lambda_.Function
            The created Lambda function instance.
        """
        custom_lambda = CustomLambdaFromDockerImage(
            scope=self,
            id=construct_id,
            src_folder_path=src_folder_path,
            stack_suffix=self.stack_suffix,
            environment=environment,
            memory_size=memory_size,
            timeout=timeout,
            initial_policy=initial_policy or [],
            role=role,
            description=description,
        )
        return custom_lambda.function

    def create_rest_api_gateway(
        self,
        construct_id: str,
        name: str,
        allow_methods: Optional[List[str]] = None,
        allow_headers: Optional[List[str]] = None,
        tracing_enabled: Optional[bool] = True,
        data_trace_enabled: Optional[bool] = True,
        metrics_enabled: Optional[bool] = True,
        authorizer: Optional[apigw.IAuthorizer] = None,
    ) -> CustomRestApi:
        """Helper method to create a REST API Gateway.

        Parameters
        ----------
        construct_id : str
            The ID of the construct.
        name : str
            The name of the REST API.
        allow_methods : Optional[List[str]], optional
            List of allowed HTTP methods for CORS, by default None
            (will use apigw.Cors.ALL_METHODS if not provided)
        allow_headers : Optional[List[str]], optional
            List of allowed headers for CORS, by default None
        tracing_enabled : Optional[bool], optional
            Whether to enable tracing for the API, by default True
        data_trace_enabled : Optional[bool], optional
            Whether to enable data tracing for the API, by default True
        metrics_enabled : Optional[bool], optional
            Whether to enable metrics for the API, by default True
        authorizer : Optional[apigw.IAuthorizer], optional
            The authorizer to use for the API, by default None

        Returns
        -------
        CustomRestApi
            The created REST API Gateway instance.
        """
        custom_rest_api = CustomRestApi(
            scope=self,
            id=construct_id,
            name=name,
            stack_suffix=self.stack_suffix,
            description="Cartographers Cloud Kit REST API",
            stage_name=self.stack_suffix.strip("-") or "prod",
            tracing_enabled=tracing_enabled,
            data_trace_enabled=data_trace_enabled,
            metrics_enabled=metrics_enabled,
            allow_methods=allow_methods,
            allow_headers=allow_headers,
            additional_headers=[
                "Content-Type",
                "Authorization",
                self.auth_header_name,
            ],
            authorizer=authorizer,
        )
        return custom_rest_api

    def create_token_authorizer(
        self,
        construct_id: str,
        name: str,
        handler: lambda_.IFunction,
        identity_source: Optional[str] = apigw.IdentitySource.header(
            "Authorization"
        ),
        results_cache_ttl: Optional[Duration] = Duration.seconds(0),
    ) -> apigw.TokenAuthorizer:
        """Helper method to create a Token Authorizer.

        Parameters
        ----------
        construct_id : str
            The ID of the construct.
        name : str
            The name of the authorizer.
        handler : lambda_.IFunction
            The Lambda function to be used as the authorizer.
        identity_source : Optional[str], optional
            The identity source for the authorizer, by default
            apigw.IdentitySource.header("Authorization")
        results_cache_ttl : Optional[Duration], optional
            Results cache TTL for the authorizer, by default Duration.seconds(0)

        Returns
        -------
        apigw.TokenAuthorizer
            The created Token Authorizer instance.
        """
        custom_token_authorizer = CustomTokenAuthorizer(
            scope=self,
            id=construct_id,
            name=name,
            handler=handler,
            stack_suffix=self.stack_suffix,
            identity_source=identity_source,
            results_cache_ttl=results_cache_ttl,
        )
        return custom_token_authorizer.authorizer
