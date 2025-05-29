# Standard Library
import os
import sys
import importlib.util
from pathlib import Path
from types import ModuleType

# Third Party
import pytest
import boto3
from moto import mock_aws


@pytest.fixture(scope="session")
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture(scope="function")
def mocked_s3(aws_credentials):
    """
    Mocked S3 service using moto for testing.
    This fixture sets up a mocked S3 service that can be used in tests.
    """
    with mock_aws():
        # Create a mocked S3 client
        s3_client = boto3.client("s3", region_name="us-east-1")
        yield s3_client


@pytest.fixture(scope="function")
def create_documents_bucket(mocked_s3):
    """
    Create a documents test bucket in the mocked S3 service.
    """
    mocked_s3.create_bucket(Bucket="test-documents-bucket")


@pytest.fixture(scope="function")
def create_vector_bucket(mocked_s3):
    """
    Create a vector output test bucket in the mocked S3 service.
    """
    mocked_s3.create_bucket(Bucket="test-vector-bucket")


def pytest_configure(config):
    """
    Configure pytest to add the src directory to sys.path for module imports.
    This allows importing modules from the src directory in tests.
    """
    # Get the absolute path to the project root
    project_root = Path(__file__).parent.parent

    # Add the src directory to sys.path
    src_path = project_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    return config


def import_handler(module_name: str) -> ModuleType:
    """
    Import a handler.py module from a src subdirectory, even when the directory
    name contains hyphens that prevent normal Python imports.

    Parameters
    ----------
    module_name : str
        The name of the module directory under src/
        (e.g., "as-presigned-url-generator")

    Returns
    -------
    ModuleType
        The imported handler module

    Raises
    ------
    ImportError
        If the module cannot be found or imported
    """
    # Get the absolute path to the project root
    project_root = Path(__file__).parent.parent

    # Construct the path to the handler.py file
    handler_path = project_root / "src" / module_name / "handler.py"

    if not handler_path.exists():
        raise ImportError(f"Handler file {handler_path} does not exist")

    # Create a unique module name to avoid conflicts
    safe_module_name = f"test_import_{module_name.replace('-', '_')}_handler"

    # Load the module specification
    spec = importlib.util.spec_from_file_location(
        safe_module_name, handler_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {handler_path}")

    # Create the module
    handler_module = importlib.util.module_from_spec(spec)

    # Save the original sys.path
    original_path = sys.path.copy()

    # Add the module directory to sys.path temporarily so internal imports work
    module_dir = str(handler_path.parent)
    sys.path.insert(0, module_dir)

    # Add parent directory (needed for package imports)
    parent_dir = str(handler_path.parent.parent)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    # Register the module in sys.modules (needed for relative imports)
    sys.modules[safe_module_name] = handler_module

    try:
        # Execute the module code
        spec.loader.exec_module(handler_module)
        return handler_module
    except Exception:
        # Clean up in case of error
        if safe_module_name in sys.modules:
            del sys.modules[safe_module_name]
        raise
    finally:
        # Restore original sys.path
        sys.path = original_path
