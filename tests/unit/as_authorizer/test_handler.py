"""Unit tests for the authorizer handler module."""

# Standard Library
from typing import Generator, Any, Dict
from unittest.mock import MagicMock, patch

# Third Party
import pytest

# Local Modules
from tests.conftest import import_handler


@pytest.fixture
def handler_module():
    """Import and return the as-authorizer handler module."""
    return import_handler("as-authorizer")


@pytest.fixture
def mock_logger(handler_module: MagicMock) -> Generator[MagicMock, None, None]:
    """Mock the logger instance in the handler."""
    with patch.object(handler_module, "logger") as mock_log:
        yield mock_log


@pytest.fixture
def sample_lambda_context() -> MagicMock:
    """Return a sample Lambda context object."""
    context = MagicMock()
    context.function_name = "test_authorizer_lambda"
    context.memory_limit_in_mb = 256
    context.aws_request_id = "test-authorizer-request-id"
    context.invoked_function_arn = (
        "arn:aws:lambda:us-east-1:123456789012:function:test_authorizer"
    )
    return context


@pytest.fixture
def sample_api_gateway_event() -> Dict[str, Any]:
    """Return a sample API Gateway HTTP API event."""
    return {
        "version": "2.0",
        "type": "REQUEST",
        "routeArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/test/GET/resource",
        "identitySource": ["$request.header.Authorization"],
        "routeKey": "GET /resource",
        "rawPath": "/resource",
        "rawQueryString": "",
        "headers": {
            "accept": "application/json",
            "content-length": "0",
            "host": "api.example.com",
            "user-agent": "test-client/1.0",
        },
        "requestContext": {
            "accountId": "123456789012",
            "apiId": "abcdef123",
            "domainName": "api.example.com",
            "http": {
                "method": "GET",
                "path": "/resource",
                "protocol": "HTTP/1.1",
                "sourceIp": "192.168.1.1",
                "userAgent": "test-client/1.0",
            },
            "requestId": "test-request-id",
            "routeKey": "GET /resource",
            "stage": "test",
            "time": "01/Jan/2023:12:00:00 +0000",
            "timeEpoch": 1672574400000,
        },
    }


