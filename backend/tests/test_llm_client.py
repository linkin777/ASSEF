"""测试 LLMClient 大模型客户端：Mock 模式、验证、请求载荷、重试、配置加载、错误分类、连接测试。"""

import pytest
from assef.llm import LLMClient, LLMError, LLMConnectionError, LLMErrorCode, classify_error_code
from assef.models.config import LLMBackendConfig


class TestLLMClientMock:
    def test_mock_returns_preset_response(self):
        client = LLMClient(backend="mock", mock_response="Hello World")
        assert client.chat([{"role": "user", "content": "hi"}]) == "Hello World"

    def test_mock_ignores_messages(self):
        client = LLMClient(backend="mock", mock_response="fixed")
        assert client.chat([{"role": "user", "content": "anything"}]) == "fixed"


class TestLLMClientValidation:
    def test_unsupported_backend_raises(self):
        with pytest.raises(ValueError, match="Unsupported backend"):
            LLMClient(backend="unsupported")

    def test_valid_backends_accepted(self):
        for backend in ("ollama", "openai", "deepseek", "anthropic", "mock"):
            LLMClient(backend=backend)


class TestLLMClientOllamaPayload:
    """测试 Ollama 请求载荷格式：URL、model、stream、temperature。"""

    def test_ollama_payload_format(self, monkeypatch):
        captured = {}

        def mock_post(url, json=None, timeout=None):
            captured["url"] = url
            captured["payload"] = json
            return type("Resp", (), {"raise_for_status": lambda self: None, "json": lambda self: {"message": {"content": "ok"}}})()

        monkeypatch.setattr("assef.llm.llm_client.requests.post", mock_post)

        client = LLMClient(backend="ollama", model="test-model")
        result = client.chat([{"role": "user", "content": "hello"}], temperature=0.5)

        assert result == "ok"
        assert captured["url"] == "http://localhost:11434/api/chat"
        assert captured["payload"]["model"] == "test-model"
        assert captured["payload"]["stream"] == False
        assert captured["payload"]["options"]["temperature"] == 0.5


class TestLLMClientRetry:
    def test_retry_on_failure_then_succeed(self, monkeypatch):
        import requests
        call_count = [0]

        def mock_post(url, json=None, timeout=None):
            call_count[0] += 1
            if call_count[0] < 2:
                raise requests.ConnectionError("Network error")
            return type("Resp", (), {"raise_for_status": lambda self: None, "json": lambda self: {"message": {"content": "ok"}}})()

        monkeypatch.setattr("assef.llm.llm_client.requests.post", mock_post)

        client = LLMClient(backend="ollama", model="test", max_retries=3)
        result = client.chat([{"role": "user", "content": "hi"}])
        assert result == "ok"
        assert call_count[0] == 2

    def test_retry_exhausted_raises_connection_error(self, monkeypatch):
        def mock_post(url, json=None, timeout=None):
            raise Exception("Always fails")

        monkeypatch.setattr("assef.llm.llm_client.requests.post", mock_post)

        client = LLMClient(backend="ollama", model="test", max_retries=2)
        with pytest.raises(LLMConnectionError) as exc_info:
            client.chat([{"role": "user", "content": "hi"}])
        assert exc_info.value.code == LLMErrorCode.UNKNOWN


class TestLLMClientFromConfig:
    def test_from_config_mock_backend(self):
        config = LLMBackendConfig(
            backend="mock",
            model="test-model",
            api_key="sk-test",
            base_url="https://api.example.com",
            mock_response="Mock output",
            max_retries=5,
            temperature=0.5,
            max_tokens=1024,
        )
        client = LLMClient.from_config(config)
        assert client._backend == "mock"
        assert client._mock_response == "Mock output"
        assert client._model == "test-model"
        assert client._api_key == "sk-test"
        assert client._max_retries == 5
        assert client.chat([{"role": "user", "content": "hi"}]) == "Mock output"

    def test_from_config_openai_backend(self):
        config = LLMBackendConfig(
            backend="openai",
            model="gpt-4o",
            api_key="sk-real-key",
            base_url="https://custom.openai.com",
            max_retries=2,
            temperature=0.3,
            max_tokens=512,
        )
        client = LLMClient.from_config(config)
        assert client._backend == "openai"
        assert client._model == "gpt-4o"
        assert client._api_key == "sk-real-key"
        assert client._max_retries == 2
        assert client._client is not None

    def test_old_init_still_works(self):
        client = LLMClient(backend="mock", mock_response="legacy")
        assert client._backend == "mock"
        assert client._mock_response == "legacy"
        assert client._max_retries == 3
        assert client.chat([{"role": "user", "content": "hi"}]) == "legacy"


