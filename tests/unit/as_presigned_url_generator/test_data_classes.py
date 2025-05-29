"""Unit tests for the presigned_url_generator.data_classes module."""

# Standard Library
from dataclasses import fields

# Third Party
import pytest

# Local
from presigned_url_generator.data_classes import PresignedUrlRequest


def test_presigned_url_request_creation_valid():
    """Test creating a PresignedUrlRequest with valid data."""
    file_name = "test_document.pdf"
    srd_id = "SRD12345"
    content_type = "application/pdf"

    request_data = PresignedUrlRequest(
        file_name=file_name, srd_id=srd_id, content_type=content_type
    )

    assert request_data.file_name == file_name
    assert request_data.srd_id == srd_id
    assert request_data.content_type == content_type


def test_presigned_url_request_creation_default_content_type():
    """Test creating a PresignedUrlRequest with default content type."""
    file_name = "another_document.docx"
    srd_id = "SRD67890"

    request_data = PresignedUrlRequest(file_name=file_name, srd_id=srd_id)

    assert request_data.file_name == file_name
    assert request_data.srd_id == srd_id
    assert request_data.content_type is None


def test_presigned_url_request_field_metadata():
    """Test the metadata of PresignedUrlRequest fields."""
    expected_metadata = {
        "file_name": {"description": "The name of the file to upload."},
        "srd_id": {"description": "The ID of the SRD document."},
        "content_type": {
            "description": "Optional content type for the file."
        },
    }

    for field_info in fields(PresignedUrlRequest):
        assert field_info.name in expected_metadata
        assert field_info.metadata == expected_metadata[field_info.name]


@pytest.mark.parametrize(
    "file_name, srd_id, content_type",
    [
        ("test.pdf", "SRD001", "application/pdf"),
        ("image.png", "SRD002", "image/png"),
        ("archive.zip", "SRD003", None),
    ],
)
def test_presigned_url_request_multiple_scenarios(
    file_name: str, srd_id: str, content_type: str | None
):
    """Test PresignedUrlRequest with various valid inputs."""
    request = PresignedUrlRequest(
        file_name=file_name, srd_id=srd_id, content_type=content_type
    )
    assert request.file_name == file_name
    assert request.srd_id == srd_id
    assert request.content_type == content_type
