"""ASSEF 基准测试路由 —— 提供多靶机、多模型批量安全性修复评估接口

路由前缀: /api/benchmark
- POST /api/benchmark/start —— 对指定靶机和 LLM 后端组合批量执行修复测试

基准测试流程：
1. 根据请求参数筛选靶机和后端
2. 对每个 (靶机, 后端) 组合调用蓝队修复
3. 对修复结果进行裁判评估（正常测试通过率、代码膨胀率）
4. 通过 WebSocket 实时推送进度
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel

from ..agents import BlueTeamAgent
from ..arena.benchmark import BenchmarkRunner
from ..core.executor import BackgroundExecutor
from ..core.progress import ProgressDispatcher, ProgressEvent
from ..history import save_benchmark_result
from ..judge import Judge
from ..llm import LLMClient
from ..models.config import build_target_spec_from_config, load_config
from ..models.benchmark_result import BenchmarkResult, ModelScore
from ..models.target_spec import TargetSpec

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_CONFIG_DEFAULT_PATH = _PROJECT_ROOT / "config.default.json"
_CONFIG_JSON_PATH = _PROJECT_ROOT / "config.json"

_task_dispatchers: dict[str, ProgressDispatcher] = {}

router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])


class BenchmarkRequest(BaseModel):
    target_names: list[str]
    backend_names: list[str]


def _resolve_config_path() -> str:
    """解析配置文件路径，优先使用 config.json，不存在则回退到 config.default.json

    Returns:
        str: 配置文件的绝对路径
    """
    if _CONFIG_JSON_PATH.exists():
        return str(_CONFIG_JSON_PATH)
    return str(_CONFIG_DEFAULT_PATH)


def _run_benchmark(
    runner: BenchmarkRunner,
    targets: list[TargetSpec],
    models: list[LLMClient],
    dispatcher: ProgressDispatcher,
    cancel_event: threading.Event,
    pause_event: threading.Event,
) -> None:
    """在后台线程中执行批量基准测试

    对每个 (靶机, LLM 客户端) 组合调用蓝队修复并评估结果，
    通过 ProgressDispatcher 实时推送进度事件。

    Args:
        runner: BenchmarkRunner 实例（含 Judge 裁判）
        targets: 靶机规格列表
        models: LLM 客户端列表
        dispatcher: 进度事件分发器
        cancel_event: 取消事件（set 时中止剩余测试）
        pause_event: 暂停事件（clear 时挂起执行）
    """
    total = len(targets) * len(models)
    completed = 0
    benchmark_results: list[BenchmarkResult] = []

    for target in targets:
        if cancel_event.is_set():
            break
        pause_event.wait()

        scores: list[ModelScore] = []
        for model in models:
            if cancel_event.is_set():
                break
            pause_event.wait()

            agent = BlueTeamAgent(model)
            start = time.perf_counter()
            fixed_code = agent.generate_fix(target)
            elapsed = time.perf_counter() - start

            report = runner._judge.judge_normal(target, fixed_code)
            pass_rate = report.passed / report.total_tests if report.total_tests > 0 else 0.0

            original_lines = len(target.code.strip().splitlines())
            fixed_lines = len(fixed_code.strip().splitlines())
            bloat_ratio = fixed_lines / original_lines if original_lines > 0 else 1.0

            completed += 1

            detail_dicts = [
                {"test_name": d.test_name, "passed": d.passed, "error": d.error}
                for d in report.details
            ]

            score = ModelScore(
                model_name=model._model or model._backend,
                fix_pass_rate=round(pass_rate, 4),
                code_bloat_ratio=round(bloat_ratio, 4),
                avg_time_seconds=round(elapsed, 4),
                details=detail_dicts,
            )
            scores.append(score)

            dispatcher.dispatch(ProgressEvent(
                type="benchmark_progress",
                data={
                    "completed": completed,
                    "total": total,
                    "target_name": target.name,
                    "model_name": model._model or model._backend,
                    "pass_rate": round(pass_rate, 4),
                    "bloat_ratio": round(bloat_ratio, 4),
                    "elapsed_seconds": round(elapsed, 4),
                },
            ))

        if scores:
            benchmark_results.append(BenchmarkResult(target_name=target.name, scores=scores))

    if benchmark_results and not cancel_event.is_set():
        save_benchmark_result(benchmark_results)

    dispatcher.dispatch(ProgressEvent(
        type="task_done",
        data={"completed": completed, "total": total},
    ))


@router.post("/start")
async def start_benchmark(req: BenchmarkRequest) -> dict:
    """启动批量基准测试

    根据请求中的靶机名称列表和后端名称列表筛选组合，
    提交后台批量执行修复评估。

    Args:
        req: 基准测试请求参数（靶机名列表、后端名列表）

    Returns:
        dict: {"task_id": str, "status": "started"}
    """
    config_path = _resolve_config_path()
    config = load_config(config_path)

    targets: list[TargetSpec] = []
    for tc in config.targets:
        if tc.name in req.target_names:
            try:
                targets.append(build_target_spec_from_config(tc))
            except ValueError:
                pass

    models: list[LLMClient] = []
    for backend in config.llm_backends:
        label = f"{backend.backend} — {backend.model}" if backend.model else backend.backend
        if backend.backend in req.backend_names or label in req.backend_names:
            models.append(LLMClient.from_config(backend))

    judge = Judge()
    runner = BenchmarkRunner(judge)

    dispatcher = ProgressDispatcher()
    task_id = f"benchmark_{uuid4().hex[:8]}"
    _task_dispatchers[task_id] = dispatcher

    cancel_event = threading.Event()
    pause_event = threading.Event()
    pause_event.set()

    executor_m = BackgroundExecutor()

    executor_m.submit_task(
        task_id, "benchmark", _run_benchmark,
        runner, targets, models, dispatcher, cancel_event, pause_event,
    )

    with executor_m._tasks_lock:
        if task_id in executor_m._tasks:
            executor_m._tasks[task_id]["_cancel_event"] = cancel_event
            executor_m._tasks[task_id]["_pause_event"] = pause_event

    return {"task_id": task_id, "status": "started"}
