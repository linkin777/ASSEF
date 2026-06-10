"""进度事件系统模块 —— 基于观察者模式的 ProgressEvent/ProgressDispatcher

定义 ProgressEvent 数据模型和 ProgressDispatcher 事件分发器，
支持注册多个回调函数接收分步执行进度、LLM token 输出等事件。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

ProgressCallback = Callable[["ProgressEvent"], None]


@dataclass
class ProgressEvent:
    """进度事件数据模型

    封装单次进度通知的所有信息，支持 step_start/step_done/llm_token/
    llm_thinking/llm_output/judge_test_result/info/error 等事件类型。

    Attributes:
        type: 事件类型字符串
        role: 角色标识（如 red_team/blue_team/judge）
        step_name: 步骤名称
        content: 文本内容（对于 llm_thinking/llm_output 类型，
            包含最新的 token 文本块，用于前端展示）
        data: 附加数据字典（对于 llm_thinking/llm_output 类型，
            应包含 token、cumulative_chars、phase 字段）
        timestamp: 事件时间戳（秒）
    """
    type: str
    role: str = ""
    step_name: str = ""
    content: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        """自动填充时间戳（若未提供）"""
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class ProgressDispatcher:
    """进度事件分发器，基于观察者模式管理多个回调

    支持注册/注销回调函数，所有已注册的回调将在事件发生时同步调用。
    提供便捷的语义化事件发送方法（step_start/step_done/llm_token 等）。
    """
    def __init__(self) -> None:
        """初始化空的回调列表"""
        self._callbacks: list[ProgressCallback] = []

    def register(self, callback: ProgressCallback) -> None:
        """注册进度事件回调函数

        Args:
            callback: 回调函数，接收 ProgressEvent 参数
        """
        self._callbacks.append(callback)

    def unregister(self, callback: ProgressCallback) -> None:
        """注销进度事件回调函数

        Args:
            callback: 已注册的回调函数
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def dispatch(self, event: ProgressEvent) -> None:
        """同步分发进度事件给所有已注册的回调

        每个回调在 try-except 中调用，单个回调异常不会影响其他回调。

        Args:
            event: 进度事件对象
        """
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                pass

    def clear(self) -> None:
        """清空所有已注册的回调函数"""
        self._callbacks.clear()

    def step_start(self, role: str, step_name: str, **extra: Any) -> None:
        """发送步骤开始事件

        Args:
            role: 角色标识
            step_name: 步骤名称
            **extra: 附加数据
        """
        self.dispatch(ProgressEvent(
            type="step_start",
            role=role,
            step_name=step_name,
            data=extra,
        ))

    def step_done(self, role: str, step_name: str, **extra: Any) -> None:
        """发送步骤完成事件

        Args:
            role: 角色标识
            step_name: 步骤名称
            **extra: 附加数据
        """
        self.dispatch(ProgressEvent(
            type="step_done",
            role=role,
            step_name=step_name,
            data=extra,
        ))

    def llm_token(self, role: str, content: str, **extra: Any) -> None:
        """发送 LLM token 输出事件（用于流式输出）

        Args:
            role: 角色标识
            content: token 文本内容
            **extra: 附加数据
        """
        self.dispatch(ProgressEvent(
            type="llm_token",
            role=role,
            content=content,
            data=extra,
        ))

    def llm_thinking(
        self, role: str, token: str, cumulative_chars: int, phase: str,
        **extra: Any,
    ) -> None:
        """发送 LLM 思考 token 事件（用于流式展示推理过程）

        Args:
            role: 角色标识
            token: 当前 token 文本块
            cumulative_chars: 累计字符数
            phase: 当前推理阶段
            **extra: 附加数据
        """
        self.dispatch(ProgressEvent(
            type="llm_thinking",
            role=role,
            content=token,
            data={
                "token": token,
                "cumulative_chars": cumulative_chars,
                "phase": phase,
                **extra,
            },
        ))

    def llm_output(
        self, role: str, token: str, cumulative_chars: int, phase: str,
        **extra: Any,
    ) -> None:
        """发送 LLM 输出 token 事件（用于流式展示最终输出）

        Args:
            role: 角色标识
            token: 当前 token 文本块
            cumulative_chars: 累计字符数
            phase: 当前输出阶段
            **extra: 附加数据
        """
        self.dispatch(ProgressEvent(
            type="llm_output",
            role=role,
            content=token,
            data={
                "token": token,
                "cumulative_chars": cumulative_chars,
                "phase": phase,
                **extra,
            },
        ))

    def judge_test_result(self, test_name: str, passed: bool, **extra: Any) -> None:
        """发送判官测试结果事件

        Args:
            test_name: 测试用例名称
            passed: 是否通过
            **extra: 附加数据
        """
        self.dispatch(ProgressEvent(
            type="judge_test_result",
            data={"test_name": test_name, "passed": passed, **extra},
        ))

    def info(self, role: str, content: str, **extra: Any) -> None:
        """发送信息事件

        Args:
            role: 角色标识
            content: 信息文本
            **extra: 附加数据
        """
        self.dispatch(ProgressEvent(
            type="info",
            role=role,
            content=content,
            data=extra,
        ))

    def error(self, role: str, content: str, **extra: Any) -> None:
        """发送错误事件

        Args:
            role: 角色标识
            content: 错误文本
            **extra: 附加数据
        """
        self.dispatch(ProgressEvent(
            type="error",
            role=role,
            content=content,
            data=extra,
        ))
