# Standard Library
import os
from unittest.mock import patch, MagicMock, call

# Third Party
import pytest
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger
from langchain_community.vectorstores import FAISS
from langchain_aws import ChatBedrock
from langchain.chains.retrieval_qa.base import RetrievalQA
from langchain_core.documents import Document

# Local Modules
from rag_query_processor import processor


@pytest.fixture(autouse=True)
def reset_module_globals_and_env(monkeypatch):
    """Resets mutable global states and sets default env vars."""
    # Clear cache and reset global instances
    processor.faiss_index_cache.clear()

    # Use patch for module-level variable
    with patch.object(processor, "_default_llm_instance", None):
        # Set environment variables with monkeypatch
        monkeypatch.setenv("VECTOR_STORE_BUCKET_NAME", "test-vector-bucket")
        monkeypatch.setenv("QUERY_CACHE_TABLE_NAME", "test-query-cache-table")
        monkeypatch.setenv(
            "BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v1"
        )
        monkeypatch.setenv(
            "BEDROCK_TEXT_GENERATION_MODEL_ID", "amazon.titan-text-express-v1"
        )

        # Use patch for module-level attributes derived from env vars
        with patch.multiple(
            processor,
            BEDROCK_EMBEDDING_MODEL_ID=os.environ.get(
                "BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v1"
            ),
            BEDROCK_TEXT_GENERATION_MODEL_ID=os.environ.get(
                "BEDROCK_TEXT_GENERATION_MODEL_ID",
                "amazon.titan-text-express-v1",
            ),
            VECTOR_STORE_BUCKET_NAME=os.environ.get(
                "VECTOR_STORE_BUCKET_NAME"
            ),
            QUERY_CACHE_TABLE_NAME=os.environ.get("QUERY_CACHE_TABLE_NAME"),
        ):
            yield


@pytest.fixture
def mock_lambda_logger():
    """Provides a MagicMock for the lambda_logger argument."""
    return MagicMock(spec=Logger)


@pytest.fixture
def mock_boto3_module_clients():
    """Mocks Boto3 clients at the processor module level."""
    with (
        patch.object(processor, "s3_client") as s3_client_mock,
        patch.object(processor, "dynamodb_client") as dynamodb_client_mock,
        patch.object(
            processor, "bedrock_runtime_client"
        ) as bedrock_runtime_client_mock,
        patch.object(processor, "embedding_model") as embedding_model_mock,
        patch.object(processor, "logger") as logger_mock,
    ):
        yield {
            "s3": s3_client_mock,
            "dynamodb": dynamodb_client_mock,
            "bedrock_runtime": bedrock_runtime_client_mock,
            "embedding_model": embedding_model_mock,
            "processor_logger": logger_mock,
        }


@pytest.fixture
def setup_vector_bucket(mocked_s3):
    """Setup the vector store bucket for processor tests."""
    mocked_s3.create_bucket(Bucket="test-vector-bucket")
    return mocked_s3


