# Standard Library
import json
from typing import Generator, Any, Dict
from unittest.mock import MagicMock, patch

# Third Party
import pytest

# Local Modules
# Assuming conftest.py provides import_handler similar to the guideline
from tests.conftest import import_handler


@pytest.fixture
def handler_module():
    """Import and return the as-rag-query handler module."""
    return import_handler("as-rag-query")


@pytest.fixture
def mock_app(handler_module: MagicMock) -> Generator[MagicMock, None, None]:
    """Mock the APIGatewayHttpResolver instance (app) in the handler."""
    with patch.object(handler_module, "app") as mock_app_instance:
        mock_event = MagicMock()
        # Default valid body for most tests
        mock_event.json_body = {
            "query_text": "What is the meaning of life?",
            "srd_id": "general_knowledge_srd",
            "invoke_generative_llm": False,
        }
        mock_event.body = json.dumps(mock_event.json_body)
        mock_app_instance.current_event = mock_event
        # Default resolve for lambda_handler tests
        mock_app_instance.resolve.return_value = {
            "statusCode": 200,
            "body": json.dumps({"message": "Resolved"}),
        }
        yield mock_app_instance


@pytest.fixture
def mock_processor(
    handler_module: MagicMock,
) -> Generator[MagicMock, None, None]:
    """Mock the processor module used by the handler."""
    with patch.object(handler_module, "processor") as mock_processor_instance:
        # Mock attributes checked by the handler
        mock_processor_instance.s3_client = MagicMock()
        mock_processor_instance.embedding_model = MagicMock()
        mock_processor_instance.bedrock_runtime_client = MagicMock()
        mock_processor_instance.DEFAULT_SRD_ID = "default_srd_id_value"
        # Mock the main function call
        mock_processor_instance.get_answer_from_rag.return_value = {
            "answer": "This is a mock answer from RAG."
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
    context.function_name = "test_rag_query_lambda"
    context.memory_limit_in_mb = 256
    context.aws_request_id = "test-rag-query-request-id"
    context.invoked_function_arn = (
        "arn:aws:lambda:us-east-1:123456789012:function:test_rag_query_lambda"
    )
    return context


class TestRagQueryHandler:
    """Tests for the RAG query handler."""

    # --- Tests for lambda_handler ---

    def test_lambda_handler_success(
        self,
        handler_module: MagicMock,
        mock_app: MagicMock,
        sample_lambda_context: MagicMock,
    ):
        """Test successful execution of lambda_handler."""
        event = {"httpMethod": "POST", "path": "/query"}
        expected_response = {
            "statusCode": 200,
            "body": json.dumps({"message": "Resolved"}),
        }
        mock_app.resolve.return_value = expected_response

        result = handler_module.lambda_handler(event, sample_lambda_context)

        assert result == expected_response
        mock_app.resolve.assert_called_once_with(event, sample_lambda_context)

    def test_lambda_handler_resolve_exception(
        self,
        handler_module: MagicMock,
        mock_app: MagicMock,
        mock_logger: MagicMock,
        sample_lambda_context: MagicMock,
    ):
        """Test lambda_handler when app.resolve raises an exception."""
        event = {"httpMethod": "POST", "path": "/query"}
        mock_app.resolve.side_effect = Exception("Resolver exploded")

        result = handler_module.lambda_handler(event, sample_lambda_context)

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert body["error"] == "An internal server error occurred."
        mock_logger.exception.assert_called_once()

    # --- Tests for query_endpoint ---

    def test_query_endpoint_success_basic(
        self,
        handler_module: MagicMock,
        mock_app: MagicMock,
        mock_processor: MagicMock,
        mock_logger: MagicMock,
    ):
        """Test successful query_endpoint execution with valid inputs."""
        mock_app.current_event.json_body = {
            "query_text": "Test query?",
            "srd_id": "test_srd_123",
            "invoke_generative_llm": True,
        }
        mock_processor.get_answer_from_rag.return_value = {
            "answer": "Success!"
        }

        result = handler_module.query_endpoint()

        assert result["statusCode"] == 200
        assert json.loads(result["body"]) == {"answer": "Success!"}
        mock_processor.get_answer_from_rag.assert_called_once_with(
            query_text="Test query?",
            srd_id="test_srd_123",
            invoke_generative_llm=True,
            use_conversational_style=False,
            generation_config_payload={},
            lambda_logger=mock_logger,
        )

    def test_query_endpoint_processor_not_initialized(
        self,
        handler_module: MagicMock,
        mock_app: MagicMock,
        mock_processor: MagicMock,
        mock_logger: MagicMock,
    ):
        """Test query_endpoint when a processor component is not initialized."""
        mock_processor.s3_client = None  # Simulate S3 client not ready

        result = handler_module.query_endpoint()

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "RAG Processor not initialized" in body["error"]
        mock_logger.error.assert_called_once()

    @pytest.mark.parametrize(
        "body_input,expected_error_message,expected_status_code",
        [
            pytest.param(
                "not_a_dict",
                "Request body must be a JSON object.",
                400,
                id="not_a_dict",
            ),
            pytest.param(
                {"srd_id": "srd1"},
                "Query text is required.",
                400,
                id="missing_query_text",
            ),
            pytest.param(
                {"query_text": "  ", "srd_id": "srd1"},
                "Query text is required.",
                400,
                id="empty_query_text",
            ),
            pytest.param(
                {"query_text": 123, "srd_id": "srd1"},
                "Query text is required.",
                400,
                id="query_text_not_str",
            ),
            pytest.param(
                {"query_text": "Q"},
                "Could not load SRD data for 'dnd5e_srd'.",
                404,
                id="missing_srd_id",
            ),
            pytest.param(
                {"query_text": "Q", "srd_id": "  "},
                "SRD ID is required.",
                400,
                id="empty_srd_id",
            ),
            pytest.param(
                {"query_text": "Q", "srd_id": 123},
                "SRD ID is required.",
                400,
                id="srd_id_not_str",
            ),
        ],
    )
    def test_query_endpoint_invalid_input(
        self,
        handler_module: MagicMock,
        mock_app: MagicMock,
        mock_logger: MagicMock,
        body_input: Any,
        expected_error_message: str,
        expected_status_code: int,
        mocked_bedrock_runtime: MagicMock,
    ):
        """Test query_endpoint with various invalid input scenarios."""
        if isinstance(body_input, str) and body_input == "not_a_dict":
            # Simulate APIGatewayHttpResolver behavior for non-dict json_body
            # For this specific case, we make json_body itself non-dict
            mock_app.current_event.json_body = "not_a_dict_payload"
            # And simulate the ValueError that would be raised by isinstance check
            # by making the .get call fail if it were not a dict.
            # A more direct way is to set it and let the isinstance check fail.
            mock_app.current_event.json_body = "this_is_a_string_not_a_dict"

        else:
            mock_app.current_event.json_body = body_input
        mock_app.current_event.body = json.dumps(body_input)

        result = handler_module.query_endpoint()

        assert result["statusCode"] == expected_status_code
        body = json.loads(result["body"])
        assert body["error"] == expected_error_message
        if "Request body must be a JSON object" in expected_error_message:
            mock_logger.warning.assert_called_once()

    def test_query_endpoint_default_srd_id_and_invoke_llm(
        self,
        handler_module: MagicMock,
        mock_app: MagicMock,
        mock_processor: MagicMock,
        mock_logger: MagicMock,
    ):
        """Test query_endpoint uses default srd_id and invoke_generative_llm."""
        mock_app.current_event.json_body = {"query_text": "Default test?"}
        # srd_id and invoke_generative_llm are missing from body

        handler_module.query_endpoint()

        mock_processor.get_answer_from_rag.assert_called_once_with(
            query_text="Default test?",
            srd_id="default_srd_id_value",
            invoke_generative_llm=False,
            use_conversational_style=False,
            generation_config_payload={},
            lambda_logger=mock_logger,
        )

    def test_query_endpoint_invoke_llm_invalid_type_defaults_to_false(
        self,
        handler_module: MagicMock,
        mock_app: MagicMock,
        mock_processor: MagicMock,
        mock_logger: MagicMock,
    ):
        """Test invoke_generative_llm defaults to False if type is invalid."""
        mock_app.current_event.json_body = {
            "query_text": "Test query",
            "srd_id": "test_srd",
            "invoke_generative_llm": "not_a_boolean",
        }

        handler_module.query_endpoint()
        mock_processor.get_answer_from_rag.assert_called_once_with(
            query_text="Test query",
            srd_id="test_srd",
            invoke_generative_llm=False,
            use_conversational_style=False,
            generation_config_payload={},
            lambda_logger=mock_logger,
        )

    def test_query_endpoint_general_exception(
        self,
        handler_module: MagicMock,
        mock_app: MagicMock,
        mock_logger: MagicMock,
        mocked_bedrock_runtime: MagicMock,
    ):
        """Test query_endpoint with a general exception during processing."""
        mock_app.current_event.json_body = (
            MagicMock()
        )  # Simulate a non-JSON body

        result = handler_module.query_endpoint()
        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert body["error"] == "Request body must be a JSON object."

    @pytest.mark.parametrize(
        "processor_return_value,expected_status_code",
        [
            pytest.param(
                {"error": "Could not load SRD data for some_srd"},
                404,
                id="srd_data_not_found",
            ),
            pytest.param(
                {
                    "error": "Knowledge base components not ready for SRD: some_srd"
                },
                503,
                id="components_not_ready",
            ),
        ],
    )
    def test_query_endpoint_processor_handled_errors(
        self,
        handler_module: MagicMock,
        mock_app: MagicMock,
        mock_processor: MagicMock,
        mock_logger: MagicMock,
        processor_return_value: Dict[str, str],
        expected_status_code: int,
    ):
        """Test query_endpoint handling of specific errors from processor."""
        mock_processor.get_answer_from_rag.return_value = (
            processor_return_value
        )

        result = handler_module.query_endpoint()

        body = json.loads(result["body"])
        assert body == processor_return_value
        assert result["statusCode"] == expected_status_code
        mock_logger.warning.assert_called_once()  # All error results log a warning

    def test_query_endpoint_processor_unhandled_exception(
        self,
        handler_module: MagicMock,
        mock_app: MagicMock,
        mock_processor: MagicMock,
        mock_logger: MagicMock,
    ):
        """Test query_endpoint when processor.get_answer_from_rag raises unhandled exception."""
        mock_processor.get_answer_from_rag.side_effect = Exception(
            "Unexpected RAG explosion"
        )

        result = handler_module.query_endpoint()

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert body["error"] == "Internal server error."
        mock_logger.exception.assert_called_once()

    def test_query_endpoint_name_error_if_json_not_imported(
        self,
        handler_module: MagicMock,
        mock_app: MagicMock,
        mock_processor: MagicMock,  # Keep processor mocked to avoid other errors
    ):
        """
        Test that a NameError for 'json' occurs if not imported in handler.
        This test relies on json.dumps being called in an error path.
        """
        # Trigger an error path that calls json.dumps
        mock_processor.s3_client = (
            None  # Causes 500 error, which calls json.dumps
        )

        # If 'json' is not imported in handler.py, this call will raise NameError
        # We are testing the handler's robustness / completeness of imports.
        with (
            patch.dict(
                handler_module.__dict__,
                {"json": NameError("json is not defined")},
            ),
            pytest.raises(NameError),
        ):
            # Temporarily remove 'json' from the handler's scope if it was auto-imported or mocked in
            if "json" in handler_module.__dict__:
                original_json = handler_module.json
                del handler_module.json
                try:
                    handler_module.query_endpoint()
                finally:
                    handler_module.json = original_json  # Restore
            else:  # if json was never in its dict (e.g. truly not imported)
                with pytest.raises(
                    NameError, match="name 'json' is not defined"
                ):
                    handler_module.query_endpoint()
