"""ASSEF 红蓝对抗竞技场 —— 回合制攻击/防御/评估引擎"""

from __future__ import annotations

import datetime
import re
import threading
import time
import traceback
from dataclasses import asdict
from typing import Callable

from ..logging_config import get_logger
from ..judge import ConstitutionJudge
from ..judge import Judge
from ..judge.event_collector import EventCollector, EventType
from ..judge.judge import _execute_in_sandbox
from ..models import TargetSpec
from ..agents import RedTeamAgent
from ..agents import BlueTeamAgent
from ..models import GameRules
from ..models import RoundRecord, ArenaResult, ArenaReport
from ..core.progress import ProgressEvent, ProgressDispatcher
from ..recorder import get_prompt_recorder

_logger = get_logger("arena")


def _strip_main_block(code: str) -> str:
    stripped = re.split(r'\nif\s+__name__\s*==\s*["\']__main__["\']\s*:', code, maxsplit=1)
    return stripped[0].rstrip()


class Arena:
    """红蓝对抗竞技场：回合制攻击/防御循环，宪法判官评估"""

    def __init__(
        self,
        judge: ConstitutionJudge,
        red_team: RedTeamAgent,
        blue_team: BlueTeamAgent,
        rules: GameRules | None = None,
    ) -> None:
        self._judge = judge
        self._red_team = red_team
        self._blue_team = blue_team
        self._rules = rules or GameRules()
        self._feedback_judge = Judge()
        self._event_collector = EventCollector()

    def _evaluate_attack_success(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        timed_out: bool,
        elapsed: float,
        target: TargetSpec,
    ) -> bool:
        judge_script = self._judge.judge_script
        if not judge_script:
            return target.success_criteria.attack in stdout

        exec_result: dict[str, object] = {
            "name": "attack_execution",
            "input": {},
            "expected_output": None,
            "actual_output": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "elapsed_time": elapsed,
        }

        import json as _json, re as _re
        from typing import Optional as _Optional
        local_env: dict = {}
        try:
            exec(judge_script, {"__builtins__": __builtins__, "json": _json, "re": _re, "Optional": _Optional}, local_env)
            judge_func = local_env.get("judge")
            if judge_func:
                try:
                    result = judge_func([exec_result])
                    if result is not None:
                        return bool(result.get("attack_success", False))
                except TypeError:
                    try:
                        result = judge_func([exec_result], 0, 0)
                        if result is not None:
                            return bool(result.get("attack_success", False))
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception as e:
            _logger.warning("Attack eval via judge script failed: %s", e)

        _logger.debug("Judge script evaluation fallback: checking stdout for flag patterns, stdout_len=%d", len(stdout))
        return "flag{" in stdout.lower() or target.success_criteria.attack in stdout

    def run(
        self,
        target: TargetSpec,
        max_rounds: int | None = None,
        on_progress: Callable[[ProgressEvent], None] | None = None,
        cancel_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
        on_llm_progress: Callable[[str, str, int], None] | None = None,
    ) -> ArenaResult:
        rounds_limit = max_rounds or self._rules.max_arena_rounds
        _logger.info("竞技场开始: target=%s, max_rounds=%d", target.name, rounds_limit)

        attack_blood_bank: list[dict] = []
        defense_code = target.code
        original_code_len = len(target.code.splitlines())

        rounds: list[RoundRecord] = []
        red_score = 0.0
        blue_score = 0.0

        if on_progress is not None:
            constitution_info = self._judge.get_constitution_info()
            on_progress(ProgressEvent(type="info", role="arena", step_name="constitution_intro",
                data={
                    "target_name": target.name,
                    "attack_success_criteria": constitution_info.get("attack_success_criteria", ""),
                    "target_code_summary": target.code[:300],
                    "target_code": target.code,
                },
                content=f"攻击目标: {target.name}\n判定标准: {constitution_info.get('attack_success_criteria', '')[:200]}"))

        if on_progress is not None:
            on_progress(ProgressEvent(type="step_start", role="judge", step_name="setup_judge",
                data={}, content="正在生成判官判词脚本..."))
        self._judge.ensure_script(on_progress=on_progress, on_llm_progress=on_llm_progress)
        recorder = get_prompt_recorder()
        if recorder is not None:
            recorder.update_useful_by_context(None, "constitution_judge", True)
        if on_progress is not None:
            on_progress(ProgressEvent(type="step_done", role="judge", step_name="setup_judge",
                data={}, content="判词脚本已就绪"))

        for round_num in range(1, rounds_limit + 1):
            _logger.info("=== 第 %d/%d 回合开始 ===", round_num, rounds_limit)
            if cancel_event is not None and cancel_event.is_set():
                _logger.info("竞技场在第 %d 回合前收到取消信号，停止执行", round_num)
                break

            if pause_event is not None:
                pause_event.wait()

            if on_progress is not None:
                on_progress(ProgressEvent(type="step_start", role="arena", step_name="round", data={"round_num": round_num, "total_rounds": rounds_limit}))

            if pause_event is not None:
                pause_event.wait()

            # ============================================================
            # 阶段 1: 红队生成攻击脚本
            # ============================================================
            attack_script = self._red_team.generate_attack(
                target, rounds,
                on_progress=on_progress,
                pause_event=pause_event,
                on_llm_progress=on_llm_progress,
            )
            _logger.info("第 %d 回合: 攻击脚本长度=%d", round_num, len(attack_script))

            self._event_collector.collect(
                EventType.ATTACK_GENERATED, round_num, "red_team",
                {"script_len": len(attack_script)},
            )

            if not attack_script or not attack_script.strip():
                _logger.warning("第 %d 回合: 攻击脚本为空或无效，本轮攻击跳过", round_num)
                record = RoundRecord(
                    round_num=round_num,
                    attack_script="",
                    successful_attacks=[],
                    attack_success=False,
                    attack_output="攻击脚本生成失败：LLM 返回了空内容或无效代码",
                    defense_code=defense_code,
                    defense_passed=False,
                    eval_red=False,
                    eval_yellow=True,
                    eval_green=False,
                    cost_score=0.0,
                    blue_retries=0,
                )
                rounds.append(record)
                continue

            if cancel_event is not None and cancel_event.is_set():
                _logger.info("竞技场在攻击生成后收到取消信号，停止执行")
                break

            if pause_event is not None:
                pause_event.wait()

            # ============================================================
            # 阶段 2: 在沙箱中执行联合代码（防御代码 + 攻击脚本）
            # ============================================================
            combined_code = _strip_main_block(defense_code) + "\n\n" + attack_script
            stdout, stderr, exit_code, timed_out, elapsed = _execute_in_sandbox(combined_code, {})

            sandbox_logs = [{
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "timed_out": timed_out,
                "elapsed_time": elapsed,
            }]

            _logger.info(
                "第 %d 回合沙箱执行: exit_code=%d, timed_out=%s, stdout_len=%d, stderr_len=%d, elapsed=%.3f",
                round_num, exit_code, timed_out, len(stdout), len(stderr), elapsed,
            )

            self._event_collector.collect(
                EventType.SANDBOX_EXECUTED, round_num, "sandbox",
                {"exit_code": exit_code, "timed_out": timed_out, "elapsed": elapsed, "stdout_len": len(stdout)},
            )

            if on_progress is not None:
                on_progress(ProgressEvent(type="info", role="arena", step_name="sandbox_exec",
                    content=f"沙箱执行攻击脚本: exit_code={exit_code}, elapsed={elapsed:.2f}s",
                    data={"stdout": stdout[:500], "stderr": stderr[:500], "exit_code": exit_code, "timed_out": timed_out, "elapsed_time": elapsed}))

            # ============================================================
            # 阶段 3: 判定攻击是否成功
            # ============================================================
            attack_success = self._evaluate_attack_success(
                stdout, stderr, exit_code, timed_out, elapsed, target,
            )

            recorder = get_prompt_recorder()
            if recorder is not None:
                recorder.update_useful_by_context(round_num, "red_team", attack_success)

            _logger.info("第 %d 回合攻击判定: attack_success=%s", round_num, attack_success)

            self._event_collector.collect(
                EventType.ATTACK_JUDGED, round_num, "judge",
                {"attack_success": attack_success},
            )

            if cancel_event is not None and cancel_event.is_set():
                _logger.info("竞技场在攻击判定后收到取消信号，停止执行")
                break

            # ============================================================
            # 阶段 4: 构建攻击产出
            # ============================================================
            attack_output = ""
            successful_attack_inputs: list[dict] = []
            if attack_success:
                attack_output = stdout[:500] if stdout else stderr[:500]
                successful_attack_inputs = [{
                    "attack_script": attack_script[:1000],
                    "attack_output": attack_output,
                }]

            # ============================================================
            # 阶段 5: 红队得分
            # ============================================================
            if attack_success:
                red_score += 10.0
                attack_blood_bank.append(successful_attack_inputs[0])
                _logger.info("第 %d 回合红队得分: +10, red_score=%.1f", round_num, red_score)

            # ============================================================
            # 阶段 6: 蓝队阶段
            # ============================================================
            final_code: str | None = None
            iterations: int = 0
            all_normal_passed: bool = False
            blue_retries: int = 0

            if pause_event is not None:
                pause_event.wait()

            if attack_success:
                if on_progress is not None:
                    on_progress(ProgressEvent(type="step_start", role="arena", step_name="try_defense", data={"round_num": round_num, "mode": "fix"}))
                final_code, iterations, all_normal_passed = self._blue_team.generate_fix_with_feedback(
                    target,
                    self._feedback_judge,
                    max_iterations=None,
                    attack_inputs=successful_attack_inputs,
                    blood_bank=attack_blood_bank,
                    attack_script=attack_script,
                    sandbox_logs=sandbox_logs,
                    on_progress=on_progress,
                    pause_event=pause_event,
                )
            else:
                if on_progress is not None:
                    on_progress(ProgressEvent(type="step_start", role="arena", step_name="try_defense", data={"round_num": round_num, "mode": "enhance"}))
                final_code, iterations, all_normal_passed = self._blue_team.generate_enhance_with_feedback(
                    target,
                    self._feedback_judge,
                    max_iterations=None,
                    attack_script=attack_script,
                    sandbox_logs=sandbox_logs,
                    blood_bank=attack_blood_bank,
                    on_progress=on_progress,
                    pause_event=pause_event,
                )

            blue_retries = iterations - 1 if iterations > 1 else 0
            _logger.info(
                "第 %d 回合蓝队: iterations=%d, all_normal_passed=%s, code_len=%d",
                round_num, iterations, all_normal_passed, len(final_code) if final_code else 0,
            )

            self._event_collector.collect(
                EventType.DEFENSE_GENERATED, round_num, "blue_team",
                {"iterations": iterations, "code_len": len(final_code) if final_code else 0},
            )

            if cancel_event is not None and cancel_event.is_set():
                _logger.info("竞技场在蓝队执行后收到取消信号，停止执行")
                break

            # ============================================================
            # 阶段 7: 蓝队评分
            # ============================================================
            defense_passed = False
            cost_score = 0.0

            if final_code:
                current_code_len = len(final_code.splitlines())
                defense_report = self._judge.judge_defense(
                    final_code,
                    successful_attack_inputs,
                    original_code_len,
                    current_code_len,
                    on_progress=on_progress,
                )
                defense_passed = defense_report.defense_passed
                cost_score = defense_report.cost_score

                self._event_collector.collect(
                    EventType.DEFENSE_EVALUATED, round_num, "judge",
                    {"defense_passed": defense_passed, "cost_score": cost_score},
                )

                normal_details = [d for d in defense_report.details if d.test_name.startswith("normal_")]
                all_normal_failed = len(normal_details) > 0 and all(not d.passed for d in normal_details)

                if attack_success and all_normal_failed:
                    blue_score -= 10.0
                    _logger.warning(
                        "第 %d 回合重罚: 攻击成功且所有正常测试失败, blue_score=%.1f",
                        round_num, blue_score,
                    )
                elif defense_passed:
                    blue_score += 15.0 * cost_score
                    _logger.info(
                        "第 %d 回合蓝队得分: +%.1f (cost_score=%.3f), blue_score=%.1f",
                        round_num, 15.0 * cost_score, cost_score, blue_score,
                    )
                    defense_code = final_code
            else:
                blue_score -= 5.0
                _logger.warning("第 %d 回合蓝队未提交代码: -5", round_num)

            self._event_collector.collect(
                EventType.SCORE_UPDATED, round_num, "arena",
                {"red_score": red_score, "blue_score": blue_score, "round_num": round_num},
            )

            recorder = get_prompt_recorder()
            if recorder is not None:
                recorder.update_useful_by_context(round_num, "blue_team", defense_passed)

            # ============================================================
            # 阶段 8: 记录回合
            # ============================================================
            record = RoundRecord(
                round_num=round_num,
                attack_script=attack_script,
                successful_attacks=successful_attack_inputs,
                attack_success=attack_success,
                attack_output=attack_output,
                defense_code=final_code,
                defense_passed=defense_passed,
                eval_red=attack_success,
                eval_yellow=not attack_success,
                eval_green=defense_passed,
                cost_score=cost_score,
                blue_retries=blue_retries,
            )

            rounds.append(record)

            # ============================================================
            # 进度事件
            # ============================================================
            if on_progress is not None:
                on_progress(ProgressEvent(type="step_done", role="arena", step_name="try_defense", data={
                    "round_num": round_num,
                    "defense_passed": defense_passed,
                    "mode": "fix" if attack_success else "enhance",
                }))
                on_progress(ProgressEvent(type="step_done", role="arena", step_name="round", data={
                    "round_num": round_num,
                    "attack_success": attack_success,
                }))
                on_progress(ProgressEvent(type="score_update", role="arena", step_name="round", data={
                    "red_score": red_score,
                    "blue_score": blue_score,
                    "round_num": round_num,
                    "attack_success": attack_success,
                    "defense_passed": defense_passed,
                    "cost_score": cost_score,
                    "successful_attack_count": len(successful_attack_inputs),
                }))

            _logger.info("=== 第 %d 回合结束: attack_success=%s, red=%.1f, blue=%.1f ===", round_num, attack_success, red_score, blue_score)

            self._event_collector.collect(
                EventType.ROUND_ENDED, round_num, "arena",
                {"attack_success": attack_success, "defense_passed": defense_passed, "cost_score": cost_score},
            )

        _logger.info(
            "竞技场结束: total_rounds=%d, red_score=%.1f, blue_score=%.1f",
            len(rounds), red_score, blue_score,
        )
        self._event_collector.collect(
            EventType.ARENA_FINISHED, 0, "arena",
            {"total_rounds": len(rounds), "final_red_score": round(red_score, 1), "final_blue_score": round(blue_score, 1)},
        )
        result = ArenaResult(
            target_name=target.name,
            total_rounds=len(rounds),
            red_score=round(red_score, 1),
            blue_score=round(blue_score, 1),
            rounds=rounds,
        )
        result.events = self._event_collector.get_timeline()

        # 生成 AI 分析报告
        import json as _json
        from pathlib import Path

        judge_summary_logger = get_logger("judge_summary")
        try:
            constitution_info = self._judge.get_constitution_info()
            constitution_text = _json.dumps(constitution_info, ensure_ascii=False, indent=2)
            report_text = self._judge.generate_summary_report(
                target_name=target.name,
                constitution_text=constitution_text,
                arena_result_dict=asdict(result),
                events=result.events,
            )
            timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")

            report = ArenaReport(
                target_name=target.name,
                generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                total_rounds=result.total_rounds,
                red_score=result.red_score,
                blue_score=result.blue_score,
                report_text=report_text,
            )

            # 保存报告到 history 目录
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            history_dir = project_root / "history"
            history_dir.mkdir(parents=True, exist_ok=True)
            report_filename = f"report_{target.name}_{timestamp}.json"
            report_path = history_dir / report_filename
            with open(report_path, "w", encoding="utf-8") as f:
                _json.dump(asdict(report), f, ensure_ascii=False, indent=2)

            result.report_path = str(report_path)
            judge_summary_logger.info("报告已生成: %s", report_path)
        except Exception as e:
            judge_summary_logger.error("报告生成失败: %s", e)
            result.report_path = ""

        return result


