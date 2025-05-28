# Standard Library
import json
from unittest.mock import MagicMock, patch

# Third-Party
import pytest
from pytest import MonkeyPatch
from botocore.exceptions import ClientError

# Local Folder
from tests.conftest import import_handler


class TestHandler:
    """Tests for the handler.py module."""

    @pytest.fixture
    def handler(self, monkeypatch: MonkeyPatch):
        """Import the handler module."""
        with monkeypatch.context() as m:
            m.setenv("DOCUMENTS_BUCKET_NAME", "test-bucket")
            return import_handler("as-presigned-url-generator")

    @pytest.fixture
    def mock_app(self, handler):
        """Mock the API Gateway resolver."""
        with patch.object(handler, "app") as mock_app:
            mock_event = MagicMock()
            mock_event.json_body = {"file_name": "test.pdf"}
            mock_event.body = '{"file_name": "test.pdf"}'
            mock_app.current_event = mock_event
            mock_app.resolve.return_value = {"statusCode": 200}
            yield mock_app

    @pytest.fixture
    def mock_processor(self, handler, monkeypatch: MonkeyPatch):
        """Mock the processor module."""
        with monkeypatch.context() as m:
            m.setenv("DOCUMENTS_BUCKET_NAME", "test-bucket")
            with patch.object(handler, "processor") as mock_proc:
                mock_proc.s3_client = MagicMock()
                mock_proc.DOCUMENTS_BUCKET_NAME = "test-bucket"
                mock_proc.generate_presigned_url.return_value = (
                    "https://example.com/presigned-url"
                )
                yield mock_proc

    @pytest.fixture
    def mock_logger(self, handler):
        """Mock the logger."""
        with patch.object(handler, "logger") as mock_logger:
            yield mock_logger

    @pytest.fixture
    def mock_presigned_url_request(self, handler):
        """Mock the PresignedUrlRequest dataclass."""
        with patch.object(handler, "PresignedUrlRequest") as mock_request:
            mock_instance = MagicMock()
            mock_instance.file_name = "test.pdf"
            mock_instance.content_type = None
            mock_request.return_value = mock_instance
            yield mock_request

    @pytest.fixture
    def sample_context(self):
        """Sample Lambda context for testing."""
        return MagicMock(
            function_name="test_function",
            memory_limit_in_mb=128,
            aws_request_id="test-request-id",
            invoked_function_arn="arn:aws:lambda:us-east-1:123456789012:function:test_function",
        )

    def test_lambda_handler_success(
        self, handler, mock_app, sample_context, monkeypatch: MonkeyPatch
    ):
        """Test successful lambda_handler execution."""
        with monkeypatch.context() as m:
            m.setenv("DOCUMENTS_BUCKET_NAME", "test-bucket")
            event = {"path": "/srd/upload-url", "httpMethod": "POST"}

            result = handler.lambda_handler(event, sample_context)

            assert result == {"statusCode": 200}
            mock_app.resolve.assert_called_once_with(event, sample_context)

    def test_lambda_handler_exception(
        self, handler, mock_app, sample_context, monkeypatch: MonkeyPatch
    ):
        """Test lambda_handler with an exception during resolution."""
        with monkeypatch.context() as m:
            m.setenv("DOCUMENTS_BUCKET_NAME", "test-bucket")
            mock_app.resolve.side_effect = Exception("Test exception")
            event = {"path": "/srd/upload-url", "httpMethod": "POST"}

            result = handler.lambda_handler(event, sample_context)

            assert result["statusCode"] == 500
            assert (
                json.loads(result["body"])["error"]
                == "An internal server error occurred."
            )

    def test_get_presigned_url_success(
        self,
        handler,
        mock_app,
        mock_processor,
        mock_presigned_url_request,
        monkeypatch: MonkeyPatch,
    ):
        """Test successful presigned URL generation."""
        with monkeypatch.context() as m:
            m.setenv("DOCUMENTS_BUCKET_NAME", "test-bucket")
            result = handler.get_presigned_url()

            assert result["statusCode"] == 200
            response_body = json.loads(result["body"])
            assert (
                response_body["presigned_url"]
                == "https://example.com/presigned-url"
            )
            assert response_body["bucket_name"] == "test-bucket"
            assert response_body["key"] == "test.pdf"
            assert response_body["expires_in"] == 900
            assert response_body["method"] == "PUT"
            mock_processor.generate_presigned_url.assert_called_once_with(
                file_name="test.pdf",
                content_type="application/pdf",  # Default content type
                expiration=900,
            )

    def test_get_presigned_url_with_custom_content_type(
        self,
        handler,
        mock_app,
        mock_processor,
        mock_presigned_url_request,
        monkeypatch: MonkeyPatch,
    ):
        """Test presigned URL generation with custom content type."""
        with monkeypatch.context() as m:
            m.setenv("DOCUMENTS_BUCKET_NAME", "test-bucket")
            mock_presigned_url_request.return_value.content_type = (
                "application/custom"
            )
            mock_app.current_event.json_body = {
                "file_name": "test.pdf",
                "content_type": "application/custom",
            }

            result = handler.get_presigned_url()

            assert result["statusCode"] == 200
            mock_processor.generate_presigned_url.assert_called_once_with(
                file_name="test.pdf",
                content_type="application/custom",
                expiration=900,
            )

    def test_get_presigned_url_no_s3_client(
        self, handler, mock_app, mock_processor, monkeypatch: MonkeyPatch
    ):
        """Test error handling when S3 client is not initialized."""
        with monkeypatch.context() as m:
            m.setenv("DOCUMENTS_BUCKET_NAME", "test-bucket")
            mock_processor.s3_client = None

            result = handler.get_presigned_url()

            assert result["statusCode"] == 500
            error_message = json.loads(result["body"])["error"]
            assert "S3 client not available" in error_message

    def test_get_presigned_url_no_bucket_name(
        self, handler, mock_app, mock_processor, monkeypatch: MonkeyPatch
    ):
        """Test error handling when bucket name is not configured."""
        with monkeypatch.context() as m:
            m.setenv("DOCUMENTS_BUCKET_NAME", "test-bucket")
            mock_processor.DOCUMENTS_BUCKET_NAME = None

            result = handler.get_presigned_url()

            assert result["statusCode"] == 500
            error_message = json.loads(result["body"])["error"]
            assert "Bucket not configured" in error_message

    def test_get_presigned_url_invalid_request_body(
        self, handler, mock_app, monkeypatch: MonkeyPatch
    ):
        """Test error handling with non-dict request body."""
        with monkeypatch.context() as m:
            m.setenv("DOCUMENTS_BUCKET_NAME", "test-bucket")
            mock_app.current_event.json_body = "not-a-dict"

            result = handler.get_presigned_url()

            assert result["statusCode"] == 400
            error_message = json.loads(result["body"])["error"]
            assert "Request body must be a JSON object" in error_message

    def test_get_presigned_url_missing_required_field(
        self, handler, mock_app, mock_processor, monkeypatch: MonkeyPatch
    ):
        """Test error handling with missing file_name field."""
        with monkeypatch.context() as m:
            m.setenv("DOCUMENTS_BUCKET_NAME", "test-bucket")
            mock_app.current_event.json_body = {}

            with patch.object(handler, "PresignedUrlRequest") as mock_request:
                mock_request.side_effect = TypeError(
                    "__init__() missing 1 required positional argument: 'file_name'"
                )

                result = handler.get_presigned_url()

                assert result["statusCode"] == 400
                error_message = json.loads(result["body"])["error"]
                assert "'file_name' is a required field" in error_message

    def test_get_presigned_url_empty_file_name(
        self,
        handler,
        mock_app,
        mock_processor,
        mock_presigned_url_request,
        monkeypatch: MonkeyPatch,
    ):
        """Test validation for empty file_name."""
        with monkeypatch.context() as m:
            m.setenv("DOCUMENTS_BUCKET_NAME", "test-bucket")
            mock_presigned_url_request.return_value.file_name = ""

            result = handler.get_presigned_url()

            assert result["statusCode"] == 400
            error_message = json.loads(result["body"])["error"]
            assert "non-empty string" in error_message

    def test_get_presigned_url_invalid_content_type(
        self,
        handler,
        mock_app,
        mock_processor,
        mock_presigned_url_request,
        monkeypatch: MonkeyPatch,
    ):
        """Test validation for non-string content_type."""
        with monkeypatch.context() as m:
            m.setenv("DOCUMENTS_BUCKET_NAME", "test-bucket")
            mock_presigned_url_request.return_value.file_name = "test.pdf"
            mock_presigned_url_request.return_value.content_type = (
                123  # Not a string
            )

            result = handler.get_presigned_url()

            assert result["statusCode"] == 400
            error_message = json.loads(result["body"])["error"]
            assert "must be a string" in error_message

    def test_get_presigned_url_value_error(
        self, handler, mock_app, mock_processor, monkeypatch: MonkeyPatch
    ):
        """Test error handling with ValueError during request parsing."""
        with monkeypatch.context() as m:
            m.setenv("DOCUMENTS_BUCKET_NAME", "test-bucket")
            with patch.object(handler, "PresignedUrlRequest") as mock_request:
                mock_request.side_effect = ValueError("Invalid value")

                result = handler.get_presigned_url()

                assert result["statusCode"] == 400
                assert "Invalid value" in json.loads(result["body"])["error"]

    def test_get_presigned_url_general_exception_during_parsing(
        self, handler, mock_app, mock_processor, monkeypatch: MonkeyPatch
    ):
        """Test error handling with general exception during request parsing."""
        with monkeypatch.context() as m:
            m.setenv("DOCUMENTS_BUCKET_NAME", "test-bucket")
            with patch.object(handler, "PresignedUrlRequest") as mock_request:
                mock_request.side_effect = Exception("Unexpected error")

                result = handler.get_presigned_url()

                assert result["statusCode"] == 400
                assert (
                    "Error processing request data"
                    in json.loads(result["body"])["error"]
                )

    def test_get_presigned_url_client_error(
        self,
        handler,
        mock_app,
        mock_processor,
        mock_presigned_url_request,
        monkeypatch: MonkeyPatch,
    ):
        """Test error handling with boto3 ClientError."""
        with monkeypatch.context() as m:
            m.setenv("DOCUMENTS_BUCKET_NAME", "test-bucket")
            mock_processor.generate_presigned_url.side_effect = ClientError(
                {"Error": {"Code": "TestException", "Message": "Test error"}},
                "generate_presigned_url",
            )

            result = handler.get_presigned_url()

            assert result["statusCode"] == 500
            assert (
                "Could not generate upload URL"
                in json.loads(result["body"])["error"]
            )

    def test_get_presigned_url_unexpected_error(
        self,
        handler,
        mock_app,
        mock_processor,
        mock_presigned_url_request,
        monkeypatch: MonkeyPatch,
    ):
        """Test error handling with unexpected exception during URL generation."""
        with monkeypatch.context() as m:
            m.setenv("DOCUMENTS_BUCKET_NAME", "test-bucket")
            mock_processor.generate_presigned_url.side_effect = Exception(
                "Unexpected error"
            )

            result = handler.get_presigned_url()

            assert result["statusCode"] == 500
            assert (
                "An unexpected error occurred"
                in json.loads(result["body"])["error"]
            )
