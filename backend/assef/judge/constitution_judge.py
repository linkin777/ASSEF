"""ASSEF 宪法判官 —— 将宪法规则驱动的判官脚本与沙箱执行集成，实现基于宪法的代码判定"""

from __future__ import annotations

from typing import Callable

from ..llm import LLMClient
from ..logging_config import get_logger
from ..models import Constitution
from ..models.target_spec import TargetSpec
from ..core.progress import ProgressEvent

from .constitution_agent import ConstitutionAgent
from .judge import Judge, VerdictReport
from .report_generator import ReportGenerator

_logger = get_logger("constitution_judge")


class ConstitutionJudge:
    """宪法裁判官 —— 基于宪法生成判官脚本并以此对红蓝代码进行判定

    判官脚本由 ConstitutionAgent 根据宪法和目标上下文动态生成。所有判定均通过该脚本
    进行，确保判定逻辑与宪法规则一致。
    """

    def __init__(self, constitution: Constitution, target: TargetSpec, llm_client: LLMClient, sandbox_description: str = "") -> None:
        self._constitution = constitution
        self._target = target
        self._agent = ConstitutionAgent(llm_client)
        self._report_generator = ReportGenerator(llm_client)
        self._judge = Judge()
        self._script: str | None = None
        self._sandbox_description = sandbox_description

    @property
    def judge_script(self) -> str | None:
        """返回当前已生成的判官脚本（未生成时返回 None）"""
        return self._script

    def ensure_script(self, on_progress=None, on_llm_progress: Callable[[str, str, int], None] | None = None) -> None:
        self._ensure_script(on_progress, on_llm_progress=on_llm_progress)

    def get_constitution_info(self) -> dict:
        return {
            "attack_success_criteria": self._constitution.attack_success_criteria,
            "fix_success_criteria": self._constitution.fix_success_criteria,
            "scoring_rules": self._constitution.scoring_rules,
            "constraints": self._constitution.constraints,
        }

    def generate_summary_report(
        self,
        target_name: str,
        constitution_text: str,
        arena_result_dict: dict,
        events: list[dict],
    ) -> str:
        """基于竞技场结果和事件时间线，通过 LLM 生成结构化的中文分析报告

        Args:
            target_name: 靶机名称
            constitution_text: 宪法规则文本（JSON 格式）
            arena_result_dict: 竞技场结果字典，包含各轮次的攻防记录和最终得分
            events: 收集到的所有事件列表

        Returns:
            LLM 生成的原始报告文本
        """
        return self._report_generator.generate_summary_report(
            target_name=target_name,
            constitution_text=constitution_text,
            arena_result_dict=arena_result_dict,
            events=events,
        )

    def _ensure_script(self, on_progress=None, on_llm_progress: Callable[[str, str, int], None] | None = None) -> None:
        if self._script is None:
            _logger.info("First-time judge script generation triggered")
            self._agent._llm.set_call_context({
                "caller": "constitution_judge",
                "round": None,
            })
            self._script = self._agent.generate_judge_script(self._constitution, self._target, self._sandbox_description, on_llm_progress=on_llm_progress)
            if on_progress is not None:
                on_progress(ProgressEvent(type="info", role="judge", step_name="judge_script_ready",
                    data={"script_content": self._script, "sandbox_description": self._sandbox_description}, content="判官脚本已生成"))

    def judge_attack(self, code: str, attack_inputs: list[dict], on_progress: Callable[[ProgressEvent], None] | None = None, original_code_len: int = 0, new_code_len: int = 0) -> VerdictReport:
        """对攻击代码执行判定

        Args:
            code: 待判定的 Python 代码（靶机代码或蓝队修复代码）
            attack_inputs: 攻击输入列表
            original_code_len: 原始代码行数（蓝队评估用）
            new_code_len: 新代码行数（蓝队评估用）

        Returns:
            VerdictReport: 攻击判定汇总结果
        """
        _logger.debug("ConstitutionJudge.judge_attack: attack_inputs_count=%d", len(attack_inputs))

        if on_progress is not None:
            on_progress(ProgressEvent(type="step_start", role="judge", step_name="judge_attack", data={"attack_inputs_count": len(attack_inputs)}))

        self._ensure_script(on_progress)
        if self._script is None:
            raise RuntimeError("Judge script not generated")
        inputs: list[dict] = []
        for i, ai in enumerate(attack_inputs):
            inputs.append({
                "name": f"attack_{i}",
                "input": ai,
                "expected_output": None,
            })
        if on_progress is not None:
            on_progress(ProgressEvent(type="info", role="judge", step_name="sandbox_exec",
                content=f"沙盒执行开始: {len(inputs)} 条测试", data={"test_count": len(inputs)}))
        result = self._judge.execute_judge_script(self._script, code, inputs, original_code_len, new_code_len)

        if on_progress is not None:
            on_progress(ProgressEvent(type="info", role="judge", step_name="sandbox_done",
                content=f"沙盒执行完成: {result.passed}/{result.total_tests} 通过",
                data={"passed": result.passed, "failed": result.failed, "total": result.total_tests}))

        if on_progress is not None:
            for detail in result.details:
                on_progress(ProgressEvent(type="judge_test_result", data={
                    "test_name": detail.test_name,
                    "passed": detail.passed,
                    "reason": detail.error or "",
                    "input": str(detail.input) if detail.input else "",
                    "expected_output": str(detail.expected_output) if detail.expected_output else "",
                    "actual_output": str(detail.actual_output) if detail.actual_output else "",
                }))

        _logger.info("ConstitutionJudge.judge_attack result: passed=%d, failed=%d, attack_success=%s",
                     result.passed, result.failed, result.attack_success)

        if on_progress is not None:
            on_progress(ProgressEvent(type="step_done", role="judge", step_name="judge_attack", data={"attack_success": result.attack_success}))

        return result

    def judge_defense(self, code: str, attack_inputs: list[dict], original_code_len: int, new_code_len: int, on_progress: Callable[[ProgressEvent], None] | None = None) -> VerdictReport:
        """对蓝队防御代码执行全面评估

        该方法运行正常功能测试和攻击测试，然后调用判官函数结合
        代码长度参数给出综合评分（包含 cost_score 和 defense_passed）。

        Args:
            code: 蓝队防御代码
            attack_inputs: 攻击输入列表
            original_code_len: 原始漏洞代码行数
            new_code_len: 蓝队修复代码行数
            on_progress: 进度回调

        Returns:
            VerdictReport: 综合判定结果，包含 defense_passed 和 cost_score
        """
        _logger.debug("ConstitutionJudge.judge_defense: normal_tests=%d, attack_inputs=%d, code_len_before=%d, code_len_after=%d",
                     len(self._target.normal_tests), len(attack_inputs), original_code_len, new_code_len)

        if on_progress is not None:
            on_progress(ProgressEvent(type="step_start", role="judge", step_name="judge_defense", data={
                "normal_test_count": len(self._target.normal_tests),
                "attack_input_count": len(attack_inputs),
                "original_code_len": original_code_len,
                "new_code_len": new_code_len,
            }))

        self._ensure_script(on_progress)
        if self._script is None:
            raise RuntimeError("Judge script not generated")

        inputs: list[dict] = []
        for test in self._target.normal_tests:
            inputs.append({
                "name": f"normal_{test.name}",
                "input": test.input,
                "expected_output": test.expected_output,
            })
        for i, ai in enumerate(attack_inputs):
            inputs.append({
                "name": f"attack_{i}",
                "input": ai,
                "expected_output": None,
            })

        if on_progress is not None:
            on_progress(ProgressEvent(type="info", role="judge", step_name="sandbox_exec",
                content=f"防御评估沙盒执行开始: {len(inputs)} 条测试 (normal={len(self._target.normal_tests)}, attack={len(attack_inputs)})",
                data={"test_count": len(inputs)}))

        result = self._judge.execute_judge_script(self._script, code, inputs, original_code_len, new_code_len)

        if on_progress is not None:
            on_progress(ProgressEvent(type="info", role="judge", step_name="sandbox_done",
                content=f"防御评估完成: {result.passed}/{result.total_tests} 通过, defense_passed={result.defense_passed}, cost_score={result.cost_score:.3f}",
                data={"passed": result.passed, "failed": result.failed, "total": result.total_tests,
                      "defense_passed": result.defense_passed, "cost_score": result.cost_score}))

        if on_progress is not None:
            for detail in result.details:
                on_progress(ProgressEvent(type="judge_test_result", data={
                    "test_name": detail.test_name,
                    "passed": detail.passed,
                    "reason": detail.error or "",
                    "input": str(detail.input) if detail.input else "",
                    "expected_output": str(detail.expected_output) if detail.expected_output else "",
                    "actual_output": str(detail.actual_output) if detail.actual_output else "",
                }))

        _logger.info("ConstitutionJudge.judge_defense result: passed=%d, failed=%d, attack_success=%s, defense_passed=%s, cost_score=%.3f",
                     result.passed, result.failed, result.attack_success, result.defense_passed, result.cost_score)

        if on_progress is not None:
            on_progress(ProgressEvent(type="step_done", role="judge", step_name="judge_defense", data={
                "attack_success": result.attack_success,
                "defense_passed": result.defense_passed,
                "cost_score": result.cost_score,
            }))

        return result

    def judge_normal(self, code: str) -> VerdictReport:
        """对代码执行正常功能测试判定

        Args:
            code: 待判定的 Python 代码

        Returns:
            VerdictReport: 正常测试判定汇总结果
        """
        _logger.debug("ConstitutionJudge.judge_normal: normal_tests_count=%d", len(self._target.normal_tests))
        self._ensure_script()
        if self._script is None:
            raise RuntimeError("Judge script not generated")
        inputs: list[dict] = []
        for test in self._target.normal_tests:
            inputs.append({
                "name": test.name,
                "input": test.input,
                "expected_output": test.expected_output,
            })
        result = self._judge.execute_judge_script(self._script, code, inputs)
        _logger.info("ConstitutionJudge.judge_normal result: passed=%d, failed=%d",
                     result.passed, result.failed)
        return result
