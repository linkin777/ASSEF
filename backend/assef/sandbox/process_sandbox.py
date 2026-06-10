"""ASSEF 进程沙箱 —— 在隔离子进程中安全执行靶机代码"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ..logging_config import get_logger
from ..models.results import SandboxResult

_logger = get_logger("sandbox")

_DANGEROUS_PATTERNS: list[str] = [
    "os.system",
    "subprocess",
    "__import__",
    "eval(",
    "exec(",
    "open(",
    "import socket",
    "import http",
    "import urllib",
    "import ftplib",
    "import requests",
]


class ProcessSandbox:
    """进程级沙箱，在子进程中安全执行靶机代码，并提供超时和危险操作检测。

    Attributes:
        _timeout: 默认执行超时时间（秒）
    """

    def __init__(self, timeout: float = 30.0) -> None:
        """初始化沙箱

        Args:
            timeout: 默认超时时间（秒），单次调用可通过 execute() 的 timeout 参数覆盖
        """
        self._timeout = timeout

    def execute(self, code: str, input_data: dict, timeout: float | None = None) -> SandboxResult:
        """在隔离子进程中执行靶机代码

        Args:
            code: 要执行的 Python 源码
            input_data: 通过 stdin 以 JSON 格式传入的输入数据
            timeout: 本次执行的超时时间（秒），为 None 则使用实例默认值

        Returns:
            SandboxResult: 包含 stdout、stderr、exit_code、timed_out、elapsed_seconds 的执行结果
        """
        _logger.debug("execute 入口: code_length=%d, input_keys=%s", len(code), list(input_data.keys()))

        code_lower = code.lower()
        for pattern in _DANGEROUS_PATTERNS:
            if pattern in code_lower:
                _logger.warning("检测到危险模式: %s", pattern)
                return SandboxResult(
                    stdout="",
                    stderr="SecurityError: dangerous operation detected",
                    exit_code=-1,
                    timed_out=False,
                    elapsed_seconds=0.0,
                    sandbox_output=f"[DENIED] Dangerous pattern '{pattern}' blocked. Code: {len(code)} chars, input: {len(input_data)} keys.",
                )

        effective_timeout = timeout if timeout is not None else self._timeout

        temp_file: Path | None = None
        start_time = time.perf_counter()

        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(code)
                temp_file = Path(f.name)

            json_str = json.dumps(input_data)

            try:
                result = subprocess.run(
                    [sys.executable, str(temp_file)],
                    input=json_str,
                    capture_output=True,
                    text=True,
                    timeout=effective_timeout,
                )
                elapsed = time.perf_counter() - start_time
                _logger.debug("执行完成: exit_code=%d, elapsed_ms=%.2f, timed_out=%s", result.returncode, elapsed * 1000, False)
                return SandboxResult(
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.returncode,
                    timed_out=False,
                    elapsed_seconds=elapsed,
                    sandbox_output=f"[OK] exit_code={result.returncode}, elapsed={elapsed:.4f}s. "
                                  f"Code: {len(code)} chars, input: {len(input_data)} keys. "
                                  f"stdout: {len(result.stdout)} chars, stderr: {len(result.stderr)} chars.",
                )
            except subprocess.TimeoutExpired as te:
                elapsed = time.perf_counter() - start_time
                partial_stdout = te.stdout.decode("utf-8", errors="replace") if te.stdout else ""
                partial_stderr = te.stderr.decode("utf-8", errors="replace") if te.stderr else ""
                rich_stderr = f"TimeoutError: execution exceeded {effective_timeout}s"
                if partial_stderr:
                    rich_stderr += f"\n--- partial stderr ---\n{partial_stderr}"
                _logger.warning("执行超时: timeout=%.1fs, elapsed_ms=%.2f", effective_timeout, elapsed * 1000)
                return SandboxResult(
                    stdout=partial_stdout,
                    stderr=rich_stderr,
                    exit_code=-1,
                    timed_out=True,
                    elapsed_seconds=elapsed,
                    sandbox_output=f"[TIMEOUT] exceeded {effective_timeout}s, elapsed={elapsed:.4f}s. "
                                  f"Code: {len(code)} chars, input: {len(input_data)} keys. "
                                  f"Partial stdout: {len(partial_stdout)} chars, partial stderr: {len(partial_stderr)} chars.",
                )
        except Exception as exc:
            elapsed = time.perf_counter() - start_time
            _logger.error("执行异常: elapsed_ms=%.2f", elapsed * 1000, exc_info=True)
            return SandboxResult(
                stdout="",
                stderr=str(exc),
                exit_code=-1,
                timed_out=False,
                elapsed_seconds=elapsed,
                sandbox_output=f"[ERROR] {type(exc).__name__}: {exc}. "
                              f"Code: {len(code)} chars, input: {len(input_data)} keys, elapsed={elapsed:.4f}s.",
            )
        finally:
            if temp_file is not None and temp_file.exists():
                temp_file.unlink()
