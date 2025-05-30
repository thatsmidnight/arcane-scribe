"""Unit tests for the PDF ingestor handler module."""

# Standard Library
from typing import Generator, Any, Dict
from unittest.mock import MagicMock, patch

# Third Party
import pytest
from aws_lambda_powertools.utilities.data_classes import S3Event

# Local Modules
from tests.conftest import import_handler


@pytest.fixture
def handler_module():
    """Import and return the as-pdf-ingestor handler module."""
    return import_handler("as-pdf-ingestor")


@pytest.fixture
def mock_processor(
    handler_module: MagicMock,
) -> Generator[MagicMock, None, None]:
    """Mock the processor module used by the handler."""
    with patch.object(handler_module, "processor") as mock_processor_instance:
        mock_processor_instance.process_s3_object.return_value = {
            "status": "success",
            "message": "PDF processed successfully",
        }
        yield mock_processor_instance


@pytest.fixture
def mock_logger(handler_module: MagicMock) -> Generator[MagicMock, None, None]:
    """Mock the logger instance in the handler."""
    with patch.object(handler_module, "logger") as mock_log:
        yield mock_log


@pytest.fixture
def sample_lambda_context() -> MagicMock:
    """Return a sample Lambda context object."""
    context = MagicMock()
    context.function_name = "test_pdf_ingestor_lambda"
    context.memory_limit_in_mb = 512
    context.aws_request_id = "test-pdf-ingestor-request-id"
    context.invoked_function_arn = (
        "arn:aws:lambda:us-east-1:123456789012:function:test_pdf_ingestor"
    )
    return context


@pytest.fixture
def sample_s3_event_data() -> Dict[str, Any]:
    """Return sample S3 event data."""
    return {
        "Records": [
            {
                "eventVersion": "2.1",
                "eventSource": "aws:s3",
                "awsRegion": "us-east-1",
                "eventTime": "2023-01-01T12:00:00.000Z",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "s3SchemaVersion": "1.0",
                    "configurationId": "test-config",
                    "bucket": {
                        "name": "test-documents-bucket",
                        "ownerIdentity": {"principalId": "test-principal"},
                        "arn": "arn:aws:s3:::test-documents-bucket",
                    },
                    "object": {
                        "key": "documents/test_document.pdf",
                        "size": 1024,
                        "eTag": "test-etag",
                        "versionId": "test-version-id",
                        "sequencer": "test-sequencer",
                    },
                },
            }
        ]
    }


@pytest.fixture
def sample_s3_event(sample_s3_event_data: Dict[str, Any]) -> S3Event:
    """Return a sample S3Event object."""
    return S3Event(sample_s3_event_data)


def test_lambda_handler_success_single_pdf(
    handler_module: MagicMock,
    mock_processor: MagicMock,
    mock_logger: MagicMock,
    sample_s3_event: S3Event,
    sample_lambda_context: MagicMock,
):
    """Test successful processing of a single PDF file."""
    expected_result = {
        "status": "success",
        "message": "PDF processed successfully",
    }
    mock_processor.process_s3_object.return_value = expected_result

    result = handler_module.lambda_handler(sample_s3_event, sample_lambda_context)

    assert result == {"results": [expected_result]}
    mock_processor.process_s3_object.assert_called_once_with(
        "test-documents-bucket", "documents/test_document.pdf", mock_logger
    )
    mock_logger.info.assert_any_call("PDF ingestion Lambda triggered.")
    mock_logger.info.assert_any_call(
        "Processing S3 event record.",
        extra={
            "event_name": "ObjectCreated:Put",
            "event_time": "2023-01-01T12:00:00.000Z",
            "bucket_name": "test-documents-bucket",
            "object_key": "documents/test_document.pdf",
            "object_version_id": "test-version-id",
            "object_size": 1024,
        },
    )
    mock_logger.info.assert_any_call(
        "Successfully processed and vectorized: s3://test-documents-bucket/documents/test_document.pdf"
    )
    mock_logger.info.assert_any_call(
        "PDF ingestion processing loop completed for all records in the event."
    )


