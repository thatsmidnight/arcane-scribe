# Standard Library
from unittest.mock import patch

# Third-Party
import pytest
from pytest import MonkeyPatch
from botocore.exceptions import ClientError


class TestProcessor:
    """Tests for the processor module."""

    @pytest.fixture
    def mock_s3_client(self, monkeypatch: MonkeyPatch):
        """Mock S3 client."""
        with monkeypatch.context() as m:
            m.setenv("DOCUMENTS_BUCKET_NAME", "test-bucket")
            with patch(
                "presigned_url_generator.processor.s3_client"
            ) as mock_client:
                mock_client.generate_presigned_url.return_value = (
                    "https://example.com/presigned-url"
                )
                yield mock_client

    def test_generate_presigned_url(
        self, mock_s3_client, monkeypatch: MonkeyPatch
    ):
        """Test successful presigned URL generation."""
        from presigned_url_generator import processor

        url = processor.generate_presigned_url(
            file_name="test.pdf",
            content_type="application/pdf",
            expiration=900,
        )

        assert url == "https://example.com/presigned-url"
        mock_s3_client.generate_presigned_url.assert_called_once_with(
            "put_object",
            Params={
                "Bucket": "test-bucket",
                "Key": "test.pdf",
                "ContentType": "application/pdf",
            },
            ExpiresIn=900,
        )

    def test_generate_presigned_url_client_error(
        self, mock_s3_client, monkeypatch: MonkeyPatch
    ):
        """Test handling of ClientError during URL generation."""
        from presigned_url_generator import processor

        mock_s3_client.generate_presigned_url.side_effect = ClientError(
            {"Error": {"Code": "TestException", "Message": "Test error"}},
            "generate_presigned_url",
        )

        with pytest.raises(ClientError):
            processor.generate_presigned_url(
                file_name="test.pdf",
                content_type="application/pdf",
                expiration=900,
            )
