# Standard Library
from typing import Optional

# Third-Party
from aws_cdk import (
    Stack,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_s3_notifications as s3n,
    aws_s3 as s3,
    Duration,
)
from constructs import Construct

# Local Folder
from cdk.custom_constructs.lamdba_function import CustomLambda
from cdk.custom_constructs.s3_bucket import CustomS3Bucket


class ArcaneScribeStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        stack_suffix: Optional[str] = "",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # region S3 Buckets
        # Bucket for storing uploaded PDF documents
        documents_bucket = CustomS3Bucket(
            self,
            "DocumentsBucket",
            name="arcane-scribe-documents",
            stack_suffix=stack_suffix,
            versioned=True,
        )
        self.documents_bucket = documents_bucket.bucket

        # Bucket for storing the FAISS index and processed text
        vector_store_bucket = CustomS3Bucket(
            self,
            "VectorStoreBucket",
            name="arcane-scribe-vector-store",
            stack_suffix=stack_suffix,
            versioned=True,
        )
        self.vector_store_bucket = vector_store_bucket.bucket
        # endregion

        # region Lambda Functions
        # Lambda for generating pre-signed URLs for document uploads
        presigned_url_lambda = CustomLambda(
            self,
            "PresignedUrlLambda",
            src_folder_path="as-presigned-url-generator",
            stack_suffix=stack_suffix,
            environment={
                "DOCUMENTS_BUCKET_NAME": self.documents_bucket.bucket_name
            },
            memory_size=128,  # Typically small for this task
            timeout=Duration.seconds(10),
        )
        self.presigned_url_lambda = presigned_url_lambda.function

        # Grant permission to the presigned URL Lambda to put objects (via
        # pre-signed URLs) to the documents bucket
        self.documents_bucket.grant_put(self.presigned_url_lambda)
        self.documents_bucket.grant_read(self.presigned_url_lambda)

        # Lambda for PDF ingestion and processing
        pdf_ingestor_lambda = CustomLambda(
            self,
            "PdfIngestorLambda",
            src_folder_path="as-pdf-ingestor",
            stack_suffix=stack_suffix,
            environment={
                "VECTOR_STORE_BUCKET_NAME": (
                    self.vector_store_bucket.bucket_name
                ),
                "DOCUMENTS_BUCKET_NAME": self.documents_bucket.bucket_name,
            },
            memory_size=1024,  # More memory for processing PDFs
            timeout=Duration.minutes(5),  # May take longer for large PDFs
        )
        self.pdf_ingestor_lambda = pdf_ingestor_lambda.function

        # Grant permissions for the PDF ingestor Lambda
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
            stack_suffix=stack_suffix,
            environment={
                "VECTOR_STORE_BUCKET_NAME": (
                    self.vector_store_bucket.bucket_name
                ),
            },
            memory_size=1024,  # More memory for processing queries
            timeout=Duration.seconds(60),
        )
        self.rag_query_lambda = rag_query_lambda.function
        self.vector_store_bucket.grant_read(self.rag_query_lambda)
        # endregion

        # region API Gateway
        # Create an HTTP API Gateway
        http_api = apigwv2.HttpApi(
            self,
            "ArcaneScribeHttpApi",
            api_name=f"ArcaneScribeHttpApi-{stack_suffix}",
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
                ],
                max_age=Duration.days(1),
            ),
        )

        # Integration for pre-signed URL generation
        presigned_url_integration = (
            apigwv2_integrations.HttpLambdaIntegration(
                "PresignedUrlIntegration",
                handler=self.presigned_url_lambda,
            )
        )

        # Add a route for pre-signed URL generation
        http_api.add_routes(
            path="/srd/upload-url",
            methods=[apigwv2.HttpMethod.POST],
            integration=presigned_url_integration,
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
        )
        # endregion