def test_lambda_handler_multiple_pdf_files(
    handler_module: MagicMock,
    mock_processor: MagicMock,
    mock_logger: MagicMock,
    sample_lambda_context: MagicMock,
):
    """Test processing multiple PDF files in a single event."""
    event_data = {
        "Records": [
            {
                "eventVersion": "2.1",
                "eventSource": "aws:s3",
                "awsRegion": "us-east-1",
                "eventTime": "2023-01-01T12:00:00.000Z",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "s3SchemaVersion": "1.0",
                    "configurationId": "test-config",
                    "bucket": {
                        "name": "test-documents-bucket",
                        "ownerIdentity": {"principalId": "test-principal"},
                        "arn": "arn:aws:s3:::test-documents-bucket",
                    },
                    "object": {
                        "key": "doc1.pdf",
                        "size": 1024,
                        "eTag": "etag1",
                        "versionId": "version1",
                        "sequencer": "seq1",
                    },
                },
            },
            {
                "eventVersion": "2.1",
                "eventSource": "aws:s3",
                "awsRegion": "us-east-1",
                "eventTime": "2023-01-01T12:05:00.000Z",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "s3SchemaVersion": "1.0",
                    "configurationId": "test-config",
                    "bucket": {
                        "name": "test-documents-bucket",
                        "ownerIdentity": {"principalId": "test-principal"},
                        "arn": "arn:aws:s3:::test-documents-bucket",
                    },
                    "object": {
                        "key": "doc2.pdf",
                        "size": 2048,
                        "eTag": "etag2",
                        "versionId": "version2",
                        "sequencer": "seq2",
                    },
                },
            },
        ]
    }
    s3_event = S3Event(event_data)

    expected_results = [
        {"status": "success", "message": "doc1 processed"},
        {"status": "success", "message": "doc2 processed"},
    ]
    mock_processor.process_s3_object.side_effect = expected_results

    result = handler_module.lambda_handler(s3_event, sample_lambda_context)

    assert result == {"results": expected_results}
    assert mock_processor.process_s3_object.call_count == 2
    mock_processor.process_s3_object.assert_any_call(
        "test-documents-bucket", "doc1.pdf", mock_logger
    )
    mock_processor.process_s3_object.assert_any_call(
        "test-documents-bucket", "doc2.pdf", mock_logger
    )


def test_lambda_handler_skip_non_pdf_files(
    handler_module: MagicMock,
    mock_processor: MagicMock,
    mock_logger: MagicMock,
    sample_lambda_context: MagicMock,
):
    """Test that non-PDF files are skipped."""
    event_data = {
        "Records": [
            {
                "eventVersion": "2.1",
                "eventSource": "aws:s3",
                "awsRegion": "us-east-1",
                "eventTime": "2023-01-01T12:00:00.000Z",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "s3SchemaVersion": "1.0",
                    "configurationId": "test-config",
                    "bucket": {
                        "name": "test-documents-bucket",
                        "ownerIdentity": {"principalId": "test-principal"},
                        "arn": "arn:aws:s3:::test-documents-bucket",
                    },
                    "object": {
                        "key": "document.txt",
                        "size": 512,
                        "eTag": "test-etag",
                        "versionId": "test-version",
                        "sequencer": "test-seq",
                    },
                },
            }
        ]
    }
    s3_event = S3Event(event_data)

    result = handler_module.lambda_handler(s3_event, sample_lambda_context)

    assert result == {"results": []}
    mock_processor.process_s3_object.assert_not_called()
    mock_logger.warning.assert_called_once_with(
        "Object document.txt is not a PDF file. Skipping."
    )


