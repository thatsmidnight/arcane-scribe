# Standard Library
from typing import Optional

# Third Party
from aws_cdk import (
    Stack,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_apigatewayv2_authorizers as apigwv2_authorizers,
    aws_s3_notifications as s3n,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_route53 as route53,
    aws_route53_targets as targets,
    aws_certificatemanager as acm,
    Duration,
    CfnOutput,
)
from constructs import Construct

# Local Modules
from cdk.custom_constructs.s3_bucket import CustomS3Bucket
from cdk.custom_constructs.lamdba_function import CustomLambda
from cdk.custom_constructs.dynamodb_table import CustomDynamoDBTable
from cdk.custom_constructs.iam_policy_statement import (
    CustomIAMPolicyStatement,
)

# Define Bedrock model ARNs or use wildcards for simplicity in a dev environment.
# For production, use specific model ARNs.
# Example: arn:aws:bedrock:REGION::foundation-model/model-id
# You can get these from the Bedrock console or documentation.
# Common model IDs:
# - Embeddings: amazon.titan-embed-text-v1 (or v2, check latest)
# - Text Generation: amazon.titan-text-express-v1, amazon.titan-text-lite-v1
BEDROCK_EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
BEDROCK_TEXT_GENERATION_MODEL_ID = "amazon.titan-text-express-v1"


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
        self.stack_suffix = (
            "-" + stack_suffix if stack_suffix else ""
        ).lower()
        self.base_domain_name = "thatsmidnight.com"
        self.subdomain_part = f"arcane-scribe{self.stack_suffix}"
        self.full_subdomain_name = (
            f"{self.subdomain_part}.{self.base_domain_name}"
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
        documents_bucket = CustomS3Bucket(
            self,
            "DocumentsBucket",
            name="arcane-scribe-documents",
            stack_suffix=self.stack_suffix,
            versioned=True,
        )
        self.documents_bucket = documents_bucket.bucket

        # Bucket for storing the FAISS index and processed text
        vector_store_bucket = CustomS3Bucket(
            self,
            "VectorStoreBucket",
            name="arcane-scribe-vector-store",
            stack_suffix=self.stack_suffix,
            versioned=True,
        )
        self.vector_store_bucket = vector_store_bucket.bucket
        # endregion

        # region DynamoDB Tables
        # This table will store query hashes and their corresponding Bedrock-generated answers
        query_cache_table = CustomDynamoDBTable(
            self,
            "RagQueryCacheTable",
            name="arcane-scribe-rag-query-cache",
            partition_key=dynamodb.Attribute(
                name="query_hash", type=dynamodb.AttributeType.STRING
            ),
            stack_suffix=self.stack_suffix,
            time_to_live_attribute="ttl",
        )
        self.query_cache_table = query_cache_table.table
        # endregion

        # region IAM Policies
        bedrock_invoke_policy = CustomIAMPolicyStatement(
            self,
            "BedrockInvokePolicy",
            actions=["bedrock:InvokeModel"],
            resources=[
                f"arn:aws:bedrock:{self.region}::foundation-model/{BEDROCK_EMBEDDING_MODEL_ID}",
                f"arn:aws:bedrock:{self.region}::foundation-model/{BEDROCK_TEXT_GENERATION_MODEL_ID}",
            ],
        )
        self.bedrock_invoke_policy = bedrock_invoke_policy.statement
        # endregion

        # region Lambda Functions
        # Lambda for generating pre-signed URLs for document uploads
        presigned_url_lambda = CustomLambda(
            self,
            "PresignedUrlLambda",
            src_folder_path="as-presigned-url-generator",
            stack_suffix=self.stack_suffix,
            environment={
                "DOCUMENTS_BUCKET_NAME": self.documents_bucket.bucket_name
            },
            memory_size=128,  # Typically small for this task
            timeout=Duration.seconds(10),
        )
        self.presigned_url_lambda = presigned_url_lambda.function

        # Grant S3 permission to the presigned URL Lambda to put objects (via
        # pre-signed URLs) to the documents bucket
        self.documents_bucket.grant_put(self.presigned_url_lambda)
        self.documents_bucket.grant_read(self.presigned_url_lambda)

        # Lambda for PDF ingestion and processing
        pdf_ingestor_lambda = CustomLambda(
            self,
            "PdfIngestorLambda",
            src_folder_path="as-pdf-ingestor",
            stack_suffix=self.stack_suffix,
            environment={
                "VECTOR_STORE_BUCKET_NAME": (
                    self.vector_store_bucket.bucket_name
                ),
                "DOCUMENTS_BUCKET_NAME": self.documents_bucket.bucket_name,
                "BEDROCK_EMBEDDING_MODEL_ID": BEDROCK_EMBEDDING_MODEL_ID,
            },
            memory_size=1024,  # More memory for processing PDFs
            timeout=Duration.minutes(5),  # May take longer for large PDFs
            initial_policy=[self.bedrock_invoke_policy],
        )
        self.pdf_ingestor_lambda = pdf_ingestor_lambda.function

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
        rag_query_lambda = CustomLambda(
            self,
            "RagQueryLambda",
            src_folder_path="as-rag-query",
            stack_suffix=self.stack_suffix,
            environment={
                "VECTOR_STORE_BUCKET_NAME": (
                    self.vector_store_bucket.bucket_name
                ),
                "BEDROCK_TEXT_GENERATION_MODEL_ID": (
                    BEDROCK_TEXT_GENERATION_MODEL_ID
                ),
                "BEDROCK_EMBEDDING_MODEL_ID": (
                    BEDROCK_EMBEDDING_MODEL_ID
                ),  # For query embedding
                "QUERY_CACHE_TABLE_NAME": self.query_cache_table.table_name,
            },
            memory_size=1024,  # More memory for processing queries
            timeout=Duration.seconds(60),
            initial_policy=[self.bedrock_invoke_policy],
        )
        self.rag_query_lambda = rag_query_lambda.function

        # Grant S3 permissions for the RAG query Lambda
        self.vector_store_bucket.grant_read(self.rag_query_lambda)

        # Grant DynamoDB permissions for the RAG query Lambda
        self.query_cache_table.grant_read_write_data(self.rag_query_lambda)

        authorizer_lambda = CustomLambda(
            self,
            "ArcaneScribeAuthorizerLambda",
            src_folder_path="as-authorizer",
            environment={
                "EXPECTED_AUTH_HEADER_NAME": final_auth_header_name,
                "EXPECTED_AUTH_HEADER_VALUE": auth_secret_value_from_context,
            },
        )
        self.authorizer_lambda = authorizer_lambda.function
        # endregion

        # region API Gateway
        # Create an HTTP API Gateway
        http_api = apigwv2.HttpApi(
            self,
            "ArcaneScribeHttpApi",
            api_name=f"ArcaneScribeHttpApi{self.stack_suffix}",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=["*"],  # Adjust as needed for security
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
            ),
        )

        # Create an authorizer for the HTTP API
        http_lambda_authorizer = apigwv2_authorizers.HttpLambdaAuthorizer(
            "ArcaneScribeHttpLambdaAuthorizer",
            handler=self.authorizer_lambda,
            authorizer_name=f"ArcaneScribeHttpLambdaAuthorizer{self.stack_suffix}",
            response_types=[apigwv2_authorizers.HttpLambdaResponseType.SIMPLE],
            identity_source=[f"$request.header.{final_auth_header_name}"],
        )

        # Integration for pre-signed URL generation
        presigned_url_integration = apigwv2_integrations.HttpLambdaIntegration(
            "PresignedUrlIntegration",
            handler=self.presigned_url_lambda,
        )

        # Add a route for pre-signed URL generation
        http_api.add_routes(
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
        http_api.add_routes(
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
            domain_name=self.full_subdomain_name,
            validation=acm.CertificateValidation.from_dns(hosted_zone),
        )

        # 3. Create the API Gateway Custom Domain Name resource
        apigw_custom_domain = apigwv2.DomainName(
            self,
            "ApiCustomDomain",
            domain_name=self.full_subdomain_name,
            certificate=api_certificate,
        )

        # 4. Map HTTP API to this custom domain
        default_stage = http_api.default_stage
        if not default_stage:
            raise ValueError(
                "Default stage could not be found for API mapping. Ensure API has a default stage or specify one."
            )

        _ = apigwv2.ApiMapping(
            self,
            "ApiMapping",
            api=http_api,
            domain_name=apigw_custom_domain,
            stage=default_stage,  # Use the actual default stage object
        )

        # 5. Create the Route 53 Alias Record pointing to the API Gateway custom domain
        route53.ARecord(
            self,
            "ApiAliasRecord",
            zone=hosted_zone,
            record_name=self.subdomain_part,  # e.g., "arcane-scribe" or "arcane-scribe-dev"
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
            value=f"https://{self.full_subdomain_name}",
            description="Custom API URL for Arcane Scribe",
            export_name=f"ArcaneScribeCustomApiUrl{self.stack_suffix}",
        )
        # endregion