@pytest.fixture
def setup_cache_table(mocked_dynamodb):
    """Setup the query cache table for processor tests."""
    mocked_dynamodb.create_table(
        TableName="test-query-cache-table",
        KeySchema=[{"AttributeName": "query_hash_srd_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "query_hash_srd_id", "AttributeType": "S"}
        ],
        ProvisionedThroughput={
            "ReadCapacityUnits": 1,
            "WriteCapacityUnits": 1,
        },
    )
    return mocked_dynamodb


# --- Tests for get_llm_instance ---
class TestGetLlmInstance:
    @pytest.fixture
    def mock_chat_bedrock_class(self):
        with patch(
            "rag_query_processor.processor.ChatBedrock", autospec=True
        ) as mock_class:
            mock_instance = mock_class.return_value
            mock_instance._llm_type = "mocked_chat_bedrock"
            yield mock_class

    def test_get_llm_instance_with_full_config(
        self, mock_chat_bedrock_class, mock_boto3_module_clients
    ):
        generation_config = {
            "temperature": 0.5,
            "topP": 0.8,
            "maxTokenCount": 500,
            "stopSequences": ["\nUser:"],
        }
        expected_model_kwargs = {
            "temperature": 0.5,
            "topP": 0.8,
            "maxTokenCount": 500,
            "stopSequences": ["\nUser:"],
        }

        llm = processor.get_llm_instance(generation_config)

        assert llm is mock_chat_bedrock_class.return_value
        mock_chat_bedrock_class.assert_called_once_with(
            client=mock_boto3_module_clients["bedrock_runtime"],
            model=processor.BEDROCK_TEXT_GENERATION_MODEL_ID,
            model_kwargs=expected_model_kwargs,
        )
        with patch.object(processor, "_default_llm_instance", None):
            assert processor._default_llm_instance is None

    def test_get_llm_instance_empty_config_uses_default_creation_flow(
        self, mock_chat_bedrock_class, mock_boto3_module_clients
    ):
        llm1 = processor.get_llm_instance({})
        assert llm1 is mock_chat_bedrock_class.return_value
        mock_chat_bedrock_class.assert_called_once_with(
            client=mock_boto3_module_clients["bedrock_runtime"],
            model=processor.BEDROCK_TEXT_GENERATION_MODEL_ID,
            model_kwargs={},
        )
        with patch.object(processor, "_default_llm_instance", None):
            assert processor._default_llm_instance is None

    def test_get_llm_instance_primary_chat_bedrock_init_fails_returns_default(
        self, mock_chat_bedrock_class, mock_boto3_module_clients
    ):
        # Simulate the first ChatBedrock call (dynamic config) failing
        chat_bedrock_side_effects = [
            Exception("Dynamic init failed"),  # First call fails
            MagicMock(spec=ChatBedrock),  # Second call (default) succeeds
        ]
        mock_chat_bedrock_class.side_effect = chat_bedrock_side_effects

        with patch.object(processor, "_default_llm_instance", None):
            llm = processor.get_llm_instance({"temperature": 0.1})

        assert llm is chat_bedrock_side_effects[1]
        with patch.object(processor, "_default_llm_instance", llm):
            assert processor._default_llm_instance is llm

        mock_boto3_module_clients[
            "processor_logger"
        ].exception.assert_called_with(
            "Failed to initialize dynamic ChatBedrock instance: Dynamic init failed"
        )
        assert mock_chat_bedrock_class.call_count == 2

        first_call_args = mock_chat_bedrock_class.call_args_list[0]
        second_call_args = mock_chat_bedrock_class.call_args_list[1]

        assert first_call_args[1]["model_kwargs"] == {"temperature": 0.1}
        assert second_call_args[1]["model_kwargs"] == {
            "temperature": 0.1,
            "maxTokenCount": 1024,
        }

    def test_get_llm_instance_both_dynamic_and_default_init_fail(
        self, mock_chat_bedrock_class, mock_boto3_module_clients
    ):
        # Simulate both ChatBedrock calls failing
        mock_chat_bedrock_class.side_effect = [
            Exception("Dynamic init failed"),
            Exception("Default init failed"),
        ]

        with patch.object(processor, "_default_llm_instance", None):
            # Expect the second exception ("Default init failed") to propagate
            with pytest.raises(Exception, match="Default init failed"):
                processor.get_llm_instance({"temperature": 0.1})

        mock_boto3_module_clients[
            "processor_logger"
        ].exception.assert_called_with(
            "Failed to initialize dynamic ChatBedrock instance: Dynamic init failed"
        )
        with patch.object(processor, "_default_llm_instance", None):
            assert processor._default_llm_instance is None
        assert mock_chat_bedrock_class.call_count == 2

    def test_get_llm_instance_no_bedrock_client_propagates_error(
        self, mock_chat_bedrock_class, mock_boto3_module_clients
    ):
        # Simulate ChatBedrock raising an error if client is None
        mock_chat_bedrock_class.side_effect = ValueError("Client is None")

        with patch.object(processor, "bedrock_runtime_client", None):
            with pytest.raises(ValueError, match="Client is None"):
                processor.get_llm_instance({})  # Empty config

        # ChatBedrock is called twice: once for dynamic, once for fallback.
        assert mock_chat_bedrock_class.call_count == 2
        mock_boto3_module_clients[
            "processor_logger"
        ].exception.assert_called_once()

        logged_exception_message = mock_boto3_module_clients[
            "processor_logger"
        ].exception.call_args[0][0]
        assert (
            "Failed to initialize dynamic ChatBedrock instance: Client is None"
            in logged_exception_message
        )

    @pytest.mark.parametrize(
        "param,invalid_value,expected_warning_part",
        [
            pytest.param(
                "temperature",
                "not_a_float",
                "Invalid temperature value",
                id="temp_not_float",
            ),
            pytest.param(
                "temperature",
                -0.1,
                "Invalid temperature value",
                id="temp_negative",
            ),
            pytest.param(
                "temperature",
                1.1,
                "Invalid temperature value",
                id="temp_above_one",
            ),
            pytest.param(
                "topP",
                "not_a_float",
                "Invalid topP value",
                id="topP_not_float",
            ),
            pytest.param(
                "topP", -0.1, "Invalid topP value", id="topP_negative"
            ),
            pytest.param(
                "topP", 1.1, "Invalid topP value", id="topP_above_one"
            ),
            pytest.param(
                "maxTokenCount",
                "not_an_int",
                "Invalid maxTokenCount",
                id="maxTokenCount_not_int",
            ),
            pytest.param(
                "maxTokenCount",
                -10,
                "Invalid maxTokenCount",
                id="maxTokenCount_negative",
            ),
            pytest.param(
                "maxTokenCount",
                9000,
                "Invalid maxTokenCount",
                id="maxTokenCount_above_limit",
            ),
            pytest.param(
                "stopSequences",
                "not_a_list",
                "Invalid stopSequences",
                id="stopSequences_not_list",
            ),
            pytest.param(
                "stopSequences",
                [123],
                "Invalid stopSequences",
                id="stopSequences_not_str",
            ),
        ],
    )
    def test_get_llm_instance_invalid_params_warns_and_omits_param(
        self,
        param,
        invalid_value,
        expected_warning_part,
        mock_chat_bedrock_class,
        mock_boto3_module_clients,
    ):
        generation_config = {param: invalid_value}
        # Ensure the primary ChatBedrock call doesn't fail for other reasons
        mock_chat_bedrock_class.side_effect = None
        mock_chat_bedrock_class.return_value = MagicMock(spec=ChatBedrock)

        processor.get_llm_instance(generation_config)

        found_warning = False
        for call_args in mock_boto3_module_clients[
            "processor_logger"
        ].warning.call_args_list:
            if expected_warning_part in call_args[0][0]:
                found_warning = True
                break
        assert (
            found_warning
        ), f"Expected warning '{expected_warning_part}' not found."

        mock_chat_bedrock_class.assert_called_once()
        called_kwargs = mock_chat_bedrock_class.call_args[1].get(
            "model_kwargs", {}
        )
        assert param not in called_kwargs  # Invalid param should be omitted


# --- Tests for _load_faiss_index_from_s3 ---
@pytest.fixture
def mock_faiss_class():
    with patch(
        "rag_query_processor.processor.FAISS", autospec=True
    ) as mock_class:
        yield mock_class


@pytest.fixture
def mock_os_module():
    with patch("rag_query_processor.processor.os", autospec=True) as m:
        # Default os.path.exists to False unless overridden in a test
        m.path.exists.return_value = False
        yield m


@pytest.fixture
def mock_shutil_module():
    with patch("rag_query_processor.processor.shutil", autospec=True) as m:
        yield m


class TestLoadFaissIndexFromS3:
    @pytest.fixture(autouse=True)
    def setup_method_mocks(
        self,
        mock_faiss_class,
        mock_os_module,
        mock_shutil_module,
        mock_boto3_module_clients,
    ):
        self.mock_faiss_class_instance = mock_faiss_class
        self.mock_faiss_load_local_return = MagicMock(spec=FAISS)
        self.mock_faiss_class_instance.load_local.return_value = (
            self.mock_faiss_load_local_return
        )
        self.os_mock = mock_os_module
        self.shutil_mock = mock_shutil_module
        self.s3_client = mock_boto3_module_clients["s3"]
        self.embedding_model = mock_boto3_module_clients["embedding_model"]
        self.processor_logger = mock_boto3_module_clients["processor_logger"]

        with patch.object(processor, "embedding_model", self.embedding_model):
            yield

    def test_cache_hit(self, mock_lambda_logger):
        srd_id = "cached_srd"
        cached_index = MagicMock(spec=FAISS)
        processor.faiss_index_cache[srd_id] = cached_index

        result = processor._load_faiss_index_from_s3(
            srd_id, mock_lambda_logger
        )
        assert result is cached_index
        self.s3_client.download_file.assert_not_called()
        mock_lambda_logger.info.assert_any_call(
            f"FAISS index for '{srd_id}' found in cache."
        )

    def test_cache_miss_success(self, mock_lambda_logger):
        srd_id = "new_srd"
        # os.path.exists: False (initial check), True (finally block)
        self.os_mock.path.exists.side_effect = [False, True]

        result = processor._load_faiss_index_from_s3(
            srd_id, mock_lambda_logger
        )

        assert result is self.mock_faiss_load_local_return

        safe_srd_id = "".join(
            c if c.isalnum() or c in ["-", "_"] else "_" for c in srd_id
        )
        expected_local_dir = f"/tmp/{safe_srd_id}_faiss_index_query"

        self.os_mock.path.exists.assert_any_call(expected_local_dir)
        self.os_mock.makedirs.assert_called_once_with(
            expected_local_dir, exist_ok=True
        )

        # shutil.rmtree should not be called for pre-cleanup
        # Call for final cleanup
        self.shutil_mock.rmtree.assert_called_once_with(expected_local_dir)

        expected_s3_key_prefix = f"{srd_id}/faiss_index"
        expected_dl_calls = [
            call(
                "test-vector-bucket",
                f"{expected_s3_key_prefix}/index.faiss",
                self.os_mock.path.join(expected_local_dir, "index.faiss"),
            ),
            call(
                "test-vector-bucket",
                f"{expected_s3_key_prefix}/index.pkl",
                self.os_mock.path.join(expected_local_dir, "index.pkl"),
            ),
        ]
        self.s3_client.download_file.assert_has_calls(
            expected_dl_calls, any_order=True
        )
        assert self.s3_client.download_file.call_count == 2

        self.mock_faiss_class_instance.load_local.assert_called_once_with(
            folder_path=expected_local_dir,
            embeddings=self.embedding_model,
            allow_dangerous_deserialization=True,
        )
        assert processor.faiss_index_cache[srd_id] is result

    def test_cache_miss_success_local_dir_exists_initially(
        self, mock_lambda_logger
    ):
        srd_id = "existing_dir_srd"
        # os.path.exists: True (initial check), True (finally block)
        self.os_mock.path.exists.return_value = (
            True  # Always True for this test
        )

        processor._load_faiss_index_from_s3(srd_id, mock_lambda_logger)

        safe_srd_id = "".join(
            c if c.isalnum() or c in ["-", "_"] else "_" for c in srd_id
        )
        expected_local_dir = f"/tmp/{safe_srd_id}_faiss_index_query"

        expected_rmtree_calls = [
            call(expected_local_dir),  # Pre-cleanup
            call(expected_local_dir),  # Final cleanup
        ]
        self.shutil_mock.rmtree.assert_has_calls(expected_rmtree_calls)
        assert self.shutil_mock.rmtree.call_count == 2
        self.os_mock.makedirs.assert_called_once_with(
            expected_local_dir, exist_ok=True
        )

    def test_cache_eviction(self, mock_lambda_logger):
        with patch.object(processor, "MAX_CACHE_SIZE", 1):
            # os.path.exists: [False, True] for first load, [False, True] for second
            self.os_mock.path.exists.side_effect = [False, True, False, True]

            processor._load_faiss_index_from_s3(
                "srd1", mock_lambda_logger
            )  # First load
            self.mock_faiss_class_instance.load_local.reset_mock()  # Reset for second load

            new_faiss_instance = MagicMock(spec=FAISS)
            self.mock_faiss_class_instance.load_local.return_value = (
                new_faiss_instance
            )

            processor._load_faiss_index_from_s3(
                "srd2", mock_lambda_logger
            )  # Second load, causes eviction

            assert "srd2" in processor.faiss_index_cache
            assert "srd1" not in processor.faiss_index_cache
            assert processor.faiss_index_cache["srd2"] is new_faiss_instance

    @pytest.mark.parametrize(
        "missing_attr,log_msg_part,is_processor_attr",
        [
            (
                "s3_client",
                "S3 client or Bedrock embedding model not initialized.",
                True,
            ),
            (
                "embedding_model",
                "S3 client or Bedrock embedding model not initialized.",
                True,
            ),
            (
                "VECTOR_STORE_BUCKET_NAME",
                "VECTOR_STORE_BUCKET_NAME not configured.",
                True,
            ),
        ],
    )
    def test_missing_config_or_clients(
        self,
        mock_lambda_logger,
        missing_attr,
        log_msg_part,
        is_processor_attr,
    ):
        with patch.object(processor, missing_attr, None):
            result = processor._load_faiss_index_from_s3(
                "any_srd", mock_lambda_logger
            )
            assert result is None
            mock_lambda_logger.error.assert_called_with(log_msg_part)

    def test_s3_download_fails(self, mock_lambda_logger):
        self.s3_client.download_file.side_effect = ClientError({}, "Op")
        # os.path.exists: False (initial), True (finally)
        self.os_mock.path.exists.side_effect = [False, True]
        result = processor._load_faiss_index_from_s3(
            "srd_dl_fail", mock_lambda_logger
        )
        assert result is None
        mock_lambda_logger.exception.assert_called()
        self.shutil_mock.rmtree.assert_called_once()  # Ensure cleanup still happens

    def test_faiss_load_local_fails(self, mock_lambda_logger):
        self.mock_faiss_class_instance.load_local.side_effect = Exception(
            "FAISS load error"
        )
        # os.path.exists: False (initial), True (finally)
        self.os_mock.path.exists.side_effect = [False, True]
        result = processor._load_faiss_index_from_s3(
            "srd_faiss_fail", mock_lambda_logger
        )
        assert result is None
        mock_lambda_logger.exception.assert_called()
        self.shutil_mock.rmtree.assert_called_once()


# --- Fixtures for TestGetAnswerFromRag ---
@pytest.fixture
def mock_processor_load_faiss_index():
    with patch("rag_query_processor.processor._load_faiss_index_from_s3") as m:
        yield m


@pytest.fixture
def mock_processor_get_llm_instance():
    with patch("rag_query_processor.processor.get_llm_instance") as m:
        yield m


@pytest.fixture
def mock_retrieval_qa_class():
    with patch(
        "rag_query_processor.processor.RetrievalQA", autospec=True
    ) as m:
        yield m


@pytest.fixture
def mock_prompt_template_class():
    with patch(
        "rag_query_processor.processor.PromptTemplate", autospec=True
    ) as m:
        yield m


@pytest.fixture
def mock_time_module():
    with patch("rag_query_processor.processor.time") as m:
        m.time.return_value = 1700000000.0
        yield m


@pytest.fixture
def mock_hashlib_md5():
    with patch("rag_query_processor.processor.hashlib.md5") as m:
        mock_hash_obj = MagicMock()
        mock_hash_obj.hexdigest.return_value = "mocked_query_hash"
        m.return_value = mock_hash_obj
        yield m


# --- Tests for get_answer_from_rag ---
class TestGetAnswerFromRag:
    @pytest.fixture(autouse=True)
    def setup_method_rag_mocks(
        self,
        mock_processor_load_faiss_index,
        mock_processor_get_llm_instance,
        mock_retrieval_qa_class,
        mock_prompt_template_class,
        mock_time_module,
        mock_hashlib_md5,
        mock_boto3_module_clients,
    ):
        self.load_faiss_index = mock_processor_load_faiss_index
        self.mock_faiss_store = MagicMock(spec=FAISS)
        # Mock retriever instance that will be returned by faiss_store.as_retriever()
        self.mock_retriever = MagicMock()
        self.mock_retriever.invoke.return_value = [
            Document(page_content="Doc1"),
            Document(page_content="Doc2"),
        ]
        self.mock_faiss_store.as_retriever.return_value = self.mock_retriever
        self.load_faiss_index.return_value = self.mock_faiss_store

        self.get_llm_instance = mock_processor_get_llm_instance
        self.mock_llm = MagicMock(spec=ChatBedrock)
        self.get_llm_instance.return_value = self.mock_llm

        self.retrieval_qa_class = mock_retrieval_qa_class
        self.mock_qa_chain = MagicMock(spec=RetrievalQA)
        self.mock_qa_chain.invoke.return_value = {
            "result": "LLM Answer",
            "source_documents": [Document(page_content="SourceDoc")],
        }
        self.retrieval_qa_class.from_chain_type.return_value = (
            self.mock_qa_chain
        )

        self.prompt_template_class = mock_prompt_template_class
        self.s3_client = mock_boto3_module_clients["s3"]
        self.dynamodb_client = mock_boto3_module_clients["dynamodb"]
        self.time_module = mock_time_module
        self.hashlib_md5 = mock_hashlib_md5

        with patch.object(processor, "CACHE_TTL_SECONDS", 3600):
            # Ensure processor's own logger is the mocked one for assertions
            self.processor_logger = mock_boto3_module_clients[
                "processor_logger"
            ]
            yield

    @pytest.mark.parametrize(
        "missing_client_attr", ["bedrock_runtime_client", "embedding_model"]
    )
    def test_get_answer_from_rag_missing_global_clients(
        self, missing_client_attr, mock_lambda_logger
    ):
        with patch.object(processor, missing_client_attr, None):
            # Also ensure the other client is present to isolate the test
            with patch.object(
                processor,
                (
                    "bedrock_runtime_client"
                    if missing_client_attr != "bedrock_runtime_client"
                    else "embedding_model"
                ),
                MagicMock(),
            ):
                result = processor.get_answer_from_rag(
                    "q", "srd", False, False, {}, mock_lambda_logger
                )
                assert "error" in result
                assert (
                    "Query processing components not ready" in result["error"]
                )
                mock_lambda_logger.error.assert_called_with(
                    "RAG components (Bedrock clients, models) not initialized."
                )

    def test_cache_hit_valid(self, mock_lambda_logger):
        cached_item = {
            "Item": {
                "answer": {"S": "cached"},
                "ttl": {"N": str(int(self.time_module.time() + 100))},
            }
        }
        self.dynamodb_client.get_item.return_value = cached_item
        result = processor.get_answer_from_rag(
            "q",
            "srd",
            True,
            False,
            {},
            mock_lambda_logger,  # invoke_generative_llm = True for cache
        )
        assert result == {"answer": "cached", "source": "cache"}
        self.load_faiss_index.assert_not_called()

    def test_cache_hit_expired_proceeds(self, mock_lambda_logger):
        cached_item = {
            "Item": {
                "answer": {"S": "expired"},
                "ttl": {"N": str(int(self.time_module.time() - 100))},
            }
        }
        self.dynamodb_client.get_item.return_value = cached_item
        processor.get_answer_from_rag(
            "q", "srd", True, False, {}, mock_lambda_logger
        )
        self.load_faiss_index.assert_called_once()

    def test_cache_miss_no_item_proceeds(self, mock_lambda_logger):
        self.dynamodb_client.get_item.return_value = {}  # No 'Item'
        processor.get_answer_from_rag(
            "q", "srd", True, False, {}, mock_lambda_logger
        )
        self.load_faiss_index.assert_called_once()

    def test_cache_dynamodb_error_proceeds(self, mock_lambda_logger):
        self.dynamodb_client.get_item.side_effect = ClientError({}, "Op")
        processor.get_answer_from_rag(
            "q", "srd", True, False, {}, mock_lambda_logger
        )
        self.load_faiss_index.assert_called_once()

    def test_get_answer_from_rag_cache_payload_json_decode_error(
        self, mock_lambda_logger
    ):
        cached_item = {
            "Item": {
                "not_answer": {"X": "this is not valid json"},
                "ttl": {"N": str(int(self.time_module.time() + 100))},
            }
        }
        self.dynamodb_client.get_item.return_value = cached_item
        processor.get_answer_from_rag(
            "q_json", "srd_json", True, False, {}, mock_lambda_logger
        )
        self.load_faiss_index.assert_called_once()

    @pytest.mark.parametrize(
        "ttl_item_data,log_message_part",
        [
            pytest.param(  # TTL field completely missing
                {"answer": {"S": "cached_bad_ttl_value"}},
                "Performing similarity search for query: 'q_ttl_err'",
                id="ttl_missing",
            ),
            pytest.param(  # TTL field wrong type (not 'N')
                {
                    "answer": {"S": "cached_bad_ttl_value"},
                    "ttl": {"S": "not_a_number_string_type_for_ttl"},
                },
                "Error processing cache item: 'N'. Proceeding without cache.",
                id="ttl_wrong_type",
            ),
            pytest.param(  # TTL field is 'N' but not a number string
                {
                    "answer": {"S": "cached_bad_ttl_value"},
                    "ttl": {"N": "not_a_number"},
                },
                "Error processing cache item: invalid literal for int() with base 10: 'not_a_number'. Proceeding without cache.",
                id="ttl_not_number_string",
            ),
        ],
    )
    def test_get_answer_from_rag_cache_invalid_ttl_data(
        self, ttl_item_data, log_message_part, mock_lambda_logger
    ):
        cached_item = {"Item": ttl_item_data}
        self.dynamodb_client.get_item.return_value = cached_item

        processor.get_answer_from_rag(
            "q_ttl_err", "srd_ttl", True, False, {}, mock_lambda_logger
        )

        # Check for specific log message (could be info or warning)
        all_log_calls = (
            mock_lambda_logger.warning.call_args_list
            + mock_lambda_logger.info.call_args_list
            + mock_lambda_logger.exception.call_args_list  # if it becomes an exception
        )
        found_log = any(
            log_message_part in str(call_args[0])
            for call_args in all_log_calls
        )
        assert (
            found_log
        ), f"Expected log containing '{log_message_part}' not found."

        self.load_faiss_index.assert_called_once()  # Should proceed as cache miss

    def test_no_cache_table_name_skips_cache(self, mock_lambda_logger):
        with patch.object(processor, "QUERY_CACHE_TABLE_NAME", None):
            processor.get_answer_from_rag(
                "q",
                "srd",
                True,
                False,
                {},
                mock_lambda_logger,  # LLM invoked
            )
            self.dynamodb_client.get_item.assert_not_called()
            self.load_faiss_index.assert_called_once()
            self.dynamodb_client.put_item.assert_not_called()
            mock_lambda_logger.warning.assert_any_call(
                "QUERY_CACHE_TABLE_NAME not set; Bedrock LLM response caching will be disabled."
            )

    def test_faiss_load_fails_returns_error(self, mock_lambda_logger):
        self.load_faiss_index.return_value = None
        result = processor.get_answer_from_rag(
            "q", "srd_fail", False, False, {}, mock_lambda_logger
        )
        assert "error" in result
        assert "Could not load SRD data for 'srd_fail'" in result["error"]

    def test_get_answer_from_rag_retriever_creation_fails(
        self, mock_lambda_logger
    ):
        self.mock_faiss_store.as_retriever.side_effect = Exception(
            "Retriever error"
        )
        result = processor.get_answer_from_rag(
            "q_ret_err", "srd_ret", False, False, {}, mock_lambda_logger
        )
        assert "error" in result
        assert (
            "Failed to prepare for information retrieval." in result["error"]
        )
        mock_lambda_logger.exception.assert_called_with(
            "Error creating retriever: Retriever error"
        )

    def test_no_llm_invocation_success(self, mock_lambda_logger):
        result = processor.get_answer_from_rag(
            "q_docs", "srd", False, False, {}, mock_lambda_logger
        )
        assert "Doc1" in result["answer"] and "Doc2" in result["answer"]
        assert result["source"] == "retrieval_only"
        self.get_llm_instance.assert_not_called()
        # No caching if LLM not invoked
        self.dynamodb_client.put_item.assert_not_called()

    def test_get_answer_from_rag_no_llm_no_docs_retrieved(
        self, mock_lambda_logger
    ):
        self.mock_retriever.invoke.return_value = []  # No docs

        result = processor.get_answer_from_rag(
            "q_no_docs", "srd_no_docs", False, False, {}, mock_lambda_logger
        )
        assert "answer" in result
        assert (
            "No specific information found to answer your query based on retrieval."
            in result["answer"]
        )
        assert result["source"] == "retrieval_only"
        self.dynamodb_client.put_item.assert_not_called()

    def test_llm_invocation_get_llm_fails(self, mock_lambda_logger):
        self.get_llm_instance.return_value = None
        result = processor.get_answer_from_rag(
            "q_llm", "srd", True, False, {}, mock_lambda_logger
        )
        assert "error" in result
        assert (
            "Internal server error: Generative LLM component could not be configured."
            in result["error"]
        )

    @pytest.mark.parametrize("conversational", [True, False])
    def test_llm_invocation_success(self, conversational, mock_lambda_logger):
        query = "q_llm"
        result = processor.get_answer_from_rag(
            query, "srd", True, conversational, {}, mock_lambda_logger
        )
        assert result["answer"] == "LLM Answer"
        assert result["source"] == "bedrock_llm"
        self.retrieval_qa_class.from_chain_type.assert_called_once()

        expected_query_to_llm = (
            f"User: {query}\nBot:" if conversational else query
        )
        self.mock_qa_chain.invoke.assert_called_once_with(
            {"query": expected_query_to_llm}
        )
        self.dynamodb_client.put_item.assert_called_once()

    def test_llm_chain_invoke_client_error(self, mock_lambda_logger):
        self.mock_qa_chain.invoke.side_effect = ClientError(
            {
                "Error": {
                    "Code": "ThrottlingException",
                    "Message": "Rate exceeded",
                }
            },
            "InvokeModel",
        )
        result = processor.get_answer_from_rag(
            "q_client_err", "srd_ce", True, False, {}, mock_lambda_logger
        )
        assert "error" in result
        assert (
            "Error communicating with the AI model. Please try again."
            in result["error"]
        )
        mock_lambda_logger.exception.assert_any_call(
            "Bedrock API error during RAG chain execution: An error occurred (ThrottlingException) when calling the InvokeModel operation: Rate exceeded"
        )

    def test_llm_chain_invoke_fails_general_exception(
        self, mock_lambda_logger
    ):
        self.mock_qa_chain.invoke.side_effect = Exception("Chain error")
        result = processor.get_answer_from_rag(
            "q_llm", "srd", True, False, {}, mock_lambda_logger
        )
        assert "error" in result
        assert (
            "Failed to generate an answer using the RAG chain."
            in result["error"]
        )
        mock_lambda_logger.exception.assert_any_call(
            "Error during RAG chain execution: Chain error"
        )

    def test_cache_put_item_fails_logs_warning(self, mock_lambda_logger):
        self.dynamodb_client.put_item.side_effect = ClientError({}, "Op")
        result = processor.get_answer_from_rag(
            "q_put_err",
            "srd_put",
            True,
            False,
            {},
            mock_lambda_logger,  # LLM invoked
        )
        assert result["answer"] == "LLM Answer"  # Still returns the result
        mock_lambda_logger.warning.assert_any_call(
            "DynamoDB cache put_item error: An error occurred (Unknown) when "
            "calling the Op operation: Unknown. Response not cached."
        )
