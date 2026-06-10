"""统一 LLM 客户端模块 —— 支持多后端（Ollama/OpenAI/DeepSeek/Anthropic/Mock）、错误分类与重试逻辑"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Callable, cast

import requests  # type: ignore[import-untyped]
from openai import (
    APIError,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)
from openai.types.chat import ChatCompletionChunk

from ..logging_config import get_logger
from ..models.config import LLMBackendConfig


class LLMErrorCode(Enum):
    """LLM 连接错误码枚举，用于分类和诊断不同类型的连接与请求错误

    每个枚举值对应一种具体的错误场景，附带对应的中文错误诊断提示。
    分为可重试错误（TIMEOUT/RATE_LIMITED/SERVER_ERROR/CONNECTION_REFUSED）
    和不可重试错误（需用户修正配置才能恢复）。
    """
    CONNECTION_REFUSED = "connection_refused"
    HOST_NOT_FOUND = "host_not_found"
    TIMEOUT = "timeout"
    AUTHENTICATION_FAILED = "authentication_failed"
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"
    NOT_FOUND = "not_found"
    INVALID_CONFIG = "invalid_config"
    UNKNOWN = "unknown"


_ERROR_CODE_MESSAGES: dict[LLMErrorCode, str] = {
    LLMErrorCode.CONNECTION_REFUSED: "连接被拒绝：LLM 服务未启动或端口不可达，请检查服务是否运行（如 Ollama 是否启动）",
    LLMErrorCode.HOST_NOT_FOUND: "主机名解析失败：无法找到目标服务器，请检查 base_url 或网络连接",
    LLMErrorCode.TIMEOUT: "连接超时：LLM 服务响应超时，请确认服务是否正常运行",
    LLMErrorCode.AUTHENTICATION_FAILED: "认证失败：API Key 无效或已过期，请检查配置中的 api_key",
    LLMErrorCode.RATE_LIMITED: "请求频率超限：API 请求被限流，请稍后重试或降低请求频率",
    LLMErrorCode.SERVER_ERROR: "服务器内部错误：LLM 服务端返回错误，请稍后重试或检查配置",
    LLMErrorCode.NOT_FOUND: "资源未找到：模型名称不存在或 API 路径错误，请检查 model 和 base_url 配置",
    LLMErrorCode.INVALID_CONFIG: "配置无效：LLM 后端配置不完整或错误，请检查 backend、model、api_key、base_url",
    LLMErrorCode.UNKNOWN: "未知连接错误：请检查 LLM 后端配置和服务状态",
}

_UNCONFIGURED_CODES = frozenset({
    LLMErrorCode.CONNECTION_REFUSED,
    LLMErrorCode.HOST_NOT_FOUND,
    LLMErrorCode.TIMEOUT,
    LLMErrorCode.INVALID_CONFIG,
    LLMErrorCode.NOT_FOUND,
    LLMErrorCode.AUTHENTICATION_FAILED,
})

_RETRYABLE_CODES = frozenset({
    LLMErrorCode.CONNECTION_REFUSED,
    LLMErrorCode.TIMEOUT,
    LLMErrorCode.RATE_LIMITED,
    LLMErrorCode.SERVER_ERROR,
})


def _classify_openai_error(exception: Exception) -> LLMErrorCode | None:
    """将 OpenAI SDK 异常映射为 LLMErrorCode

    根据异常类型和 HTTP 状态码进行分类，支持所有 OpenAI SDK 内置异常类型。

    Args:
        exception: OpenAI SDK 抛出的异常实例

    Returns:
        对应的 LLMErrorCode，若无法分类则返回 None
    """
    if isinstance(exception, APITimeoutError):
        return LLMErrorCode.TIMEOUT
    if isinstance(exception, APIConnectionError):
        return LLMErrorCode.CONNECTION_REFUSED
    if isinstance(exception, AuthenticationError):
        return LLMErrorCode.AUTHENTICATION_FAILED
    if isinstance(exception, PermissionDeniedError):
        return LLMErrorCode.AUTHENTICATION_FAILED
    if isinstance(exception, NotFoundError):
        return LLMErrorCode.NOT_FOUND
    if isinstance(exception, RateLimitError):
        return LLMErrorCode.RATE_LIMITED
    if isinstance(exception, InternalServerError):
        return LLMErrorCode.SERVER_ERROR
    if isinstance(exception, BadRequestError):
        return LLMErrorCode.INVALID_CONFIG
    if isinstance(exception, APIStatusError):
        status_code = getattr(exception, 'status_code', None)
        if status_code is not None and status_code >= 500:
            return LLMErrorCode.SERVER_ERROR
        return LLMErrorCode.INVALID_CONFIG
    if isinstance(exception, APIError):
        return LLMErrorCode.UNKNOWN
    return None


def classify_error_code(exception: Exception, backend: str) -> LLMErrorCode:
    """将多种异常类型统一分类为 LLMErrorCode

    依次尝试 OpenAI SDK 异常匹配和 requests 库异常匹配，
    同时根据后端类型（如 Ollama）执行特定的错误消息解析。

    Args:
        exception: 原始异常实例
        backend: 后端类型字符串（如 "ollama"/"openai"/"deepseek" 等）

    Returns:
        分类后的 LLMErrorCode
    """
    code = _classify_openai_error(exception)
    if code is not None:
        return code
    if isinstance(exception, requests.ConnectionError):
        error_str = str(exception).lower()
        if "refused" in error_str or "connect" in error_str:
            return LLMErrorCode.CONNECTION_REFUSED
        if "name or service not known" in error_str or "getaddrinfo" in error_str or "nodename nor servname" in error_str:
            return LLMErrorCode.HOST_NOT_FOUND
        return LLMErrorCode.CONNECTION_REFUSED

    if isinstance(exception, requests.Timeout):
        return LLMErrorCode.TIMEOUT

    if isinstance(exception, requests.HTTPError):
        status_code = getattr(exception.response, "status_code", None) if hasattr(exception, "response") else None
        if status_code == 401:
            return LLMErrorCode.AUTHENTICATION_FAILED
        if status_code == 429:
            return LLMErrorCode.RATE_LIMITED
        if status_code == 404:
            return LLMErrorCode.NOT_FOUND
        if status_code is not None and status_code >= 500:
            return LLMErrorCode.SERVER_ERROR

    error_str = str(exception).lower()
    if backend == "ollama":
        return _classify_ollama_error(error_str)

    if any(kw in error_str for kw in ("401", "unauthorized", "invalid api key", "incorrect api key", "authentication")):
        return LLMErrorCode.AUTHENTICATION_FAILED
    if any(kw in error_str for kw in ("403", "forbidden", "permission", "not allowed")):
        return LLMErrorCode.AUTHENTICATION_FAILED
    if any(kw in error_str for kw in ("429", "rate limit", "too many requests")):
        return LLMErrorCode.RATE_LIMITED
    if any(kw in error_str for kw in ("404", "not found", "model not found", "does not exist")):
        return LLMErrorCode.NOT_FOUND
    if any(kw in error_str for kw in ("500", "502", "503", "internal server error", "service unavailable")):
        return LLMErrorCode.SERVER_ERROR
    if any(kw in error_str for kw in ("connection", "timeout", "timed out")):
        return LLMErrorCode.CONNECTION_REFUSED

    return LLMErrorCode.UNKNOWN


def _classify_ollama_error(error_str: str) -> LLMErrorCode:
    """根据 Ollama 错误消息字符串分类错误类型

    Args:
        error_str: 错误消息字符串（已转为小写）

    Returns:
        对应的 LLMErrorCode
    """
    if any(kw in error_str for kw in ("connection refused", "connect error", "connectionerror")):
        return LLMErrorCode.CONNECTION_REFUSED
    if "timeout" in error_str or "timed out" in error_str:
        return LLMErrorCode.TIMEOUT
    if "not found" in error_str or "unknown model" in error_str:
        return LLMErrorCode.NOT_FOUND
    return LLMErrorCode.UNKNOWN


def is_unconfigured(code: LLMErrorCode) -> bool:
    """检查错误码是否属于未配置类错误（需用户修正配置后才能恢复）

    Args:
        code: LLMErrorCode 枚举值

    Returns:
        若属于未配置错误则返回 True，否则返回 False
    """
    return code in _UNCONFIGURED_CODES


class LLMError(Exception):
    """LLM 客户端通用异常基类"""
    pass


class LLMConnectionError(LLMError):
    """LLM 连接错误异常，携带结构化错误码和诊断信息

    Attributes:
        code: 分类后的 LLMErrorCode
        detail: 原始异常详情字符串
        is_unconfigured: 是否属于配置类错误（不可重试）
    """
    def __init__(self, message: str, code: LLMErrorCode = LLMErrorCode.UNKNOWN, detail: str = "") -> None:
        """初始化 LLM 连接错误

        Args:
            message: 错误描述信息
            code: 分类后的错误码，默认为 UNKNOWN
            detail: 原始异常详情字符串
        """
        super().__init__(message)
        self.code = code
        self.detail = detail
        self.is_unconfigured = is_unconfigured(code)

    @property
    def diagnostic(self) -> str:
        """获取错误码对应的中文诊断提示信息"""
        return _ERROR_CODE_MESSAGES.get(self.code, _ERROR_CODE_MESSAGES[LLMErrorCode.UNKNOWN])


class LLMClient:
    """统一 LLM 客户端，支持多后端（Ollama/OpenAI/DeepSeek/Anthropic/Mock）

    提供聊天补全、流式输出、连接测试等功能，内置指数退避重试逻辑和结构化错误分类。
    支持 OpenAI 兼容接口的统一调用，Ollama 通过原生 HTTP API 调用，
    Mock 后端用于测试和离线场景。
    """
    OLLAMA_URL = "http://localhost:11434/api/chat"
    _logger = get_logger("llm")

    def __init__(
        self,
        backend: str,
        model: str = "",
        api_key: str = "",
        base_url: str = "",
        mock_response: str = "",
        max_retries: int = 3,
        is_reasoning_model: bool = False,
        on_call_record: Callable[[dict], None] | None = None,
    ) -> None:
        """初始化 LLM 客户端

        根据 backend 类型初始化对应的 SDK 客户端（OpenAI 兼容），
        或保留 _client=None（Ollama/Mock 后端不需要 SDK 客户端）。

        Args:
            backend: 后端类型（ollama/openai/deepseek/anthropic/mock）
            model: 模型名称
            api_key: API 密钥
            base_url: API 基础 URL
            mock_response: Mock 后端使用的模拟响应文本
            max_retries: 最大重试次数
            is_reasoning_model: 是否为 reasoning 模型
            on_call_record: LLM 调用记录回调函数

        Raises:
            ValueError: 后端类型不受支持
        """
        backend_lower = backend.lower()
        if backend_lower not in ("ollama", "openai", "deepseek", "anthropic", "mock"):
            raise ValueError(f"Unsupported backend: {backend}")
        self._backend = backend_lower
        self._model = model
        self._api_key = api_key
        self._base_url = base_url
        self._mock_response = mock_response
        self._max_retries = max_retries
        self._is_reasoning_model = is_reasoning_model
        self._on_call_record = on_call_record
        self._call_context: dict | None = None

        self._client: OpenAI | None = None

        if self._backend == "openai":
            resolved_url = base_url or "https://api.openai.com/v1"
            self._client = OpenAI(api_key=api_key or "sk-placeholder", base_url=resolved_url)
        elif self._backend == "deepseek":
            resolved_url = base_url or "https://api.deepseek.com/v1"
            self._client = OpenAI(api_key=api_key or "sk-placeholder", base_url=resolved_url)
        elif self._backend == "anthropic":
            resolved_url = base_url or "https://api.anthropic.com/v1"
            self._client = OpenAI(api_key=api_key or "sk-placeholder", base_url=resolved_url)

    @classmethod
    def from_config(cls, config: LLMBackendConfig, on_call_record: Callable[[dict], None] | None = None) -> LLMClient:
        """从 LLMBackendConfig 配置对象创建 LLMClient 实例

        Args:
            config: LLM 后端配置
            on_call_record: LLM 调用记录回调函数

        Returns:
            新的 LLMClient 实例
        """
        return cls(
            backend=config.backend,
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            mock_response=config.mock_response,
            max_retries=config.max_retries,
            is_reasoning_model=config.is_reasoning_model,
            on_call_record=on_call_record,
        )

    def set_call_context(self, context: dict) -> None:
        """设置 LLM 调用的上下文信息，将附带在 on_call_record 回调中

        Args:
            context: 上下文字典（如 round/caller/call_id 等信息）
        """
        self._call_context = context

    def test_connection(self) -> tuple[bool, str]:
        """快速测试 LLM 后端连接是否可用

        Returns:
            (is_ok, message) 元组
        """
        if self._backend == "mock":
            return True, "Mock 后端无需连接"

        try:
            self.chat([{"role": "user", "content": "hello"}], temperature=0.0, max_tokens=128)
            return True, "连接成功"
        except LLMConnectionError as e:
            return False, f"{e} — {e.diagnostic}"
        except Exception as e:
            code = classify_error_code(e, self._backend)
            msg = _ERROR_CODE_MESSAGES.get(code, str(e))
            return False, msg

    def chat(self, messages: list[dict], **kwargs: Any) -> str:
        """发送聊天消息并返回完整响应

        支持自动重试（指数退避）、空响应检测和 on_call_record 回调。
        对不可重试的错误码（如认证失败、配置无效）直接抛出异常。

        Args:
            messages: 消息列表，每项包含 role 和 content 字段
            **kwargs: 可选参数，如 temperature、max_tokens 等

        Returns:
            LLM 响应文本

        Raises:
            LLMConnectionError: 所有重试耗尽后或不可重试错误
        """
        if self._backend == "mock":
            result = self._mock_response
            if self._on_call_record is not None:
                try:
                    self._on_call_record({
                        "messages": messages,
                        "response": result,
                        "duration_ms": 0,
                        "backend": self._backend,
                        "model": self._model,
                        "call_context": self._call_context,
                    })
                except Exception:
                    self._logger.warning("on_call_record callback failed", exc_info=True)
            return result

        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        self._logger.debug(
            "LLM chat request: backend=%s model=%s messages=%d total_chars=%d",
            self._backend,
            self._model,
            len(messages),
            total_chars,
        )
        self._logger.info("LLM Request: backend=%s model=%s messages_chars=%d",
            self._backend, self._model, total_chars)
        msg_preview = str(messages)[:800]
        self._logger.debug("LLM Request messages: %s", msg_preview)

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                t0 = time.time()
                result = self._chat_inner(messages, **kwargs)
                if not result or not result.strip():
                    elapsed_ms = (time.time() - t0) * 1000
                    self._logger.warning(
                        "LLM returned empty response (attempt %d/%d, elapsed_ms=%.0f)",
                        attempt,
                        self._max_retries,
                        elapsed_ms,
                    )
                    if attempt < self._max_retries:
                        if self._is_reasoning_model:
                            kwargs["max_tokens"] = kwargs.get("max_tokens", 2048) + 2048
                            self._logger.info("Reasoning model retry with increased max_tokens=%d", kwargs["max_tokens"])
                        time.sleep(2 ** (attempt - 1))
                    continue
                elapsed_ms = (time.time() - t0) * 1000
                self._logger.info("LLM Response: role=%s/%s duration=%dms response_chars=%d",
                    self._backend, self._model, elapsed_ms, len(result))
                self._logger.debug("LLM Response content: %s", result[:2000])
                self._logger.debug(
                    "LLM chat success: backend=%s model=%s elapsed_ms=%.0f response_len=%d",
                    self._backend,
                    self._model,
                    elapsed_ms,
                    len(result),
                )
                if self._on_call_record is not None:
                    try:
                        self._on_call_record({
                            "messages": messages,
                            "response": result,
                            "duration_ms": elapsed_ms,
                            "backend": self._backend,
                            "model": self._model,
                            "call_context": self._call_context,
                        })
                    except Exception:
                        self._logger.warning("on_call_record callback failed", exc_info=True)
                return result
            except LLMConnectionError as e:
                if e.code not in _RETRYABLE_CODES:
                    raise
                last_error = e
                self._logger.warning(
                    "LLM chat retry %d/%d: %s",
                    attempt,
                    self._max_retries,
                    e,
                )
                if attempt < self._max_retries:
                    time.sleep(2 ** (attempt - 1))
            except Exception as e:
                last_error = e
                self._logger.warning(
                    "LLM chat retry %d/%d: %s",
                    attempt,
                    self._max_retries,
                    e,
                    exc_info=True,
                )
                if attempt < self._max_retries:
                    time.sleep(2 ** (attempt - 1))

        if last_error is None:
            raise LLMConnectionError(
                message=f"LLM returned empty response after {self._max_retries} retries",
                code=LLMErrorCode.INVALID_CONFIG,
            )

        code = classify_error_code(last_error, self._backend)
        detail = str(last_error)
        self._logger.error(
            "LLM chat exhausted all %d retries: code=%s detail=%s",
            self._max_retries,
            code.value,
            detail,
        )
        raise LLMConnectionError(
            message=f"[{code.value}] {detail[:200]}",
            code=code,
            detail=detail,
        )

    def chat_stream(
        self,
        messages: list[dict],
        on_token: Callable[[str], None],
        **kwargs: Any,
    ) -> str:
        """发送聊天消息并以流式方式逐 token 输出

        通过 on_token 回调逐 token 推送响应内容，同时返回完整响应文本。
        支持自动重试（指数退避）。

        Args:
            messages: 消息列表，每项包含 role 和 content 字段
            on_token: token 回调函数，接收每个生成的 token 文本
            **kwargs: 可选参数，如 temperature、max_tokens 等

        Returns:
            完整的 LLM 响应文本

        Raises:
            LLMConnectionError: 所有重试耗尽后或不可重试错误
        """
        if self._backend == "mock":
            chunk_size = 10
            for i in range(0, len(self._mock_response), chunk_size):
                chunk = self._mock_response[i:i + chunk_size]
                on_token(chunk)
                time.sleep(0.02)
            result = self._mock_response
            if self._on_call_record is not None:
                try:
                    self._on_call_record({
                        "messages": messages,
                        "response": result,
                        "duration_ms": 0,
                        "backend": self._backend,
                        "model": self._model,
                        "call_context": self._call_context,
                    })
                except Exception:
                    self._logger.warning("on_call_record callback failed", exc_info=True)
            return result

        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        self._logger.debug(
            "LLM chat_stream request: backend=%s model=%s messages=%d total_chars=%d",
            self._backend,
            self._model,
            len(messages),
            total_chars,
        )

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                t0 = time.time()
                result = self._chat_stream_inner(messages, on_token, **kwargs)
                elapsed_ms = (time.time() - t0) * 1000
                self._logger.debug(
                    "LLM chat_stream success: backend=%s model=%s elapsed_ms=%.0f response_len=%d",
                    self._backend,
                    self._model,
                    elapsed_ms,
                    len(result),
                )
                if self._on_call_record is not None:
                    try:
                        self._on_call_record({
                            "messages": messages,
                            "response": result,
                            "duration_ms": elapsed_ms,
                            "backend": self._backend,
                            "model": self._model,
                            "call_context": self._call_context,
                        })
                    except Exception:
                        self._logger.warning("on_call_record callback failed", exc_info=True)
                return result
            except LLMConnectionError as e:
                if e.code not in _RETRYABLE_CODES:
                    raise
                last_error = e
                self._logger.warning(
                    "LLM chat_stream retry %d/%d: %s",
                    attempt,
                    self._max_retries,
                    e,
                )
                if attempt < self._max_retries:
                    time.sleep(2 ** (attempt - 1))
            except Exception as e:
                last_error = e
                self._logger.warning(
                    "LLM chat_stream retry %d/%d: %s",
                    attempt,
                    self._max_retries,
                    e,
                    exc_info=True,
                )
                if attempt < self._max_retries:
                    time.sleep(2 ** (attempt - 1))

        code = classify_error_code(last_error, self._backend) if last_error else LLMErrorCode.UNKNOWN
        detail = str(last_error) if last_error else "未知错误"
        self._logger.error(
            "LLM chat_stream exhausted all %d retries: code=%s detail=%s",
            self._max_retries,
            code.value,
            detail,
        )
        raise LLMConnectionError(
            message=f"[{code.value}] {detail[:200]}",
            code=code,
            detail=detail,
        )

    def chat_stream_with_phase(
        self,
        messages: list[dict],
        on_phase: Callable[[str], None],
        on_token: Callable[[str, str], None],
        **kwargs: Any,
    ) -> str:
        """发送聊天消息并以流式方式输出，通过相位回调区分思考和输出阶段"""
        if self._backend == "mock":
            on_phase("output")
            chunk_size = 10
            for i in range(0, len(self._mock_response), chunk_size):
                chunk = self._mock_response[i:i + chunk_size]
                on_token(chunk, "output")
                time.sleep(0.02)
            return self._mock_response

        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        self._logger.debug(
            "LLM chat_stream_with_phase: backend=%s model=%s messages=%d total_chars=%d",
            self._backend, self._model, len(messages), total_chars,
        )

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                t0 = time.time()
                if self._backend in ("openai", "deepseek", "anthropic"):
                    temperature = kwargs.get("temperature", 0.7)
                    max_tokens = kwargs.get("max_tokens", 2048)
                    result = self._chat_openai_compat_stream_with_phase(
                        messages, on_phase, on_token, temperature, max_tokens,
                    )
                elif self._backend == "ollama":
                    raise NotImplementedError("Ollama stream with phase not implemented")
                else:
                    raise LLMError(f"Unknown backend: {self._backend}")

                elapsed_ms = (time.time() - t0) * 1000
                self._logger.debug(
                    "chat_stream_with_phase success: backend=%s model=%s elapsed_ms=%.0f response_len=%d",
                    self._backend, self._model, elapsed_ms, len(result),
                )
                return result
            except LLMConnectionError as e:
                if e.code not in _RETRYABLE_CODES:
                    raise
                last_error = e
                if attempt < self._max_retries:
                    time.sleep(2 ** (attempt - 1))
            except Exception as e:
                last_error = e
                if attempt < self._max_retries:
                    time.sleep(2 ** (attempt - 1))

        code = classify_error_code(last_error, self._backend) if last_error else LLMErrorCode.UNKNOWN
        detail = str(last_error) if last_error else "unknown"
        raise LLMConnectionError(
            message=f"[{code.value}] {detail[:200]}",
            code=code,
            detail=detail,
        )

    def _chat_stream_inner(
        self,
        messages: list[dict],
        on_token: Callable[[str], None],
        **kwargs: Any,
    ) -> str:
        """根据后端类型分发到对应的流式聊天内部实现

        Args:
            messages: 消息列表
            on_token: token 回调函数
            **kwargs: 可选参数

        Returns:
            完整的 LLM 响应文本

        Raises:
            LLMError: 后端类型未知
        """
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 2048)

        if self._backend == "ollama":
            return self._chat_ollama_stream(messages, on_token, temperature, max_tokens)
        elif self._backend in ("openai", "deepseek", "anthropic"):
            return self._chat_openai_compat_stream(messages, on_token, temperature, max_tokens)
        raise LLMError(f"Unknown backend: {self._backend}")

    def _chat_inner(self, messages: list[dict], **kwargs: Any) -> str:
        """根据后端类型分发到对应的聊天内部实现

        Args:
            messages: 消息列表
            **kwargs: 可选参数

        Returns:
            LLM 响应文本

        Raises:
            LLMError: 后端类型未知
        """
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 2048)

        if self._backend == "ollama":
            return self._chat_ollama(messages, temperature, max_tokens)
        elif self._backend in ("openai", "deepseek", "anthropic"):
            return self._chat_openai_compat(messages, temperature, max_tokens)
        raise LLMError(f"Unknown backend: {self._backend}")

    def _chat_ollama(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
        """通过 Ollama 原生 HTTP API 发送非流式聊天请求

        Args:
            messages: 消息列表
            temperature: 生成温度
            max_tokens: 最大生成 token 数

        Returns:
            LLM 响应文本

        Raises:
            LLMConnectionError: 连接错误（已分类）
        """
        last_msg_content = ""
        for m in reversed(messages):
            if m.get("role") == "user" and m.get("content"):
                last_msg_content = m["content"]
                break
        self._logger.debug(
            "Ollama request: model=%s temperature=%.2f max_tokens=%d messages=%d last_msg=%.500s",
            self._model,
            temperature,
            max_tokens,
            len(messages),
            last_msg_content,
        )
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            t0 = time.time()
            resp = requests.post(self.OLLAMA_URL, json=payload, timeout=120)
            resp.raise_for_status()
            result = resp.json()["message"]["content"]
            elapsed_ms = (time.time() - t0) * 1000
            self._logger.debug(
                "Ollama response: model=%s elapsed_ms=%.0f response_len=%d response=%.1000s",
                self._model,
                elapsed_ms,
                len(result),
                result,
            )
            return result
        except requests.ConnectionError as e:
            self._logger.warning("Ollama connection refused: %s", e)
            raise LLMConnectionError(
                message=f"Ollama 连接被拒绝：{e}",
                code=LLMErrorCode.CONNECTION_REFUSED,
                detail=str(e),
            ) from e
        except requests.Timeout as e:
            self._logger.warning("Ollama timeout: %s", e)
            raise LLMConnectionError(
                message=f"Ollama 请求超时：{e}",
                code=LLMErrorCode.TIMEOUT,
                detail=str(e),
            ) from e
        except requests.HTTPError as e:
            status_code = getattr(e.response, "status_code", None) if hasattr(e, "response") else None
            if status_code == 404:
                raise LLMConnectionError(
                    message=f"Ollama 模型未找到：{self._model}",
                    code=LLMErrorCode.NOT_FOUND,
                    detail=str(e),
                ) from e
            self._logger.warning("Ollama HTTP error: %s", e)
            raise LLMConnectionError(
                message=f"Ollama 服务错误：{e}",
                code=LLMErrorCode.SERVER_ERROR if status_code and status_code >= 500 else LLMErrorCode.UNKNOWN,
                detail=str(e),
            ) from e
        except LLMConnectionError:
            raise
        except Exception as e:
            self._logger.warning("Ollama request failed: model=%s", self._model, exc_info=True)
            raise LLMConnectionError(
                message=f"Ollama 请求失败：{e}",
                code=LLMErrorCode.UNKNOWN,
                detail=str(e),
            ) from e

    def _chat_ollama_stream(
        self,
        messages: list[dict],
        on_token: Callable[[str], None],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """通过 Ollama 原生 HTTP API 发送流式聊天请求

        Args:
            messages: 消息列表
            on_token: token 回调函数
            temperature: 生成温度
            max_tokens: 最大生成 token 数

        Returns:
            完整的 LLM 响应文本

        Raises:
            LLMConnectionError: 连接错误（已分类）
        """
        self._logger.debug(
            "Ollama stream request: model=%s temperature=%.2f max_tokens=%d messages=%d",
            self._model,
            temperature,
            max_tokens,
            len(messages),
        )
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            t0 = time.time()
            resp = requests.post(self.OLLAMA_URL, json=payload, timeout=120, stream=True)
            resp.raise_for_status()
            full_response = ""
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    data = __import__("json").loads(line)
                except Exception:
                    continue
                content = data.get("message", {}).get("content", "")
                if content:
                    on_token(content)
                    full_response += content
            elapsed_ms = (time.time() - t0) * 1000
            self._logger.debug(
                "Ollama stream response: model=%s elapsed_ms=%.0f response_len=%d",
                self._model,
                elapsed_ms,
                len(full_response),
            )
            return full_response
        except requests.ConnectionError as e:
            self._logger.warning("Ollama stream connection refused: %s", e)
            raise LLMConnectionError(
                message=f"Ollama 连接被拒绝：{e}",
                code=LLMErrorCode.CONNECTION_REFUSED,
                detail=str(e),
            ) from e
        except requests.Timeout as e:
            self._logger.warning("Ollama stream timeout: %s", e)
            raise LLMConnectionError(
                message=f"Ollama 请求超时：{e}",
                code=LLMErrorCode.TIMEOUT,
                detail=str(e),
            ) from e
        except requests.HTTPError as e:
            status_code = getattr(e.response, "status_code", None) if hasattr(e, "response") else None
            if status_code == 404:
                raise LLMConnectionError(
                    message=f"Ollama 模型未找到：{self._model}",
                    code=LLMErrorCode.NOT_FOUND,
                    detail=str(e),
                ) from e
            self._logger.warning("Ollama stream HTTP error: %s", e)
            raise LLMConnectionError(
                message=f"Ollama 服务错误：{e}",
                code=LLMErrorCode.SERVER_ERROR if status_code and status_code >= 500 else LLMErrorCode.UNKNOWN,
                detail=str(e),
            ) from e
        except LLMConnectionError:
            raise
        except Exception as e:
            self._logger.warning("Ollama stream request failed: model=%s", self._model, exc_info=True)
            raise LLMConnectionError(
                message=f"Ollama 流式请求失败：{e}",
                code=LLMErrorCode.UNKNOWN,
                detail=str(e),
            ) from e

    def _chat_openai_compat(self, messages: list[dict[str, Any]], temperature: float, max_tokens: int) -> str:
        """通过 OpenAI 兼容 SDK 发送非流式聊天请求

        支持 OpenAI、DeepSeek、Anthropic 等兼容接口。
        对 reasoning 模型自动回退到 reasoning_content 字段。

        Args:
            messages: 消息列表
            temperature: 生成温度
            max_tokens: 最大生成 token 数

        Returns:
            LLM 响应文本

        Raises:
            LLMConnectionError: OpenAI SDK 异常（已分类）
        """
        last_msg_content = ""
        for m in reversed(messages):
            if m.get("role") == "user" and m.get("content"):
                last_msg_content = m["content"]
                break
        self._logger.debug(
            "OpenAI-compat request: backend=%s model=%s temperature=%.2f max_tokens=%d messages=%d last_msg=%.500s",
            self._backend,
            self._model,
            temperature,
            max_tokens,
            len(messages),
            last_msg_content,
        )
        try:
            t0 = time.time()
            assert self._client is not None, "OpenAI client not initialized"
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
            )
            msg = response.choices[0].message
            result = msg.content or ""
            if not result:
                if self._is_reasoning_model:
                    self._logger.warning("Reasoning model returned empty content (reasoning_content ignored for code generation): model=%s", self._model)
                else:
                    reasoning = getattr(msg, 'reasoning_content', None) or ""
                    if reasoning:
                        result = reasoning
                        self._logger.debug("Empty msg.content, used reasoning_content: len=%d", len(reasoning))
                    else:
                        self._logger.debug("Both msg.content and reasoning_content are empty for model=%s", self._model)
            elapsed_ms = (time.time() - t0) * 1000
            self._logger.debug(
                "OpenAI-compat response: backend=%s model=%s elapsed_ms=%.0f response_len=%d response=%.1000s",
                self._backend,
                self._model,
                elapsed_ms,
                len(result),
                result,
            )
            return result
        except LLMConnectionError:
            raise
        except (APITimeoutError, APIConnectionError, AuthenticationError,
                PermissionDeniedError, NotFoundError, RateLimitError,
                InternalServerError, BadRequestError, APIStatusError, APIError) as e:
            code = _classify_openai_error(e) or LLMErrorCode.UNKNOWN
            raise LLMConnectionError(
                message=_ERROR_CODE_MESSAGES.get(code, str(e)),
                code=code,
                detail=str(e),
            ) from e
        except Exception as e:
            raise

    def _chat_openai_compat_stream(
        self,
        messages: list[dict[str, Any]],
        on_token: Callable[[str], None],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """通过 OpenAI 兼容 SDK 发送流式聊天请求

        支持 OpenAI、DeepSeek、Anthropic 等兼容接口的流式输出。
        对 reasoning 模型自动回退到 reasoning_content 字段。

        Args:
            messages: 消息列表
            on_token: token 回调函数
            temperature: 生成温度
            max_tokens: 最大生成 token 数

        Returns:
            完整的 LLM 响应文本

        Raises:
            LLMConnectionError: OpenAI SDK 异常（已分类）
        """
        self._logger.debug(
            "OpenAI-compat stream request: backend=%s model=%s temperature=%.2f max_tokens=%d",
            self._backend,
            self._model,
            temperature,
            max_tokens,
        )
        try:
            t0 = time.time()
            assert self._client is not None, "OpenAI client not initialized"
            stream = self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            full_response = ""
            for chunk in stream:
                if not isinstance(chunk, ChatCompletionChunk):
                    continue
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta is None:
                    continue
                token = delta.content or (getattr(delta, 'reasoning_content', '') if not self._is_reasoning_model else '') or ''
                if token:
                    on_token(token)
                    full_response += token
            elapsed_ms = (time.time() - t0) * 1000
            self._logger.debug(
                "OpenAI-compat stream response: backend=%s model=%s elapsed_ms=%.0f response_len=%d",
                self._backend,
                self._model,
                elapsed_ms,
                len(full_response),
            )
            return full_response
        except LLMConnectionError:
            raise
        except (APITimeoutError, APIConnectionError, AuthenticationError,
                PermissionDeniedError, NotFoundError, RateLimitError,
                InternalServerError, BadRequestError, APIStatusError, APIError) as e:
            code = _classify_openai_error(e) or LLMErrorCode.UNKNOWN
            raise LLMConnectionError(
                message=_ERROR_CODE_MESSAGES.get(code, str(e)),
                code=code,
                detail=str(e),
            ) from e
        except Exception as e:
            raise

    def _chat_openai_compat_stream_with_phase(
        self,
        messages: list[dict[str, Any]],
        on_phase: Callable[[str], None],
        on_token: Callable[[str, str], None],
        temperature: float,
        max_tokens: int,
    ) -> str:
        self._logger.debug(
            "OpenAI-compat stream with phase: backend=%s model=%s temperature=%.2f max_tokens=%d",
            self._backend, self._model, temperature, max_tokens,
        )
        try:
            t0 = time.time()
            assert self._client is not None, "OpenAI client not initialized"
            stream = self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            full_response = ""
            content_only = ""
            current_phase: str | None = None
            for chunk in stream:
                if not isinstance(chunk, ChatCompletionChunk):
                    continue
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                reasoning = getattr(delta, 'reasoning_content', None) or ''
                content = delta.content or ''

                if reasoning and self._is_reasoning_model:
                    if current_phase != "thinking":
                        current_phase = "thinking"
                        on_phase("thinking")
                    token = reasoning
                elif content:
                    if current_phase != "output":
                        current_phase = "output"
                        on_phase("output")
                    token = content
                    content_only += content
                elif reasoning and not self._is_reasoning_model:
                    if current_phase != "output":
                        current_phase = "output"
                        on_phase("output")
                    token = reasoning
                    content_only += reasoning
                else:
                    continue

                if current_phase is not None:
                    on_token(token, current_phase)
                full_response += token
            elapsed_ms = (time.time() - t0) * 1000
            self._logger.debug(
                "OpenAI-compat stream with phase done: backend=%s model=%s elapsed_ms=%.0f response_len=%d",
                self._backend, self._model, elapsed_ms, len(full_response),
            )
            return content_only if (self._is_reasoning_model and content_only) else full_response
        except LLMConnectionError:
            raise
        except (APITimeoutError, APIConnectionError, AuthenticationError,
                PermissionDeniedError, NotFoundError, RateLimitError,
                InternalServerError, BadRequestError, APIStatusError, APIError) as e:
            code = _classify_openai_error(e) or LLMErrorCode.UNKNOWN
            raise LLMConnectionError(
                message=_ERROR_CODE_MESSAGES.get(code, str(e)),
                code=code,
                detail=str(e),
            ) from e
        except Exception as e:
            raise
