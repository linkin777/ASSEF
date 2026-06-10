"""ASSEF 竞技场路由 —— 提供红蓝对抗竞技场的启动与管理接口

路由前缀: /api/arena
- POST /api/arena/start —— 启动一场红蓝对抗（指定靶机、红队/蓝队/裁判的 LLM 后端）

竞技场启动流程：
1. 加载配置并验证请求参数
2. 创建红队/蓝队/裁判的 LLM 客户端
3. 初始化 Arena 实例
4. 通过 BackgroundExecutor 异步执行对抗
5. 返回 task_id 供前端通过 WebSocket 订阅进度
"""

import threading
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..arena import Arena
from ..agents import BlueTeamAgent, RedTeamAgent
from ..core.executor import BackgroundExecutor
from ..core.progress import ProgressEvent, ProgressDispatcher
from ..history import save_arena_result
from ..judge import ConstitutionJudge
from ..llm.llm_client import LLMClient
from ..logging_config import get_logger
from ..recorder import get_prompt_recorder, PromptRecorder
from ..models import (
    Constitution,
    GameRules,
    LLMBackendConfig,
    build_target_spec_from_config,
    load_config,
)

from .routes_benchmark import _task_dispatchers

_logger = get_logger("api.arena")

router = APIRouter(prefix="/api/arena", tags=["arena"])


class ArenaRequest(BaseModel):
    target_name: str
    max_rounds: int = 10
    red_backend_name: str
    blue_backend_name: str
    judge_backend_name: str


def _find_backend_by_name(backends: list[LLMBackendConfig], name: str) -> LLMBackendConfig:
    """根据名称从后端配置列表中查找 LLM 后端

    Args:
        backends: LLM 后端配置列表
        name: 后端名称（与 LLMBackendConfig.backend 字段匹配）

    Returns:
        LLMBackendConfig: 匹配的后端配置

    Raises:
        ValueError: 未找到指定名称的后端配置
    """
    for be in backends:
        if be.backend == name:
            return be
    raise ValueError(f"LLM backend '{name}' not found in config")


def _run_arena(
    arena,
    target,
    max_rounds,
    dispatcher,
    cancel_event,
    pause_event,
):
    """在后台线程中执行竞技场对抗任务

    检查取消状态后调用 Arena.run() 运行多轮红蓝对抗，
    结果通过 ProgressDispatcher 实时推送至前端 WebSocket。

    Args:
        arena: Arena 实例（已配置红队/蓝队/裁判）
        target: 靶机规格对象
        max_rounds: 最大对抗回合数
        dispatcher: 进度事件分发器，用于推送事件至前端
        cancel_event: 线程取消事件（Event），set 时终止对抗
        pause_event: 线程暂停事件（Event），clear 时暂停对抗
    """
    def _dispatch(event):
        pause_event.wait()
        if not cancel_event.is_set():
            dispatcher.dispatch(event)

    if cancel_event.is_set():
        _logger.info("Arena task cancelled before start")
        dispatcher.dispatch(ProgressEvent(type="task_done", data={"result": None, "cancelled": True}))
        return

    _logger.info("Arena starting: target=%s max_rounds=%d", target.name, max_rounds)
    dispatcher.dispatch(ProgressEvent(type="info", role="arena", step_name="setup", content=f"竞技场启动: 靶机={target.name}, 最大回合={max_rounds}"))

    try:
        result = arena.run(target, max_rounds, on_progress=_dispatch, cancel_event=cancel_event, pause_event=pause_event)
        _logger.info("Arena completed: target=%s rounds=%d red=%.1f blue=%.1f",
                     result.target_name, result.total_rounds, result.red_score, result.blue_score)
        save_arena_result(result)
        dispatcher.dispatch(ProgressEvent(type="task_done", data={
            "result": {
                "target_name": result.target_name,
                "total_rounds": result.total_rounds,
                "red_score": result.red_score,
                "blue_score": result.blue_score,
                "target_code": target.code,
                "rounds": [
                    {
                        "round_num": r.round_num,
                        "attack_success": r.attack_success,
                        "defense_passed": r.defense_passed,
                        "defense_code": r.defense_code,
                        "cost_score": r.cost_score,
                        "blue_retries": r.blue_retries,
                    }
                    for r in result.rounds
                ],
            }
        }))
    except Exception as e:
        _logger.error("Arena run failed: %s", e, exc_info=True)
        dispatcher.dispatch(ProgressEvent(
            type="task_done",
            role="arena",
            content=f"任务失败: {e}",
            data={"error": str(e)}
        ))
        dispatcher.dispatch(ProgressEvent(
            type="error",
            role="arena",
            content=f"任务失败: {e}"
        ))


