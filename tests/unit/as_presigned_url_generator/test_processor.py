"""Unit tests for the presigned_url_generator.processor module."""

# Standard Library
import os
from unittest.mock import patch, MagicMock

# Third Party
import pytest
from botocore.exceptions import ClientError

# Local
from presigned_url_generator.processor import generate_presigned_url


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Mock environment variables for tests."""
    monkeypatch.setenv("DOCUMENTS_BUCKET_NAME", "test-documents-bucket")


@pytest.fixture
def mock_s3_client():
    """Fixture to mock the Boto3 S3 client."""
    with patch("presigned_url_generator.processor.s3_client") as mock_client:
        yield mock_client


def test_generate_presigned_url_success(mock_s3_client: MagicMock):
    """Test successful generation of a presigned URL."""
    mock_s3_client.generate_presigned_url.return_value = (
        "https://test-documents-bucket.s3.amazonaws.com/test_url"
    )

    file_name = "test_document.pdf"
    srd_id = "SRD123"
    content_type = "application/pdf"
    expiration = 3600

    url = generate_presigned_url(
        file_name=file_name,
        srd_id=srd_id,
        content_type=content_type,
        expiration=expiration,
    )

    assert url == "https://test-documents-bucket.s3.amazonaws.com/test_url"
    mock_s3_client.generate_presigned_url.assert_called_once_with(
        "put_object",
        Params={
            "Bucket": "test-documents-bucket",
            "Key": f"{srd_id}/{file_name}",
            "ContentType": content_type,
        },
        ExpiresIn=expiration,
    )


def test_generate_presigned_url_default_content_type(
    mock_s3_client: MagicMock,
):
    """Test presigned URL generation with default content type."""
    mock_s3_client.generate_presigned_url.return_value = (
        "https://test-documents-bucket.s3.amazonaws.com/default_content_url"
    )

    file_name = "another_doc.txt"
    srd_id = "SRD456"

    url = generate_presigned_url(file_name=file_name, srd_id=srd_id)

    assert (
        url
        == "https://test-documents-bucket.s3.amazonaws.com/default_content_url"
    )
    mock_s3_client.generate_presigned_url.assert_called_once_with(
        "put_object",
        Params={
            "Bucket": "test-documents-bucket",
            "Key": f"{srd_id}/{file_name}",
            "ContentType": "application/pdf",  # Default value
        },
        ExpiresIn=3600,  # Default value
    )


def test_generate_presigned_url_client_error(mock_s3_client: MagicMock):
    """Test presigned URL generation when Boto3 client raises an error."""
    mock_s3_client.generate_presigned_url.side_effect = ClientError(
        {"Error": {"Code": "500", "Message": "Internal Server Error"}},
        "generate_presigned_url",
    )

    with pytest.raises(ClientError):
        generate_presigned_url(file_name="error_doc.pdf", srd_id="SRD789")


@patch.dict(os.environ, {}, clear=True)
def test_generate_presigned_url_missing_env_var():
    """Test behavior when DOCUMENTS_BUCKET_NAME is not set."""
    # Need to reload the module to re-evaluate the global variable
    # This is a bit of a hack, but necessary for this specific test case.
    with pytest.raises(Exception) as exc_info:
        # Attempt to import or reload the module where the check occurs
        # For simplicity, we'll assume the check is at the module level
        # and will be hit upon trying to use the function if not before.
        # If processor.py was already imported, we might need to reload it.
        from importlib import reload
        from presigned_url_generator import processor

        reload(processor)  # Force re-evaluation of module-level code
        processor.generate_presigned_url(file_name="any.pdf", srd_id="any_id")

    assert (
        "Environment variable DOCUMENTS_BUCKET_NAME must be set for S3 operations."
        in str(exc_info.value)
    )
    # Restore environment for other tests
    os.environ["DOCUMENTS_BUCKET_NAME"] = "test-documents-bucket"
    # Reload again to restore the s3_client with the mocked env var for other tests
    from importlib import reload
    from presigned_url_generator import processor

    reload(processor)


@pytest.mark.parametrize(
    "file_name, srd_id, content_type, expiration, expected_key_format",
    [
        (
            "report.docx",
            "CLIENT001",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            1800,
            "CLIENT001/report.docx",
        ),
        (
            "image_archive.zip",
            "PROJECTX",
            "application/zip",
            7200,
            "PROJECTX/image_archive.zip",
        ),
    ],
)
def test_generate_presigned_url_various_inputs(
    mock_s3_client: MagicMock,
    file_name: str,
    srd_id: str,
    content_type: str,
    expiration: int,
    expected_key_format: str,
):
    """Test presigned URL generation with various valid inputs."""
    expected_url = (
        f"https://test-documents-bucket.s3.amazonaws.com/{expected_key_format}"
    )
    mock_s3_client.generate_presigned_url.return_value = expected_url

    url = generate_presigned_url(
        file_name=file_name,
        srd_id=srd_id,
        content_type=content_type,
        expiration=expiration,
    )

    assert url == expected_url
    mock_s3_client.generate_presigned_url.assert_called_once_with(
        "put_object",
        Params={
            "Bucket": "test-documents-bucket",
            "Key": expected_key_format,
            "ContentType": content_type,
        },
        ExpiresIn=expiration,
    )