@pytest.mark.parametrize(
    "file_extension,should_process",
    [
        (".pdf", True),
        (".PDF", True),
        (".Pdf", True),
        (".pDf", True),
        (".txt", False),
        (".docx", False),
        (".png", False),
        ("", False),
    ],
)
def test_lambda_handler_file_extension_handling(
    handler_module: MagicMock,
    mock_processor: MagicMock,
    mock_logger: MagicMock,
    sample_lambda_context: MagicMock,
    file_extension: str,
    should_process: bool,
):
    """Test file extension handling for various cases."""
    filename = f"test_document{file_extension}"
    event_data = {
        "Records": [
            {
                "eventVersion": "2.1",
                "eventSource": "aws:s3",
                "awsRegion": "us-east-1",
                "eventTime": "2023-01-01T12:00:00.000Z",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "s3SchemaVersion": "1.0",
                    "configurationId": "test-config",
                    "bucket": {
                        "name": "test-documents-bucket",
                        "ownerIdentity": {"principalId": "test-principal"},
                        "arn": "arn:aws:s3:::test-documents-bucket",
                    },
                    "object": {
                        "key": filename,
                        "size": 1024,
                        "eTag": "test-etag",
                        "versionId": "test-version",
                        "sequencer": "test-seq",
                    },
                },
            }
        ]
    }
    s3_event = S3Event(event_data)

    result = handler_module.lambda_handler(s3_event, sample_lambda_context)

    if should_process:
        mock_processor.process_s3_object.assert_called_once_with(
            "test-documents-bucket", filename, mock_logger
        )
        assert len(result["results"]) == 1
    else:
        mock_processor.process_s3_object.assert_not_called()
        mock_logger.warning.assert_called_once_with(
            f"Object {filename} is not a PDF file. Skipping."
        )
        assert result == {"results": []}


def test_lambda_handler_processor_exception(
    handler_module: MagicMock,
    mock_processor: MagicMock,
    mock_logger: MagicMock,
    sample_s3_event: S3Event,
    sample_lambda_context: MagicMock,
):
    """Test handling of processor exceptions."""
    error_message = "Failed to process PDF document"
    mock_processor.process_s3_object.side_effect = Exception(error_message)

    result = handler_module.lambda_handler(sample_s3_event, sample_lambda_context)

    expected_error_result = {
        "error": error_message,
        "bucket": "test-documents-bucket",
        "key": "documents/test_document.pdf",
    }
    assert result == {"results": [expected_error_result]}
    mock_logger.exception.assert_called_once_with(
        "Failed to process s3://test-documents-bucket/documents/test_document.pdf. Error: Failed to process PDF document"
    )


def test_lambda_handler_mixed_success_and_failure(
    handler_module: MagicMock,
    mock_processor: MagicMock,
    mock_logger: MagicMock,
    sample_lambda_context: MagicMock,
):
    """Test handling of mixed success and failure scenarios."""
    event_data = {
        "Records": [
            {
                "eventVersion": "2.1",
                "eventSource": "aws:s3",
                "awsRegion": "us-east-1",
                "eventTime": "2023-01-01T12:00:00.000Z",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "s3SchemaVersion": "1.0",
                    "configurationId": "test-config",
                    "bucket": {
                        "name": "test-documents-bucket",
                        "ownerIdentity": {"principalId": "test-principal"},
                        "arn": "arn:aws:s3:::test-documents-bucket",
                    },
                    "object": {
                        "key": "success.pdf",
                        "size": 1024,
                        "eTag": "etag1",
                        "versionId": "version1",
                        "sequencer": "seq1",
                    },
                },
            },
            {
                "eventVersion": "2.1",
                "eventSource": "aws:s3",
                "awsRegion": "us-east-1",
                "eventTime": "2023-01-01T12:05:00.000Z",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "s3SchemaVersion": "1.0",
                    "configurationId": "test-config",
                    "bucket": {
                        "name": "test-documents-bucket",
                        "ownerIdentity": {"principalId": "test-principal"},
                        "arn": "arn:aws:s3:::test-documents-bucket",
                    },
                    "object": {
                        "key": "failure.pdf",
                        "size": 2048,
                        "eTag": "etag2",
                        "versionId": "version2",
                        "sequencer": "seq2",
                    },
                },
            },
        ]
    }
    s3_event = S3Event(event_data)

    success_result = {"status": "success", "message": "Processed successfully"}
    error_message = "Processing failed"

    def side_effect(bucket, key, logger):
        if key == "success.pdf":
            return success_result
        else:
            raise Exception(error_message)

    mock_processor.process_s3_object.side_effect = side_effect

    result = handler_module.lambda_handler(s3_event, sample_lambda_context)

    expected_results = [
        success_result,
        {
            "error": error_message,
            "bucket": "test-documents-bucket",
            "key": "failure.pdf",
        },
    ]
    assert result == {"results": expected_results}
    assert mock_processor.process_s3_object.call_count == 2