@router.post("/start")
async def start_arena(request: ArenaRequest):
    """启动一场红蓝对抗竞技场

    根据请求参数创建 Arena 实例并提交后台执行。
    返回 task_id 供前端通过 WebSocket（/ws/task/{task_id}）订阅实时进度。

    Args:
        request: 竞技场请求参数（靶机名、最大回合、红/蓝/裁判后端名）

    Returns:
        dict: {"task_id": str, "status": "started"}

    Raises:
        HTTPException: 404 — 指定的靶机名称不存在
        HTTPException: （由 _find_backend_by_name 抛出的 ValueError）
    """
    _logger.info("POST /api/arena/start: target=%s max_rounds=%d red=%s blue=%s judge=%s",
                 request.target_name, request.max_rounds,
                 request.red_backend_name, request.blue_backend_name, request.judge_backend_name)

    config = load_config("config.json")
    _logger.info("Config loaded: targets=%d backends=%d", len(config.targets), len(config.llm_backends))

    target_config = None
    for tc in config.targets:
        if tc.name == request.target_name:
            target_config = tc
            break
    if target_config is None:
        _logger.warning("Target not found: %s", request.target_name)
        raise HTTPException(status_code=404, detail=f"Target '{request.target_name}' not found")

    _logger.info("Building TargetSpec for: %s", request.target_name)
    target = build_target_spec_from_config(target_config)

    red_backend = _find_backend_by_name(config.llm_backends, request.red_backend_name)
    blue_backend = _find_backend_by_name(config.llm_backends, request.blue_backend_name)
    judge_backend = _find_backend_by_name(config.llm_backends, request.judge_backend_name)
    _logger.info("LLM backends resolved: red=%s/%s blue=%s/%s judge=%s/%s",
                 red_backend.backend, red_backend.model,
                 blue_backend.backend, blue_backend.model,
                 judge_backend.backend, judge_backend.model)

    prompt_recorder = get_prompt_recorder()

    def _make_on_call_record(recorder: PromptRecorder):
        def _on_call_record(data: dict) -> None:
            from datetime import datetime

            from ..models.recorder import Metrics, RecordEntry

            call_ctx = data.get("call_context") or {}
            caller = call_ctx.get("caller", "unknown")
            round_num = call_ctx.get("round")
            response = data.get("response", "")

            metrics = PromptRecorder.compute_metrics(response, caller)

            messages_str = str(data.get("messages", []))
            response_str = str(response)

            entry = RecordEntry(
                timestamp=datetime.now().isoformat(),
                caller=caller,
                round=round_num,
                backend=data.get("backend", ""),
                model=data.get("model", ""),
                messages=messages_str[:4000],
                response=response_str[:4000],
                duration_ms=data.get("duration_ms", 0.0),
                metrics=metrics,
            )
            recorder.record(entry)
        return _on_call_record

    if prompt_recorder is not None:
        on_record = _make_on_call_record(prompt_recorder)
        red_llm = LLMClient.from_config(red_backend, on_call_record=on_record)
        blue_llm = LLMClient.from_config(blue_backend, on_call_record=on_record)
        judge_llm = LLMClient.from_config(judge_backend, on_call_record=on_record)
    else:
        red_llm = LLMClient.from_config(red_backend)
        blue_llm = LLMClient.from_config(blue_backend)
        judge_llm = LLMClient.from_config(judge_backend)
    _logger.info("LLM clients created")

    rules = GameRules(
        max_blue_retries=config.game_rules.max_blue_retries,
        performance_degrade_limit=config.game_rules.performance_degrade_limit,
        code_bloat_limit=config.game_rules.code_bloat_limit,
        red_strategy_mutation_threshold=config.game_rules.red_strategy_mutation_threshold,
        max_arena_rounds=config.game_rules.max_arena_rounds,
        self_adversary_attempts=config.game_rules.self_adversary_attempts,
        blue_self_iteration_limit=config.game_rules.blue_self_iteration_limit,
        red_max_plans_early=config.game_rules.red_max_plans_early,
        red_max_plans_late=config.game_rules.red_max_plans_late,
    )

    constitution = Constitution(
        preamble=config.constitution.preamble,
        attack_success_criteria=config.constitution.attack_success_criteria,
        fix_success_criteria=config.constitution.fix_success_criteria,
        scoring_rules=config.constitution.scoring_rules,
        constraints=config.constitution.constraints,
    )

    _logger.info("Initializing arena agents...")
    red_team = RedTeamAgent(red_llm, rules=rules)
    blue_team = BlueTeamAgent(blue_llm)
    sandbox_description = config.sandbox.description if config.sandbox and config.sandbox.description else ""
    constitution_judge = ConstitutionJudge(constitution, target, judge_llm, sandbox_description=sandbox_description)

    arena = Arena(
        judge=constitution_judge,
        red_team=red_team,
        blue_team=blue_team,
        rules=rules,
    )
    _logger.info("Arena instance ready")

    cancel_event = threading.Event()
    pause_event = threading.Event()
    pause_event.set()

    dispatcher = ProgressDispatcher()
    task_id = f"arena_{uuid4().hex[:8]}"
    _task_dispatchers[task_id] = dispatcher
    _logger.info("Task registered: task_id=%s dispatcher_id=%d", task_id, id(dispatcher))

    executor_m = BackgroundExecutor()

    executor_m.submit_task(
        task_id, "arena", _run_arena,
        arena, target, request.max_rounds, dispatcher, cancel_event, pause_event,
    )

    with executor_m._tasks_lock:
        if task_id in executor_m._tasks:
            executor_m._tasks[task_id]["_cancel_event"] = cancel_event
            executor_m._tasks[task_id]["_pause_event"] = pause_event

    _logger.info("Arena task submitted: task_id=%s", task_id)
    return {"task_id": task_id, "status": "started"}