class TestAuthorizerHandler:
    """Test class for the authorizer handler."""

    def test_lambda_handler_success_authorization(
        self,
        handler_module: MagicMock,
        mock_logger: MagicMock,
        sample_api_gateway_event: Dict[str, Any],
        sample_lambda_context: MagicMock,
    ):
        """Test successful authorization with correct header."""
        with patch.multiple(
            handler_module,
            EXPECTED_HEADER_NAME_CONFIG="x-api-key",
            EXPECTED_HEADER_VALUE="valid-secret-key",
        ):
            # Add the expected header to the event
            sample_api_gateway_event["headers"][
                "x-api-key"
            ] = "valid-secret-key"

            result = handler_module.lambda_handler(
                sample_api_gateway_event, sample_lambda_context
            )

            assert result == {"isAuthorized": True}
            mock_logger.info.assert_any_call(
                "Authorizer invoked.",
                extra={
                    "route_arn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/test/GET/resource"
                },
            )
            mock_logger.info.assert_any_call(
                "Authorization successful for header: x-api-key"
            )

    def test_lambda_handler_success_case_insensitive_header(
        self,
        handler_module: MagicMock,
        mock_logger: MagicMock,
        sample_api_gateway_event: Dict[str, Any],
        sample_lambda_context: MagicMock,
    ):
        """Test successful authorization with case-insensitive header names."""
        with patch.multiple(
            handler_module,
            EXPECTED_HEADER_NAME_CONFIG="x-api-key",
            EXPECTED_HEADER_VALUE="valid-secret-key",
        ):
            # Add header with different case
            sample_api_gateway_event["headers"][
                "X-API-KEY"
            ] = "valid-secret-key"

            result = handler_module.lambda_handler(
                sample_api_gateway_event, sample_lambda_context
            )

            assert result == {"isAuthorized": True}
            mock_logger.info.assert_any_call(
                "Authorization successful for header: x-api-key"
            )

    def test_lambda_handler_denied_missing_header(
        self,
        handler_module: MagicMock,
        mock_logger: MagicMock,
        sample_api_gateway_event: Dict[str, Any],
        sample_lambda_context: MagicMock,
    ):
        """Test authorization denied when required header is missing."""
        with patch.multiple(
            handler_module,
            EXPECTED_HEADER_NAME_CONFIG="x-api-key",
            EXPECTED_HEADER_VALUE="valid-secret-key",
        ):
            # Don't add the expected header

            result = handler_module.lambda_handler(
                sample_api_gateway_event, sample_lambda_context
            )

            assert result == {"isAuthorized": False}
            mock_logger.warning.assert_called_once_with(
                "Authorization denied. Missing required header: x-api-key"
            )

    def test_lambda_handler_denied_invalid_header_value(
        self,
        handler_module: MagicMock,
        mock_logger: MagicMock,
        sample_api_gateway_event: Dict[str, Any],
        sample_lambda_context: MagicMock,
    ):
        """Test authorization denied when header value is invalid."""
        with patch.multiple(
            handler_module,
            EXPECTED_HEADER_NAME_CONFIG="x-api-key",
            EXPECTED_HEADER_VALUE="valid-secret-key",
        ):
            # Add header with wrong value
            sample_api_gateway_event["headers"]["x-api-key"] = "invalid-key"

            result = handler_module.lambda_handler(
                sample_api_gateway_event, sample_lambda_context
            )

            assert result == {"isAuthorized": False}
            mock_logger.warning.assert_called_once_with(
                "Authorization denied. Invalid value for header: x-api-key"
            )

    def test_lambda_handler_denied_missing_env_header_name(
        self,
        handler_module: MagicMock,
        mock_logger: MagicMock,
        sample_api_gateway_event: Dict[str, Any],
        sample_lambda_context: MagicMock,
    ):
        """Test authorization denied when header name env var is missing."""
        with patch.multiple(
            handler_module,
            EXPECTED_HEADER_NAME_CONFIG="",
            EXPECTED_HEADER_VALUE="valid-secret-key",
        ):
            result = handler_module.lambda_handler(
                sample_api_gateway_event, sample_lambda_context
            )

            assert result == {"isAuthorized": False}
            mock_logger.error.assert_called_once_with(
                "Authorizer is misconfigured (missing env vars). Denying request."
            )

    def test_lambda_handler_denied_missing_env_header_value(
        self,
        handler_module: MagicMock,
        mock_logger: MagicMock,
        sample_api_gateway_event: Dict[str, Any],
        sample_lambda_context: MagicMock,
    ):
        """Test authorization denied when header value env var is missing."""
        with patch.multiple(
            handler_module,
            EXPECTED_HEADER_NAME_CONFIG="x-api-key",
            EXPECTED_HEADER_VALUE=None,
        ):
            result = handler_module.lambda_handler(
                sample_api_gateway_event, sample_lambda_context
            )

            assert result == {"isAuthorized": False}
            mock_logger.error.assert_called_once_with(
                "Authorizer is misconfigured (missing env vars). Denying request."
            )

    def test_lambda_handler_empty_headers(
        self,
        handler_module: MagicMock,
        mock_logger: MagicMock,
        sample_lambda_context: MagicMock,
    ):
        """Test authorization with event that has no headers."""
        with patch.multiple(
            handler_module,
            EXPECTED_HEADER_NAME_CONFIG="x-api-key",
            EXPECTED_HEADER_VALUE="valid-secret-key",
        ):
            event_without_headers = {
                "routeArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/test/GET/resource"
            }

            result = handler_module.lambda_handler(
                event_without_headers, sample_lambda_context
            )

            assert result == {"isAuthorized": False}
            mock_logger.warning.assert_called_once_with(
                "Authorization denied. Missing required header: x-api-key"
            )

    def test_lambda_handler_missing_route_arn(
        self,
        handler_module: MagicMock,
        mock_logger: MagicMock,
        sample_lambda_context: MagicMock,
    ):
        """Test authorization with event that has no routeArn."""
        with patch.multiple(
            handler_module,
            EXPECTED_HEADER_NAME_CONFIG="x-api-key",
            EXPECTED_HEADER_VALUE="valid-secret-key",
        ):
            event_without_route_arn = {
                "headers": {"x-api-key": "valid-secret-key"}
            }

            result = handler_module.lambda_handler(
                event_without_route_arn, sample_lambda_context
            )

            assert result == {"isAuthorized": True}
            mock_logger.info.assert_any_call(
                "Authorizer invoked.", extra={"route_arn": None}
            )

    @pytest.mark.parametrize(
        "header_name,header_value,expected_header_config,expected_value,should_authorize",
        [
            ("x-api-key", "secret123", "x-api-key", "secret123", True),
            ("X-API-KEY", "secret123", "x-api-key", "secret123", True),
            (
                "Authorization",
                "Bearer token",
                "authorization",
                "Bearer token",
                True,
            ),
            ("custom-auth", "value", "custom-auth", "value", True),
            ("x-api-key", "wrong", "x-api-key", "secret123", False),
            ("wrong-header", "secret123", "x-api-key", "secret123", False),
        ],
    )
    def test_lambda_handler_parametrized_authorization(
        self,
        handler_module: MagicMock,
        mock_logger: MagicMock,
        sample_api_gateway_event: Dict[str, Any],
        sample_lambda_context: MagicMock,
        header_name: str,
        header_value: str,
        expected_header_config: str,
        expected_value: str,
        should_authorize: bool,
    ):
        """Test various authorization scenarios with parameterized inputs."""
        with patch.multiple(
            handler_module,
            EXPECTED_HEADER_NAME_CONFIG=expected_header_config,
            EXPECTED_HEADER_VALUE=expected_value,
        ):
            sample_api_gateway_event["headers"][header_name] = header_value

            result = handler_module.lambda_handler(
                sample_api_gateway_event, sample_lambda_context
            )

            assert result == {"isAuthorized": should_authorize}

    def test_lambda_handler_logging_context_injection(
        self,
        handler_module: MagicMock,
        sample_api_gateway_event: Dict[str, Any],
        sample_lambda_context: MagicMock,
    ):
        """Test that the lambda_handler has proper logging context injection."""
        with patch.multiple(
            handler_module,
            EXPECTED_HEADER_NAME_CONFIG="x-api-key",
            EXPECTED_HEADER_VALUE="valid-secret-key",
        ):
            # This test verifies the decorators are applied correctly
            handler_func = handler_module.lambda_handler

            # Check if the function has the inject_lambda_context decorator
            assert hasattr(handler_func, "__wrapped__")

            # The actual behavior testing is covered in other tests
            result = handler_module.lambda_handler(
                sample_api_gateway_event, sample_lambda_context
            )

            assert "isAuthorized" in result
            assert isinstance(result["isAuthorized"], bool)