def test_lambda_handler_empty_event(
    handler_module: MagicMock,
    mock_processor: MagicMock,
    mock_logger: MagicMock,
    sample_lambda_context: MagicMock,
):
    """Test handling of empty S3 event."""
    event_data = {"Records": []}
    s3_event = S3Event(event_data)

    result = handler_module.lambda_handler(s3_event, sample_lambda_context)

    assert result == {"results": []}
    mock_processor.process_s3_object.assert_not_called()
    mock_logger.info.assert_any_call("PDF ingestion Lambda triggered.")
    mock_logger.info.assert_any_call(
        "PDF ingestion processing loop completed for all records in the event."
    )


def test_lambda_handler_url_encoded_object_key(
    handler_module: MagicMock,
    mock_processor: MagicMock,
    mock_logger: MagicMock,
    sample_lambda_context: MagicMock,
):
    """Test handling of URL-encoded object keys."""
    # S3Event automatically decodes URL-encoded keys
    event_data = {
        "Records": [
            {
                "eventVersion": "2.1",
                "eventSource": "aws:s3",
                "awsRegion": "us-east-1",
                "eventTime": "2023-01-01T12:00:00.000Z",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "s3SchemaVersion": "1.0",
                    "configurationId": "test-config",
                    "bucket": {
                        "name": "test-documents-bucket",
                        "ownerIdentity": {"principalId": "test-principal"},
                        "arn": "arn:aws:s3:::test-documents-bucket",
                    },
                    "object": {
                        "key": "documents/file with spaces.pdf",
                        "size": 1024,
                        "eTag": "test-etag",
                        "versionId": "test-version",
                        "sequencer": "test-seq",
                    },
                },
            }
        ]
    }
    s3_event = S3Event(event_data)

    handler_module.lambda_handler(s3_event, sample_lambda_context)

    mock_processor.process_s3_object.assert_called_once_with(
        "test-documents-bucket", "documents/file with spaces.pdf", mock_logger
    )


def test_lambda_handler_logging_context_injection(
    handler_module: MagicMock,
    mock_processor: MagicMock,
    sample_s3_event: S3Event,
    sample_lambda_context: MagicMock,
):
    """Test that the lambda_handler has proper logging context injection."""
    # This test verifies the decorators are applied correctly
    handler_func = handler_module.lambda_handler

    # Check if the function has the inject_lambda_context decorator
    assert hasattr(handler_func, "__wrapped__")

    # The actual behavior testing is covered in other tests
    result = handler_module.lambda_handler(sample_s3_event, sample_lambda_context)

    assert "results" in result
    assert isinstance(result["results"], list)


def test_s3_event_data_class_usage(
    handler_module: MagicMock,
    mock_processor: MagicMock,
    sample_lambda_context: MagicMock,
):
    """Test that the handler properly uses S3Event data class features."""
    event_data = {
        "Records": [
            {
                "eventVersion": "2.1",
                "eventSource": "aws:s3",
                "awsRegion": "us-east-1",
                "eventTime": "2023-01-01T12:00:00.000Z",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "s3SchemaVersion": "1.0",
                    "configurationId": "test-config",
                    "bucket": {
                        "name": "test-bucket",
                        "ownerIdentity": {"principalId": "test-principal"},
                        "arn": "arn:aws:s3:::test-bucket",
                    },
                    "object": {
                        "key": "test.pdf",
                        "size": 1024,
                        "eTag": "test-etag",
                        "versionId": "test-version",
                        "sequencer": "test-seq",
                    },
                },
            }
        ]
    }
    s3_event = S3Event(event_data)

    handler_module.lambda_handler(s3_event, sample_lambda_context)

    # Verify that the handler accesses S3Event properties correctly
    mock_processor.process_s3_object.assert_called_once_with(
        "test-bucket", "test.pdf", handler_module.logger
    )