class TestErrorClassification:
    """测试错误分类：连接拒绝、超时、HTTP 401/404/429/500、未知错误。"""

    def test_connection_refused_classified(self):
        import requests
        e = requests.ConnectionError("Connection refused")
        code = classify_error_code(e, "ollama")
        assert code == LLMErrorCode.CONNECTION_REFUSED

    def test_timeout_classified(self):
        import requests
        e = requests.Timeout("Read timed out")
        code = classify_error_code(e, "ollama")
        assert code == LLMErrorCode.TIMEOUT

    def test_http_401_classified(self):
        import requests
        mock_resp = type("Resp", (), {"status_code": 401, "text": "unauthorized"})()
        e = requests.HTTPError("401 Unauthorized", response=mock_resp)
        code = classify_error_code(e, "openai")
        assert code == LLMErrorCode.AUTHENTICATION_FAILED

    def test_http_404_classified(self):
        import requests
        mock_resp = type("Resp", (), {"status_code": 404, "text": "not found"})()
        e = requests.HTTPError("404 Not Found", response=mock_resp)
        code = classify_error_code(e, "openai")
        assert code == LLMErrorCode.NOT_FOUND

    def test_http_429_classified(self):
        import requests
        mock_resp = type("Resp", (), {"status_code": 429, "text": "rate limited"})()
        e = requests.HTTPError("429 Too Many Requests", response=mock_resp)
        code = classify_error_code(e, "openai")
        assert code == LLMErrorCode.RATE_LIMITED

    def test_http_500_classified(self):
        import requests
        mock_resp = type("Resp", (), {"status_code": 500, "text": "server error"})()
        e = requests.HTTPError("500 Internal Server Error", response=mock_resp)
        code = classify_error_code(e, "openai")
        assert code == LLMErrorCode.SERVER_ERROR

    def test_unknown_error_default(self):
        code = classify_error_code(ValueError("something random"), "ollama")
        assert code == LLMErrorCode.UNKNOWN

    def test_ollama_not_found(self):
        code = classify_error_code(Exception("model not found"), "ollama")
        assert code == LLMErrorCode.NOT_FOUND


class TestLLMConnectionError:
    def test_connection_error_has_code_and_diagnostic(self):
        e = LLMConnectionError(
            message="Ollama 连接被拒绝",
            code=LLMErrorCode.CONNECTION_REFUSED,
            detail="Connection refused",
        )
        assert e.code == LLMErrorCode.CONNECTION_REFUSED
        assert e.is_unconfigured is True
        assert "连接被拒绝" in e.diagnostic

    def test_auth_error_is_unconfigured(self):
        e = LLMConnectionError(
            message="认证失败",
            code=LLMErrorCode.AUTHENTICATION_FAILED,
            detail="Invalid API key",
        )
        assert e.is_unconfigured is True
        assert "认证失败" in e.diagnostic

    def test_server_error_is_not_unconfigured(self):
        e = LLMConnectionError(
            message="服务器错误",
            code=LLMErrorCode.SERVER_ERROR,
            detail="Internal server error",
        )
        assert e.is_unconfigured is False
        assert "服务器内部错误" in e.diagnostic


class TestLLMClientConnection:
    """测试连接测试和连接错误：Mock 连接、连接拒绝、HTTP 404、超时。"""

    def test_test_connection_mock(self):
        client = LLMClient(backend="mock", mock_response="test")
        ok, msg = client.test_connection()
        assert ok is True
        assert "Mock" in msg

    def test_connection_refused_gives_unconfigured(self, monkeypatch):
        import requests

        def mock_post(url, json=None, timeout=None):
            raise requests.ConnectionError("Connection refused")

        monkeypatch.setattr("assef.llm.llm_client.requests.post", mock_post)
        client = LLMClient(backend="ollama", model="test", max_retries=1)
        ok, msg = client.test_connection()
        assert ok is False
        assert "连接被拒绝" in msg

    def test_chat_raises_connection_error_on_refused(self, monkeypatch):
        import requests

        def mock_post(url, json=None, timeout=None):
            raise requests.ConnectionError("Connection refused")

        monkeypatch.setattr("assef.llm.llm_client.requests.post", mock_post)
        client = LLMClient(backend="ollama", model="test", max_retries=1)
        with pytest.raises(LLMConnectionError) as exc_info:
            client.chat([{"role": "user", "content": "hi"}])
        assert exc_info.value.code == LLMErrorCode.CONNECTION_REFUSED

    def test_ollama_http_404_raises_not_found(self, monkeypatch):
        import requests

        mock_resp = type("Resp", (), {"status_code": 404, "text": "model not found", "raise_for_status": lambda self: (_ for _ in ()).throw(requests.HTTPError("404", response=mock_resp))})()

        def mock_post(url, json=None, timeout=None):
            from requests.exceptions import HTTPError
            resp = type("Resp", (), {"status_code": 404, "text": "model not found", "raise_for_status": lambda self: (_ for _ in ()).throw(HTTPError("404 Not Found", response=self))})()
            raise HTTPError("404 Not Found", response=resp)

        monkeypatch.setattr("assef.llm.llm_client.requests.post", mock_post)
        client = LLMClient(backend="ollama", model="no-such-model", max_retries=1)
        with pytest.raises(LLMConnectionError) as exc_info:
            client.chat([{"role": "user", "content": "hi"}])
        assert exc_info.value.code == LLMErrorCode.NOT_FOUND

    def test_ollama_retry_timeout_raises_timeout_code(self, monkeypatch):
        import requests

        def mock_post(url, json=None, timeout=None):
            raise requests.Timeout("Read timed out")

        monkeypatch.setattr("assef.llm.llm_client.requests.post", mock_post)
        client = LLMClient(backend="ollama", model="test", max_retries=2)
        with pytest.raises(LLMConnectionError) as exc_info:
            client.chat([{"role": "user", "content": "hi"}])
        assert exc_info.value.code == LLMErrorCode.TIMEOUT
