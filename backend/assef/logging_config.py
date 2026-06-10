"""模块化日志系统 —— 基于 ModuleFileHandler 按模块路由日志文件

通过 _LOGGER_FILE_MAP 映射将不同模块的日志分别写入对应文件，
同时保留统一的 all.log 汇总日志和控制台输出。
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_logging_initialized = False
_debug_enabled = False
_logs_dir: Path | None = None

_LOGGER_FILE_MAP: dict[str, str] = {
    "assef.arena": "arena/arena",
    "assef.benchmark": "arena/benchmark",
    "assef.llm": "llm/llm_client",
    "assef.judge": "judge/judge",
    "assef.constitution_judge": "judge/constitution_judge",
    "assef.constitution_agent": "judge/constitution_agent",
    "assef.judge_summary": "judge/judge_summary",
    "assef.red_team": "agents/red_team",
    "assef.blue_team": "agents/blue_team",
    "assef.sandbox": "sandbox/sandbox",
    "assef.api.server": "api/server",
    "assef.api.arena": "api/arena",
    "assef.config": "models/config",
}


class ModuleFileHandler(logging.Handler):
    """按 logger 名称路由到对应日志文件的处理器

    根据 _LOGGER_FILE_MAP 映射表，将不同模块的日志写入不同的子目录文件中。
    未匹配的模块统一写入 other/other.log。
    """
    def __init__(self, logs_dir: Path, fmt: logging.Formatter):
        """初始化模块日志处理器

        Args:
            logs_dir: 日志根目录
            fmt: 日志格式化器
        """
        super().__init__()
        self._logs_dir = logs_dir
        self._fmt = fmt

    def _resolve_path(self, name: str) -> Path:
        """根据 logger 名称解析对应的日志文件路径

        先在 _LOGGER_FILE_MAP 中精确匹配，再按前缀匹配。
        未匹配的模块统一路由到 other/other.log。

        Args:
            name: logger 全限定名称

        Returns:
            对应日志文件的 Path 对象
        """
        rel = _LOGGER_FILE_MAP.get(name)
        if rel is None:
            for prefix, path in _LOGGER_FILE_MAP.items():
                if name == prefix or name.startswith(prefix + "."):
                    rel = path
                    break
        if rel is None:
            rel = "other/other"
        return self._logs_dir / f"{rel}.log"

    def emit(self, record: logging.LogRecord) -> None:
        """写入一条日志记录到对应的模块日志文件

        自动创建子目录，异常时调用 handleError 进行容错处理。

        Args:
            record: 日志记录对象
        """
        try:
            log_path = self._resolve_path(record.name)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(self._fmt.format(record) + "\n")
        except Exception:
            self.handleError(record)


def setup_logging(debug: bool = False) -> None:
    """初始化 ASSEF 日志系统

    设置根 logger "assef" 的级别和处理器：控制台输出 + 模块路由文件 + all.log 汇总。
    仅首次调用时完成完整初始化，后续调用仅用于切换 debug 级别。

    Args:
        debug: 是否启用 DEBUG 级别（控制台也输出 DEBUG）
    """
    global _logging_initialized, _debug_enabled, _logs_dir

    if _logging_initialized and not (debug and not _debug_enabled):
        return

    project_root = Path(__file__).resolve().parent.parent.parent
    _logs_dir = project_root / "backend" / "logs"
    all_log = _logs_dir / "all.log"

    root_logger = logging.getLogger("assef")
    root_logger.propagate = False

    fmt = logging.Formatter(
        "[%(asctime)s.%(msecs)03d] [%(levelname)-7s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s",
        datefmt="%H:%M:%S",
    )

    if not _logging_initialized:
        root_logger.setLevel(logging.DEBUG)

        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.DEBUG if debug else logging.WARNING)
        console_handler.setFormatter(fmt)
        root_logger.addHandler(console_handler)

        _logs_dir.mkdir(parents=True, exist_ok=True)

        module_handler = ModuleFileHandler(_logs_dir, fmt)
        module_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(module_handler)

        all_handler = logging.FileHandler(str(all_log), encoding="utf-8")
        all_handler.setLevel(logging.DEBUG)
        all_handler.setFormatter(fmt)
        root_logger.addHandler(all_handler)

        _logging_initialized = True
    else:
        root_logger.setLevel(logging.DEBUG)
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setLevel(logging.DEBUG)

    _debug_enabled = debug


def get_logger(name: str) -> logging.Logger:
    """获取 ASSEF 模块日志记录器

    若日志系统尚未初始化，自动从 ASSEF_DEBUG 环境变量读取 debug 配置并完成初始化。
    自动为名称添加 "assef." 前缀（若未以 "assef." 开头）。

    Args:
        name: 模块名称（如 "llm"/"judge"/"arena"）

    Returns:
        配置完成的 Logger 实例
    """
    if not _logging_initialized:
        debug_env = os.environ.get("ASSEF_DEBUG", "").strip()
        debug = debug_env.lower() in ("1", "true", "yes")
        setup_logging(debug=debug)
    if not name.startswith("assef."):
        name = f"assef.{name}"
    return logging.getLogger(name)
