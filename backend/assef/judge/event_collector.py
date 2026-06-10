"""事件收集器模块 —— 收集并管理判官系统运行过程中的所有事件"""

import threading
from datetime import datetime, timezone
from enum import Enum


class EventType(str, Enum):
    """判官系统事件类型"""

    ATTACK_GENERATED = "ATTACK_GENERATED"
    SANDBOX_EXECUTED = "SANDBOX_EXECUTED"
    ATTACK_JUDGED = "ATTACK_JUDGED"
    DEFENSE_GENERATED = "DEFENSE_GENERATED"
    DEFENSE_EVALUATED = "DEFENSE_EVALUATED"
    SCORE_UPDATED = "SCORE_UPDATED"
    ROUND_ENDED = "ROUND_ENDED"
    ARENA_FINISHED = "ARENA_FINISHED"


class EventCollector:
    """线程安全的事件收集器，用于记录判官系统运行过程中的各类事件"""

    def __init__(self) -> None:
        self._events: list[dict] = []
        self._lock = threading.Lock()

    def collect(
        self,
        event_type: str,
        round_num: int,
        role: str,
        data: dict,
        summary: str = "",
    ) -> None:
        """创建一个事件并追加到内部事件列表中

        Args:
            event_type: 事件类型，应为 EventType 中的某个值
            round_num: 事件发生的轮次编号
            role: 事件关联的角色，如 "red_team", "blue_team", "judge", "arena"
            data: 事件携带的附加数据
            summary: 事件的可读摘要
        """
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "round_num": round_num,
            "event_type": event_type,
            "role": role,
            "data": data,
            "summary": summary,
        }
        with self._lock:
            self._events.append(event)

    def get_timeline(self) -> list[dict]:
        """返回按时间戳排序的所有事件"""
        with self._lock:
            return sorted(self._events, key=lambda e: e["timestamp"])

    def get_round_events(self, round_num: int) -> list[dict]:
        """返回指定轮次的所有事件，按时间戳排序"""
        with self._lock:
            return sorted(
                [e for e in self._events if e["round_num"] == round_num],
                key=lambda e: e["timestamp"],
            )

    def clear(self) -> None:
        """清空所有已收集的事件"""
        with self._lock:
            self._events.clear()
