# # Standard Library
# from dataclasses import is_dataclass

# # Local Folder
# from presigned_url_generator.data_classes import PresignedUrlRequest


# class TestDataClasses:
#     """Tests for the data_classes module."""

#     def test_presigned_url_request_is_dataclass(self):
#         """Test that PresignedUrlRequest is a dataclass."""
#         assert is_dataclass(PresignedUrlRequest)

#     def test_presigned_url_request_initialization(self):
#         """Test PresignedUrlRequest initialization with required fields."""
#         request = PresignedUrlRequest(file_name="test.pdf")
#         assert request.file_name == "test.pdf"
#         assert request.content_type is None

#     def test_presigned_url_request_with_content_type(self):
#         """Test PresignedUrlRequest initialization with content_type."""
#         request = PresignedUrlRequest(
#             file_name="test.pdf", content_type="application/pdf"
#         )
#         assert request.file_name == "test.pdf"
#         assert request.content_type == "application/pdf"

#     def test_presigned_url_request_repr(self):
#         """Test the string representation of PresignedUrlRequest."""
#         request = PresignedUrlRequest(
#             file_name="test.pdf", content_type="application/pdf"
#         )
#         repr_str = repr(request)
#         assert "file_name='test.pdf'" in repr_str
#         assert "content_type='application/pdf'" in repr_str
