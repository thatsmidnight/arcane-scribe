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
    aws_apigatewayv2 as apigwv2,
    aws_route53_targets as targets,
    aws_s3_notifications as s3n,
    aws_certificatemanager as acm,
    aws_apigatewayv2_authorizers as apigwv2_authorizers,
    aws_apigatewayv2_integrations as apigwv2_integrations,
)
from constructs import Construct

# Local Modules
from cdk.custom_constructs.iam_role import CustomIamRole
from cdk.custom_constructs.http_api import CustomHttpApiGateway
from cdk.custom_constructs.s3_bucket import CustomS3Bucket
from cdk.custom_constructs.dynamodb_table import CustomDynamoDBTable
from cdk.custom_constructs.lambda_function import CustomLambda
from cdk.custom_constructs.api_custom_domain import ApiCustomDomain
from cdk.custom_constructs.iam_policy_statement import CustomIAMPolicyStatement
from cdk.custom_constructs.http_lambda_authorizer import (
    CustomHttpLambdaAuthorizer,
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
        # endregion

        # region Authorization Header and Secret
        # Retrieve context variables passed from CDK CLI
        auth_header_name_from_context = self.node.try_get_context(
            "authorizer_header_name"
        )
        auth_secret_value_from_context = self.node.try_get_context(
            "authorizer_secret_value"
        )

        if not auth_secret_value_from_context:
            # Fail deployment if the secret value isn't provided, especially for non-local scenarios.
            # For local dev, cdk.json might provide a default, but CI should always pass it.
            raise ValueError(
                "CRITICAL: 'authorizer_secret_value' context variable must be provided for deployment."
            )

        # Use a default if the header name context variable isn't provided.
        # This matches the default in the GitHub Actions workflow.
        final_auth_header_name = (
            auth_header_name_from_context
            if auth_header_name_from_context
            else "X-Custom-Auth-Token"
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
        # Lambda for generating pre-signed URLs for document uploads
        self.presigned_url_lambda = self.create_lambda_function(
            construct_id="PresignedUrlLambda",
            src_folder_path="as-presigned-url-generator",
            environment={
                "DOCUMENTS_BUCKET_NAME": self.documents_bucket.bucket_name
            },
            description="Generates pre-signed S3 URLs for uploading documents",
        )

        # Grant S3 permission to the presigned URL Lambda to put objects (via
        # pre-signed URLs) to the documents bucket
        self.documents_bucket.grant_put(self.presigned_url_lambda)
        self.documents_bucket.grant_read(self.presigned_url_lambda)

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

        # Lambda for RAG queries (using Langchain)
        self.rag_query_lambda = self.create_lambda_function(
            construct_id="RagQueryLambda",
            src_folder_path="as-rag-query",
            environment={
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
            },
            memory_size=1024,  # More memory for processing queries
            timeout=Duration.seconds(60),
            initial_policy=[self.bedrock_invoke_policy],
            description="Handles RAG queries using Langchain, retrieves documents from S3, and generates answers using Bedrock",
        )

        # Grant S3 permissions for the RAG query Lambda
        self.vector_store_bucket.grant_read(self.rag_query_lambda)

        # Grant DynamoDB permissions for the RAG query Lambda
        self.query_cache_table.grant_read_write_data(self.rag_query_lambda)

        # Lambda for the custom authorizer
        self.authorizer_lambda = self.create_lambda_function(
            construct_id="ArcaneScribeAuthorizerLambda",
            src_folder_path="as-authorizer",
            environment={
                "EXPECTED_AUTH_HEADER_NAME": final_auth_header_name,
                "EXPECTED_AUTH_HEADER_VALUE": auth_secret_value_from_context,
            },
            description="Custom authorizer for Arcane Scribe HTTP API",
        )
        # endregion

        # region API Gateway
        # Create an HTTP API Gateway
        self.http_api = self.create_http_api_gateway(
            construct_id="ArcaneScribeHttpApi",
            api_name="arcane-scribe-http-api",
            allow_origins=["*"],
            allow_methods=[
                apigwv2.CorsHttpMethod.POST,
                apigwv2.CorsHttpMethod.GET,
                apigwv2.CorsHttpMethod.OPTIONS,
            ],
            allow_headers=[
                "Content-Type",
                "Authorization",
                "X-Amz-Date",
                "X-Api-Key",
                "X-Amz-Security-Token",
                "X-Amz-User-Agent",
                "X-File-Name",
                "X-File-Type",
                final_auth_header_name,  # Custom auth header
            ],
            max_age=Duration.days(1),
        )

        # Create an authorizer for the HTTP API
        http_lambda_authorizer = self.create_http_lambda_authorizer(
            construct_id="ArcaneScribeHttpLambdaAuthorizer",
            name="arcane-scribe-http-authorizer",
            authorizer_function=self.authorizer_lambda,
            identity_source=[f"$request.header.{final_auth_header_name}"],
        )

        # Integration for pre-signed URL generation
        presigned_url_integration = apigwv2_integrations.HttpLambdaIntegration(
            "PresignedUrlIntegration",
            handler=self.presigned_url_lambda,
        )

        # Add a route for pre-signed URL generation
        self.http_api.http_api.add_routes(
            path="/srd/upload-url",
            methods=[apigwv2.HttpMethod.POST],
            integration=presigned_url_integration,
            authorizer=http_lambda_authorizer,
        )

        # Integration for RAG queries
        rag_query_integration = apigwv2_integrations.HttpLambdaIntegration(
            "RagQueryIntegration",
            handler=self.rag_query_lambda,
        )

        # Add a route for RAG queries
        self.http_api.http_api.add_routes(
            path="/query",
            methods=[apigwv2.HttpMethod.POST],
            integration=rag_query_integration,
            authorizer=http_lambda_authorizer,
        )
        # endregion

        # region Custom Domain Setup for API Gateway
        # 1. Look up existing hosted zone for "thatsmidnight.com"
        hosted_zone = route53.HostedZone.from_lookup(
            self, "ArcaneScribeHostedZone", domain_name=self.base_domain_name
        )

        # 2. Create an ACM certificate for subdomain with DNS validation
        api_certificate = acm.Certificate(
            self,
            "ApiCertificate",
            domain_name=self.full_domain_name,
            validation=acm.CertificateValidation.from_dns(hosted_zone),
        )

        # 3. Create the API Gateway Custom Domain Name resource
        apigw_custom_domain = apigwv2.DomainName(
            self,
            "ApiCustomDomain",
            domain_name=self.full_domain_name,
            certificate=api_certificate,
        )

        # 4. Map HTTP API to this custom domain
        default_stage = self.http_api.http_api.default_stage
        if not default_stage:
            raise ValueError(
                "Default stage could not be found for API mapping. Ensure API has a default stage or specify one."
            )

        _ = apigwv2.ApiMapping(
            self,
            "ApiMapping",
            api=self.http_api.http_api,
            domain_name=apigw_custom_domain,
            stage=default_stage,  # Use the actual default stage object
        )

        # 5. Create the Route 53 Alias Record pointing to the API Gateway custom domain
        route53.ARecord(
            self,
            "ApiAliasRecord",
            zone=hosted_zone,
            record_name=f"{self.subdomain_part}{self.stack_suffix}",  # e.g., "arcane-scribe" or "arcane-scribe-dev"
            target=route53.RecordTarget.from_alias(
                targets.ApiGatewayv2DomainProperties(
                    regional_domain_name=apigw_custom_domain.regional_domain_name,
                    regional_hosted_zone_id=apigw_custom_domain.regional_hosted_zone_id,
                )
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
        description : Optional[str], optional
            Description for the Lambda function, by default None

        Returns
        -------
        lambda_.Function
            The created Lambda function instance.
        """
        custom_lambda = CustomLambda(
            scope=self,
            id=construct_id,
            src_folder_path=src_folder_path,
            stack_suffix=self.stack_suffix,
            environment=environment,
            memory_size=memory_size,
            timeout=timeout,
            initial_policy=initial_policy or [],
            description=description,
        )
        return custom_lambda.function

    def create_http_lambda_authorizer(
        self,
        construct_id: str,
        name: str,
        authorizer_function: lambda_.IFunction,
        response_types: Optional[
            List[apigwv2_authorizers.HttpLambdaResponseType]
        ] = None,
        identity_source: Optional[List[str]] = None,
    ) -> apigwv2_authorizers.HttpLambdaAuthorizer:
        """Helper method to create an HTTP Lambda Authorizer.

        Parameters
        ----------
        construct_id : str
            The ID of the construct.
        name : str
            The name of the authorizer.
        authorizer_function : lambda_.IFunction
            The Lambda function to be used as the authorizer.
        response_types : Optional[List[apigwv2_authorizers.HttpLambdaResponseType]], optional
            List of response types for the authorizer, by default None
        identity_source : Optional[List[str]], optional
            List of identity sources for the authorizer, by default None
        Returns
        -------
        apigwv2_authorizers.HttpLambdaAuthorizer
            The created HTTP Lambda Authorizer instance.
        """
        custom_http_lambda_authorizer = CustomHttpLambdaAuthorizer(
            scope=self,
            id=construct_id,
            name=name,
            authorizer_function=authorizer_function,
            stack_suffix=self.stack_suffix,
            response_types=response_types,
            identity_source=identity_source,
        )
        return custom_http_lambda_authorizer.authorizer

    def create_http_api_gateway(
        self,
        construct_id: str,
        api_name: str,
        allow_origins: Optional[List[str]] = None,
        allow_methods: Optional[List[apigwv2.CorsHttpMethod]] = None,
        allow_headers: Optional[List[str]] = None,
        max_age: Optional[Duration] = None,
        default_authorizer: Optional[
            apigwv2_authorizers.HttpLambdaAuthorizer
        ] = None,
    ) -> CustomHttpApiGateway:
        """Helper method to create an HTTP API Gateway.

        Parameters
        ----------
        construct_id : str
            The ID of the construct.
        api_name : str
            The name of the API Gateway.
        allow_origins : Optional[List[str]], optional
            List of allowed origins for CORS, by default ["*"]
        allow_methods : Optional[List[apigwv2.CorsHttpMethod]], optional
            List of allowed HTTP methods for CORS, by default
            [apigwv2.CorsHttpMethod.POST, apigwv2.CorsHttpMethod.GET,
            apigwv2.CorsHttpMethod.OPTIONS]
        allow_headers : Optional[List[str]], optional
            List of allowed headers for CORS, by default
            ["Content-Type", "Authorization",
            "X-Amz-Date", "X-Api-Key", "X-Amz-Security-Token",
            "X-Amz-User-Agent"]
        max_age : Optional[Duration], optional
            Maximum age for CORS preflight requests, by default Duration.days(1)
        default_authorizer : Optional[apigwv2_authorizers.HttpLambdaAuthorizer], optional
            The default authorizer for the API Gateway, by default None

        Returns
        -------
        CustomHttpApiGateway
            The created HTTP API Gateway instance.
        """
        return CustomHttpApiGateway(
            scope=self,
            id=construct_id,
            name=api_name,
            stack_suffix=self.stack_suffix,
            allow_origins=allow_origins,
            allow_methods=allow_methods,
            allow_headers=allow_headers,
            max_age=max_age,
            default_authorizer=default_authorizer,
        )

    def create_api_custom_domain(
        self, http_api: apigwv2.IHttpApi
    ) -> ApiCustomDomain:
        """Helper method to create an API Gateway custom domain.

        Parameters
        ----------
        http_api : apigwv2.IHttpApi
            The HTTP API to map to the custom domain.

        Returns
        -------
        ApiCustomDomain
            The created API Gateway custom domain instance.
        """
        return ApiCustomDomain(
            scope=self,
            id="ArcaneScribeCustomDomain",
            base_domain_name=self.base_domain_name,
            subdomain_part=self.subdomain_part,
            http_api=http_api,
            stack_suffix=self.stack_suffix,
        )
