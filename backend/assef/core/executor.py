"""后台线程池执行器模块 —— 单例 BackgroundExecutor 支持任务的取消/暂停/恢复状态机

通过 ThreadPoolExecutor 管理并发任务，每项任务持有独立的取消和暂停事件，
支持通过 task_id 精确控制任务生命周期。
"""

from __future__ import annotations

import threading
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, TypeVar, cast

T = TypeVar("T")


class BackgroundExecutor:
    """后台线程池单例执行器，支持任务的取消/暂停/恢复状态机

    使用双检锁模式实现线程安全的单例，基于 ThreadPoolExecutor 管理并发任务。
    每个提交的任务被赋予唯一的 task_id，通过 cancel_event/pause_event 实现精确的生命周期控制。

    Attributes:
        _instance: 单例实例
        _lock: 单例创建锁
    """
    _instance: BackgroundExecutor | None = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, max_workers: int = 3) -> BackgroundExecutor:
        """双检锁单例创建

        Args:
            max_workers: 线程池最大工作线程数（仅首次创建时生效）

        Returns:
            单例 BackgroundExecutor 实例
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, max_workers: int = 3) -> None:
        """初始化线程池和任务管理数据结构（仅首次调用时生效）

        Args:
            max_workers: 线程池最大工作线程数
        """
        if getattr(self, "_initialized", False):
            return
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: dict[str, dict] = {}
        self._tasks_lock = threading.Lock()
        self._initialized = True

    def submit_task(self, task_id: str, task_type: str, func: Callable[..., T], *args: Any) -> dict:
        """提交一个可被追踪和控制的异步任务

        若 task_id 已存在且正在运行或暂停中，直接返回当前状态而不重复提交。
        任务执行过程中可通过 cancel_event/pause_event 进行取消或暂停控制。

        Args:
            task_id: 任务唯一标识
            task_type: 任务类型字符串
            func: 任务执行函数
            *args: 任务函数的参数

        Returns:
            任务状态字典，包含 task_id/task_type/status/error/started_at 字段
        """
        with self._tasks_lock:
            if task_id in self._tasks:
                existing = self._tasks[task_id]
                if existing["status"] in ("running", "paused"):
                    return self._build_status(task_id)
                del self._tasks[task_id]

            cancel_event = threading.Event()
            pause_event = threading.Event()
            pause_event.set()

            task_state = {
                "task_id": task_id,
                "task_type": task_type,
                "status": "running",
                "error": None,
                "started_at": time.time(),
                "_cancel_event": cancel_event,
                "_pause_event": pause_event,
                "_future": None,
            }
            self._tasks[task_id] = task_state

        def run_wrapper(*w_args: Any) -> None:
            try:
                func(*w_args)
                with self._tasks_lock:
                    if task_id in self._tasks:
                        t = self._tasks[task_id]
                        if t["status"] not in ("cancelled", "error"):
                            t["status"] = "completed"
            except Exception as e:
                with self._tasks_lock:
                    if task_id in self._tasks:
                        t = self._tasks[task_id]
                        if t["status"] != "cancelled":
                            t["status"] = "error"
                            t["error"] = {
                                "message": str(e),
                                "detail": traceback.format_exc(),
                            }

        future = self._executor.submit(run_wrapper, *args)
        with self._tasks_lock:
            if task_id in self._tasks:
                self._tasks[task_id]["_future"] = future

        return self._build_status(task_id)

    def submit_single(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> Future[T]:
        """提交一个简单的异步任务并返回 Future 对象

        使用固定的 "_single" 作为 task_id，不支持暂停控制。
        用于不需要任务追踪的轻量级异步调用。

        Args:
            func: 任务执行函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            关联的 Future 对象
        """
        task_id = "_single"

        with self._tasks_lock:
            if task_id in self._tasks:
                existing = self._tasks[task_id]
                if existing["status"] in ("running", "paused"):
                    return existing["_future"]
                del self._tasks[task_id]

            cancel_event = threading.Event()
            pause_event = threading.Event()
            pause_event.set()

            task_state = {
                "task_id": task_id,
                "task_type": "single",
                "status": "running",
                "error": None,
                "started_at": time.time(),
                "_cancel_event": cancel_event,
                "_pause_event": pause_event,
                "_future": None,
            }
            self._tasks[task_id] = task_state

        def wrapper(*w_args: Any, **w_kwargs: Any) -> T:
            try:
                return func(*w_args, **w_kwargs)
            except Exception as e:
                with self._tasks_lock:
                    if task_id in self._tasks:
                        self._tasks[task_id]["error"] = {
                            "message": str(e),
                            "detail": traceback.format_exc(),
                        }
                raise

        def run_wrapper(*w_args: Any, **w_kwargs: Any) -> None:
            try:
                wrapper(*w_args, **w_kwargs)
                with self._tasks_lock:
                    if task_id in self._tasks:
                        t = self._tasks[task_id]
                        if t["status"] not in ("cancelled", "error"):
                            t["status"] = "completed"
            except Exception:
                with self._tasks_lock:
                    if task_id in self._tasks:
                        t = self._tasks[task_id]
                        if t["status"] != "cancelled":
                            t["status"] = "error"

        future: Future[T] = cast(Future[T], self._executor.submit(run_wrapper, *args, **kwargs))
        with self._tasks_lock:
            if task_id in self._tasks:
                self._tasks[task_id]["_future"] = future

        return future

    def pause_task(self, task_id: str) -> bool:
        """暂停指定的任务

        将任务状态从 running 切换为 paused，清除暂停事件以阻塞任务执行。

        Args:
            task_id: 任务唯一标识

        Returns:
            操作是否成功（任务不存在或状态不允许时返回 False）
        """
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task is None or task["status"] != "running":
                return False
            task["status"] = "paused"
            task["_pause_event"].clear()
        return True

    def resume_task(self, task_id: str) -> bool:
        """恢复暂停的任务

        将任务状态从 paused 切换为 running，设置暂停事件以释放阻塞。

        Args:
            task_id: 任务唯一标识

        Returns:
            操作是否成功（任务不存在或状态不允许时返回 False）
        """
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task is None or task["status"] != "paused":
                return False
            task["status"] = "running"
            task["_pause_event"].set()
        return True

    def cancel_task(self, task_id: str) -> bool:
        """取消指定的任务

        设置取消事件和暂停事件以通知任务停止，同时尝试取消关联的 Future。

        Args:
            task_id: 任务唯一标识

        Returns:
            操作是否成功（任务不存在或已结束时返回 False）
        """
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task is None or task["status"] not in ("running", "paused"):
                return False
            task["status"] = "cancelled"
            task["_cancel_event"].set()
            task["_pause_event"].set()
            future = task.get("_future")
            if future is not None and not future.done():
                future.cancel()
        return True

    def cancel(self) -> None:
        """取消所有正在运行或暂停的任务"""
        with self._tasks_lock:
            for task_id in list(self._tasks.keys()):
                task = self._tasks[task_id]
                if task["status"] in ("running", "paused"):
                    task["status"] = "cancelled"
                    task["_cancel_event"].set()
                    task["_pause_event"].set()
                    future = task.get("_future")
                    if future is not None and not future.done():
                        future.cancel()

    def get_task_status(self, task_id: str) -> dict | None:
        """获取指定任务的状态快照

        Args:
            task_id: 任务唯一标识

        Returns:
            任务状态字典，任务不存在时返回 None
        """
        with self._tasks_lock:
            if task_id not in self._tasks:
                return None
        return self._build_status(task_id)

    def get_all_tasks(self) -> list[dict]:
        """获取所有任务的状态快照列表

        Returns:
            任务状态字典列表
        """
        with self._tasks_lock:
            return [self._build_status(tid) for tid in self._tasks]

    def _build_status(self, task_id: str) -> dict:
        """构建任务状态快照字典（内部使用，不含控制事件等内部字段）

        Args:
            task_id: 任务唯一标识

        Returns:
            包含 task_id/task_type/status/error/started_at 的状态字典
        """
        task = self._tasks.get(task_id)
        if task is None:
            return {
                "task_id": task_id,
                "task_type": "",
                "status": "unknown",
                "error": None,
                "started_at": 0.0,
            }
        return {
            "task_id": task["task_id"],
            "task_type": task["task_type"],
            "status": task["status"],
            "error": task["error"],
            "started_at": task["started_at"],
        }

    def shutdown(self) -> None:
        """关闭线程池，等待所有已提交任务完成后释放资源"""
        self._executor.shutdown(wait=True, cancel_futures=False)