def run_arena_async(
    arena: Arena,
    target: TargetSpec,
    max_rounds: int | None,
    shared_state: dict,
    cancel_event: threading.Event,
) -> None:
    if cancel_event.is_set():
        shared_state["_arena_finished"] = True
        return

    dispatcher = ProgressDispatcher()

    def _on_progress(event: ProgressEvent) -> None:
        shared_state.setdefault("_arena_progress_events", [])
        shared_state["_arena_progress_events"].append(event)

        if event.type in ("step_start", "step_done"):
            entry = {
                "time": datetime.datetime.now().strftime("%H:%M:%S"),
                "role": event.role,
                "html": f"<span>{event.role}/{event.step_name} {event.type}</span>",
            }
            shared_state.setdefault("_arena_log_stream", [])
            shared_state["_arena_log_stream"].append(entry)

        if event.type == "step_done":
            if event.role == "red_team" and event.step_name == "generate_attack":
                shared_state["_arena_current_attack_plans"] = event.data
            elif event.role == "judge" and event.step_name == "judge_attack":
                shared_state["_arena_attack_success"] = event.data.get("attack_success", False)
            elif event.role == "arena" and event.step_name == "try_defense":
                shared_state["_arena_defense_result"] = event.data
            elif event.role == "arena" and event.step_name == "round":
                shared_state["_arena_completed_rounds"] = shared_state.get("_arena_completed_rounds", 0) + 1

    dispatcher.register(_on_progress)

    try:
        result = arena.run(target, max_rounds, on_progress=dispatcher.dispatch, cancel_event=cancel_event)
        shared_state["_arena_result"] = result
    except Exception as e:
        shared_state["_arena_error"] = {
            "message": str(e),
            "detail": traceback.format_exc(),
        }
    finally:
        shared_state["_arena_finished"] = True
