"""ASSEF 蓝队Agent —— 安全修复代码生成器，针对已知漏洞生成最小化修复方案"""

from __future__ import annotations

import re
import json
from typing import Callable

from ..llm import LLMClient
from ..logging_config import get_logger
from ..models import TargetSpec
from ..models.results import VerdictReport
from ..core.progress import ProgressEvent


_logger = get_logger("blue_team")

DEFAULT_MAX_ITERATIONS = 30

SYSTEM_PROMPT = """\
You are a security-focused software engineer (Blue Team). Your task is to fix a vulnerability in the provided code.

## Rules (follow strictly):
1. ONLY modify the vulnerable parts — make minimal changes.
2. Do NOT introduce unnecessary dependencies or complex logic.
3. **Preserve all input validation** (type checks, bounds checks, sanitization) — do NOT remove or weaken them.
4. Keep the code clean, readable, and maintainable.
5. Return ONLY the complete fixed code, without any markdown code blocks or explanations.
6. The fixed code MUST still pass all normal functionality tests.
7. The fixed code MUST block the described attack vector.

## Input format:
- Code: the current code with a vulnerability
- Public Interface: the contract the code must fulfill
- Normal Tests: test cases the fixed code must pass
- Fix Goal: description of what the fix should achieve

Output ONLY the fixed Python code, nothing else.
"""

FIX_FEEDBACK_SYSTEM_PROMPT = """\
You are a security-focused software engineer (Blue Team). Your previous fix FAILED some tests. Your task is to analyze the failures and fix the ROOT CAUSE.

## Rules (follow strictly):
1. Analyze why the tests failed — identify the ROOT CAUSE, not the symptoms.
2. ONLY modify the broken parts — do NOT change code that already passes tests.
3. Do NOT introduce unnecessary dependencies or complex logic.
4. Return ONLY the complete fixed code, without any markdown code blocks or explanations.
5. The fixed code MUST pass ALL normal functionality tests.
6. The fixed code MUST block ALL attack inputs provided below.

Output ONLY the fixed Python code, nothing else.
"""

ENHANCE_SYSTEM_PROMPT = """\
You are a security-focused software engineer (Blue Team). Your task is to proactively harden the provided code against potential security vulnerabilities.

The red team attempted an attack but it FAILED. However, the attack attempt reveals potential weaknesses. Your job is to strengthen the code to prevent future attacks.

## Rules (follow strictly):
1. Analyze the attack approach — what was the attacker trying? What weaknesses might exist?
2. Proactively harden the code against potential future attacks based on the attack surface
3. Keep the code clean and maintainable
4. Don't over-engineer — make targeted, meaningful improvements
5. Return ONLY the complete hardened code, without any markdown code blocks or explanations
6. The hardened code MUST still pass ALL normal functionality tests

## Input format:
- Code: the current code
- Public Interface: the contract the code must fulfill
- Normal Tests: test cases the code must pass
- Attack Script: the red team's attack approach (which FAILED)
- Sandbox Logs: execution results from the attack attempt

Output ONLY the hardened Python code, nothing else.
"""

ENHANCE_FEEDBACK_SYSTEM_PROMPT = """\
You are a security-focused software engineer (Blue Team). Your previous security hardening FAILED some normal tests. Your task is to fix the ROOT CAUSE while maintaining security improvements.

## Rules (follow strictly):
1. Analyze why the normal tests failed — identify the ROOT CAUSE, not the symptoms
2. FIX the test failures while keeping the security hardening intact
3. Do not remove security hardening just to pass tests — find a correct approach
4. Return ONLY the complete code, without any markdown code blocks or explanations
5. If ALL normal tests fail and the code is broken, revert your hardening approach and start fresh
6. The code MUST still be hardened against potential attacks

Output ONLY the complete Python code, nothing else.
"""


def _build_fix_prompt(
    target: TargetSpec,
    successful_attacks: list[dict] | None = None,
    blood_bank: list[dict] | None = None,
    attack_script: str | None = None,
    sandbox_logs: list[dict] | None = None,
) -> list[dict]:
    """构建蓝队修复代码生成的 LLM 对话消息

    组装 system/user 消息，包含目标代码、公共接口、正常测试用例、
    攻击脚本和沙箱执行日志，引导 LLM 生成针对性修复。

    Args:
        target: 靶机规格（含漏洞代码、修复目标和攻击面）
        successful_attacks: 成功攻击的输入列表（修复必须拦截的攻击）
        blood_bank: 历史攻击血库（修复不能重新引入已修复的漏洞）
        attack_script: 红队攻击脚本（可选）
        sandbox_logs: 沙箱执行日志（可选）

    Returns:
        list[dict]: 包含 system 和 user 角色的对话消息列表
    """
    normal_tests_str = json.dumps(
        [{"name": t.name, "input": t.input, "expected_output": t.expected_output} for t in target.normal_tests],
        indent=2,
        ensure_ascii=False,
    )
    user_content = f"""\
## Code:
```python
{target.code}
```

## Public Interface:
{target.public_spec}

## Normal Tests:
{normal_tests_str}

## Fix Goal:
{target.success_criteria.fix}

## Attack Surface:
{target.attack_surface}
"""

    if attack_script:
        user_content += f"\n## Red Team Attack Script:\n{attack_script}\n"

    if sandbox_logs:
        user_content += "\n## Sandbox Execution Logs:\n"
        for i, log in enumerate(sandbox_logs):
            user_content += (
                f"- Attack {i}: stdout={log.get('stdout', '')[:200]}, "
                f"stderr={log.get('stderr', '')[:200]}, "
                f"exit_code={log.get('exit_code')}, timed_out={log.get('timed_out')}\n"
            )

    if successful_attacks:
        user_content += "\n## Attacks to Block:\n"
        for attack in successful_attacks:
            user_content += f"{json.dumps(attack, ensure_ascii=False)}\n"
        user_content += "\nYour fix MUST block all attacks above.\n"

    if blood_bank:
        user_content += "\n## Historical Attack Blood Bank (DO NOT reintroduce vulnerabilities for these):\n"
        for attack in blood_bank:
            user_content += f"{json.dumps(attack, ensure_ascii=False)}\n"
        user_content += "\nYour fix must NOT reintroduce vulnerabilities that allow any of these historical attacks.\n"

    user_content += "\nPlease provide the fixed code:"

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _build_fix_with_feedback_prompt(
    target: TargetSpec,
    current_code: str,
    failed_tests: list[dict],
    successful_attacks: list[dict] | None = None,
    blood_bank: list[dict] | None = None,
    attack_script: str | None = None,
    sandbox_logs: list[dict] | None = None,
) -> list[dict]:
    """构建蓝队修复反馈迭代的 LLM 对话消息

    当上一轮修复未通过测试时，组装包含失败测试详情的消息，
    引导 LLM 分析根因并重新生成修复。

    Args:
        target: 靶机规格
        current_code: 上一轮生成的修复代码
        failed_tests: 失败测试详情列表（含 test_name、input、expected_output、actual_output、error）
        successful_attacks: 成功攻击列表（可选，修复必须拦截）
        blood_bank: 历史攻击血库（可选，防止修复倒退）
        attack_script: 红队攻击脚本（可选）
        sandbox_logs: 沙箱执行日志（可选）

    Returns:
        list[dict]: 包含 system 和 user 角色的对话消息列表
    """
    user_content = f"""\
## Your Previous Fix Code:
```python
{current_code}
```

## Failed Test Details:
"""
    for ft in failed_tests:
        user_content += f"""
- Test Name: {ft.get('test_name', 'unknown')}
  Input: {json.dumps(ft.get('input', {}), ensure_ascii=False)}
  Expected Output: {json.dumps(ft.get('expected_output'), ensure_ascii=False) if ft.get('expected_output') is not None else 'N/A'}
  Actual Output: {ft.get('actual_output', '')}
  Error: {ft.get('error', 'unknown')}
"""

    if attack_script:
        user_content += f"\n## Red Team Attack Script:\n{attack_script}\n"

    if sandbox_logs:
        user_content += "\n## Sandbox Execution Logs:\n"
        for i, log in enumerate(sandbox_logs):
            user_content += (
                f"- Attack {i}: stdout={log.get('stdout', '')[:200]}, "
                f"stderr={log.get('stderr', '')[:200]}, "
                f"exit_code={log.get('exit_code')}, timed_out={log.get('timed_out')}\n"
            )

    if successful_attacks:
        user_content += "\n## Successful Attacks (must be blocked):\n"
        for attack in successful_attacks:
            user_content += f"{json.dumps(attack, ensure_ascii=False)}\n"

    if blood_bank:
        user_content += "\n## Historical Attack Blood Bank (must remain blocked):\n"
        for attack in blood_bank:
            user_content += f"{json.dumps(attack, ensure_ascii=False)}\n"

    user_content += """
## Instructions:
1. Analyze why the tests failed — find the ROOT CAUSE
2. Fix the root cause, NOT the symptoms
3. Make minimal changes — don't rewrite working code
4. After fixing, re-verify all test cases should pass
5. The fix must also block ALL attacks shown above

Provide the complete fixed code:"""

    return [
        {"role": "system", "content": FIX_FEEDBACK_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _build_enhance_prompt(
    target: TargetSpec,
    attack_script: str | None = None,
    sandbox_logs: list[dict] | None = None,
    blood_bank: list[dict] | None = None,
) -> list[dict]:
    """构建蓝队主动加固代码生成的 LLM 对话消息

    当红队攻击失败时，蓝队主动分析攻击手法并加固代码，
    防止未来的类似攻击。

    Args:
        target: 靶机规格（含当前代码、攻击面）
        attack_script: 红队攻击脚本（攻击已失败，用于分析攻击意图）
        sandbox_logs: 沙箱执行日志（攻击已失败的证据）
        blood_bank: 历史攻击血库（可选，防止加固引入历史漏洞）

    Returns:
        list[dict]: 包含 system 和 user 角色的对话消息列表
    """
    normal_tests_str = json.dumps(
        [{"name": t.name, "input": t.input, "expected_output": t.expected_output} for t in target.normal_tests],
        indent=2,
        ensure_ascii=False,
    )
    user_content = f"""\
## Code:
```python
{target.code}
```

## Public Interface:
{target.public_spec}

## Normal Tests:
{normal_tests_str}

## Attack Surface:
{target.attack_surface}
"""

    if attack_script:
        user_content += f"\n## Red Team Attack Script (FAILED):\n{attack_script}\n"
        user_content += "\nAnalyze what the attacker was trying to do and harden the code against similar attack vectors.\n"

    if sandbox_logs:
        user_content += "\n## Sandbox Execution Logs (attack FAILED):\n"
        for i, log in enumerate(sandbox_logs):
            user_content += (
                f"- Attack {i}: stdout={log.get('stdout', '')[:200]}, "
                f"stderr={log.get('stderr', '')[:200]}, "
                f"exit_code={log.get('exit_code')}, timed_out={log.get('timed_out')}\n"
            )

    if blood_bank:
        user_content += "\n## Historical Attack Blood Bank (DO NOT reintroduce vulnerabilities for these):\n"
        for attack in blood_bank:
            user_content += f"{json.dumps(attack, ensure_ascii=False)}\n"
        user_content += "\nYour hardening must NOT reintroduce vulnerabilities that allow any of these historical attacks.\n"

    user_content += "\nPlease provide the hardened code:"

    return [
        {"role": "system", "content": ENHANCE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _build_enhance_with_feedback_prompt(
    target: TargetSpec,
    current_code: str,
    failed_tests: list[dict],
    attack_script: str | None = None,
    sandbox_logs: list[dict] | None = None,
    blood_bank: list[dict] | None = None,
) -> list[dict]:
    """构建蓝队加固反馈迭代的 LLM 对话消息

    当上一轮加固代码未通过正常测试时，组装包含失败测试详情的消息，
    引导 LLM 修复根因同时保留安全加固。

    Args:
        target: 靶机规格
        current_code: 上一轮生成的加固代码
        failed_tests: 失败测试详情列表
        attack_script: 红队攻击脚本（可选，已知已拦截）
        sandbox_logs: 沙箱执行日志（可选）
        blood_bank: 历史攻击血库（可选，必须保持拦截）

    Returns:
        list[dict]: 包含 system 和 user 角色的对话消息列表
    """
    user_content = f"""\
## Your Previous Hardened Code:
```python
{current_code}
```

## Failed Test Details:
"""
    for ft in failed_tests:
        user_content += f"""
- Test Name: {ft.get('test_name', 'unknown')}
  Input: {json.dumps(ft.get('input', {}), ensure_ascii=False)}
  Expected Output: {json.dumps(ft.get('expected_output'), ensure_ascii=False) if ft.get('expected_output') is not None else 'N/A'}
  Actual Output: {ft.get('actual_output', '')}
  Error: {ft.get('error', 'unknown')}
"""

    if attack_script:
        user_content += f"\n## Red Team Attack Script (already blocked):\n{attack_script}\n"

    if sandbox_logs:
        user_content += "\n## Sandbox Execution Logs:\n"
        for i, log in enumerate(sandbox_logs):
            user_content += (
                f"- Attack {i}: stdout={log.get('stdout', '')[:200]}, "
                f"stderr={log.get('stderr', '')[:200]}, "
                f"exit_code={log.get('exit_code')}, timed_out={log.get('timed_out')}\n"
            )

    if blood_bank:
        user_content += "\n## Historical Attack Blood Bank (must remain blocked):\n"
        for attack in blood_bank:
            user_content += f"{json.dumps(attack, ensure_ascii=False)}\n"

    user_content += """
## Instructions:
1. Analyze why the normal tests failed — find the ROOT CAUSE
2. Fix the root cause while keeping security hardening
3. Make minimal changes — don't rewrite working code
4. After fixing, re-verify all test cases should pass
5. The code must remain hardened against the attack approach shown above

Provide the complete code:"""

    return [
        {"role": "system", "content": ENHANCE_FEEDBACK_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _extract_code(response: str) -> str:
    _logger.debug("_extract_code(): response_len=%d", len(response))
    pattern = r"```(?:python)?\s*\n(.*?)```"
    match = re.search(pattern, response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return response.strip()


class BlueTeamAgent:
    """蓝队修复代理 —— 通过 LLM 生成针对漏洞的最小化安全修复代码"""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    def generate_fix(
        self,
        target: TargetSpec,
        attack_script: str | None = None,
        sandbox_logs: list[dict] | None = None,
    ) -> str:
        """为目标靶机生成安全修复代码

        Args:
            target: 包含漏洞代码和修复目标的靶机规格
            attack_script: 红队攻击脚本（可选，用于提供攻击上下文）
            sandbox_logs: 沙箱执行日志（可选）

        Returns:
            str: 修复后的完整 Python 代码
        """
        _logger.debug("generate_fix(): target=%s, calling LLM", target.name)
        messages = _build_fix_prompt(target, attack_script=attack_script, sandbox_logs=sandbox_logs)
        self._llm.set_call_context({
            "caller": "blue_team",
            "round": None,
        })
        response = self._llm.chat(messages, temperature=0.3, max_tokens=4096)
        return _extract_code(response)

    def _generate_initial_fix(
        self,
        target: TargetSpec,
        attack_script: str | None = None,
        sandbox_logs: list[dict] | None = None,
    ) -> str:
        return self.generate_fix(target, attack_script=attack_script, sandbox_logs=sandbox_logs)

    def _build_failed_tests_from_report(self, normal_report: VerdictReport) -> list[dict]:
        """从裁判报告中提取所有失败测试的详情

        Args:
            normal_report: 正常功能测试的判定报告

        Returns:
            list[dict]: 失败测试详情列表，每项含 test_name、input、
                        expected_output、actual_output、error 字段
        """
        return [
            {
                "test_name": d.test_name,
                "input": d.input,
                "expected_output": d.expected_output,
                "actual_output": d.actual_output,
                "error": d.error,
            }
            for d in normal_report.details
            if not d.passed
        ]

    def generate_fix_with_feedback(
        self,
        target: TargetSpec,
        judge,
        max_iterations: int | None = None,
        attack_inputs: list[dict] | None = None,
        blood_bank: list[dict] | None = None,
        attack_script: str | None = None,
        sandbox_logs: list[dict] | None = None,
        on_progress: Callable[[ProgressEvent], None] | None = None,
        pause_event=None,
    ) -> tuple[str, int, bool]:
        """生成修复代码并自我迭代验证

        生成初始修复 → 裁判测试 → 若失败则反馈重试 → 循环直到通过或耗尽迭代次数。
        当 max_iterations 为 None 时，使用默认上限 30，蓝队可以自行决定何时提交。

        Args:
            target: 靶机规格
            judge: 裁判实例（需有 judge_normal 和 judge_attack 方法）
            max_iterations: 最大自我迭代次数（None 表示使用默认上限 30）
            attack_inputs: 需要拦截的攻击输入列表
            blood_bank: 历史攻击血库（防止修复倒退）
            attack_script: 红队攻击脚本描述
            sandbox_logs: 沙箱执行日志

        Returns:
            tuple[str, int, bool]: (最终代码, 实际迭代次数, 是否全部测试通过)
        """
        effective_max = max_iterations if max_iterations is not None else DEFAULT_MAX_ITERATIONS
        _logger.debug(
            "generate_fix_with_feedback(): start, max_iterations=%d, attack_inputs_count=%d",
            effective_max, len(attack_inputs) if attack_inputs else 0,
        )

        if on_progress is not None:
            on_progress(ProgressEvent(type="step_start", role="blue_team", step_name="generate_fix", data={"max_iterations": effective_max, "mode": "fix"}))

        _logger.info("蓝队迭代 1: 开始生成修复 code_len=%d", len(target.code))
        code = self._generate_initial_fix(target, attack_script=attack_script, sandbox_logs=sandbox_logs)

        if pause_event is not None:
            pause_event.wait()

        return self._iterate_fix(
            target=target, judge=judge,
            max_iterations=effective_max,
            code=code, attack_inputs=attack_inputs,
            blood_bank=blood_bank, attack_script=attack_script,
            sandbox_logs=sandbox_logs,
            on_progress=on_progress, pause_event=pause_event,
            start_iteration=1,
        )

    def _iterate_fix(
        self,
        target: TargetSpec,
        judge,
        max_iterations: int,
        code: str,
        attack_inputs: list[dict] | None,
        blood_bank: list[dict] | None,
        attack_script: str | None,
        sandbox_logs: list[dict] | None,
        on_progress: Callable[[ProgressEvent], None] | None,
        pause_event,
        start_iteration: int = 1,
    ) -> tuple[str, int, bool]:
        for iteration in range(start_iteration, max_iterations + 1):
            normal_report = judge.judge_normal(target, code)
            all_normal_ok = normal_report.passed == normal_report.total_tests

            attack_ok = True
            if attack_inputs:
                attack_report = judge.judge_attack(target, code, attack_inputs)
                attack_ok = not attack_report.attack_success

            _logger.info(
                "generate_fix_with_feedback(): iteration=%d, normal=%d/%d, attack_ok=%s",
                iteration, normal_report.passed, normal_report.total_tests, attack_ok,
            )
            _logger.info("蓝队迭代 %d: passed=%s, code_len=%d", iteration, all_normal_ok and attack_ok, len(code))

            _logger.debug("迭代 %d 代码 (%d chars): %s", iteration, len(code), code[:300])

            if on_progress is not None:
                on_progress(ProgressEvent(type="iteration_result", role="blue_team", step_name="iteration", data={
                    "iteration": iteration,
                    "normal_passed": normal_report.passed,
                    "normal_total": normal_report.total_tests,
                    "attack_ok": attack_ok,
                    "passed": all_normal_ok and attack_ok,
                }))

            if all_normal_ok and attack_ok:
                _logger.info(
                    "generate_fix_with_feedback(): all passed, total_iterations=%d, final_passed=True",
                    iteration,
                )

                if on_progress is not None:
                    on_progress(ProgressEvent(type="step_done", role="blue_team", step_name="generate_fix", data={"total_iterations": iteration, "passed": True, "code_len": len(code), "mode": "fix"}))
                return (code, iteration, True)

            if iteration >= max_iterations:
                _logger.info(
                    "generate_fix_with_feedback(): max iterations reached, total_iterations=%d, final_passed=False",
                    iteration,
                )

                if on_progress is not None:
                    on_progress(ProgressEvent(type="step_done", role="blue_team", step_name="generate_fix", data={"total_iterations": iteration, "passed": False, "code_len": len(code), "mode": "fix", "limit_hit": True}))
                return (code, iteration, False)

            failed_tests = self._build_failed_tests_from_report(normal_report)

            if on_progress is not None:
                all_normal_failed = normal_report.passed == 0
                on_progress(ProgressEvent(type="iteration_feedback", role="blue_team", step_name="iteration", data={
                    "iteration": iteration,
                    "failed_test_count": len(failed_tests),
                    "all_normal_failed": all_normal_failed,
                }))

            feedback_messages = _build_fix_with_feedback_prompt(
                target, code, failed_tests, attack_inputs, blood_bank,
                attack_script=attack_script, sandbox_logs=sandbox_logs,
            )
            self._llm.set_call_context({
                "caller": "blue_self_iter",
                "round": None,
            })
            _logger.info("蓝队迭代 %d: 开始生成修复 (feedback)", iteration + 1)
            response = self._llm.chat(feedback_messages, temperature=0.3, max_tokens=4096)
            code = _extract_code(response)

            if pause_event is not None:
                pause_event.wait()

        return (code, max_iterations, False)

    def generate_enhance_with_feedback(
        self,
        target: TargetSpec,
        judge,
        max_iterations: int | None = None,
        attack_script: str | None = None,
        sandbox_logs: list[dict] | None = None,
        blood_bank: list[dict] | None = None,
        on_progress: Callable[[ProgressEvent], None] | None = None,
        pause_event=None,
    ) -> tuple[str, int, bool]:
        """增强模式：当红队攻击失败时，蓝队主动加固代码

        蓝队分析攻击手法 → 生成加固代码 → 裁判测试正常功能 → 若失败则反馈重试。
        当 max_iterations 为 None 时，使用默认上限 30。

        Args:
            target: 靶机规格
            judge: 裁判实例（需有 judge_normal 方法）
            max_iterations: 最大自我迭代次数（None 表示使用默认上限 30）
            attack_script: 红队的攻击脚本描述（用于分析攻击意图）
            sandbox_logs: 沙箱执行日志（攻击已失败的证据）
            blood_bank: 历史攻击血库（防止修复倒退）

        Returns:
            tuple[str, int, bool]: (最终代码, 实际迭代次数, 是否全部正常测试通过)
        """
        effective_max = max_iterations if max_iterations is not None else DEFAULT_MAX_ITERATIONS
        _logger.debug(
            "generate_enhance_with_feedback(): start, max_iterations=%d, target=%s",
            effective_max, target.name,
        )

        if on_progress is not None:
            on_progress(ProgressEvent(type="step_start", role="blue_team", step_name="generate_enhance", data={"max_iterations": effective_max, "mode": "enhance"}))

        _logger.info("蓝队增强 迭代 1: 开始生成加固代码 code_len=%d", len(target.code))

        messages = _build_enhance_prompt(
            target, attack_script=attack_script,
            sandbox_logs=sandbox_logs, blood_bank=blood_bank,
        )
        self._llm.set_call_context({
            "caller": "blue_enhance",
            "round": None,
        })
        response = self._llm.chat(messages, temperature=0.3, max_tokens=4096)
        code = _extract_code(response)

        if pause_event is not None:
            pause_event.wait()

        for iteration in range(1, effective_max + 1):
            normal_report = judge.judge_normal(target, code)
            all_normal_ok = normal_report.passed == normal_report.total_tests

            _logger.info(
                "generate_enhance_with_feedback(): iteration=%d, normal=%d/%d",
                iteration, normal_report.passed, normal_report.total_tests,
            )

            _logger.debug("增强迭代 %d 代码 (%d chars): %s", iteration, len(code), code[:300])

            if on_progress is not None:
                on_progress(ProgressEvent(type="iteration_result", role="blue_team", step_name="enhance_iteration", data={
                    "iteration": iteration,
                    "normal_passed": normal_report.passed,
                    "normal_total": normal_report.total_tests,
                    "passed": all_normal_ok,
                }))

            if all_normal_ok:
                _logger.info(
                    "generate_enhance_with_feedback(): all normal passed, total_iterations=%d",
                    iteration,
                )

                if on_progress is not None:
                    on_progress(ProgressEvent(type="step_done", role="blue_team", step_name="generate_enhance", data={"total_iterations": iteration, "passed": True, "code_len": len(code), "mode": "enhance"}))
                return (code, iteration, True)

            if iteration >= effective_max:
                _logger.info(
                    "generate_enhance_with_feedback(): max iterations reached, total_iterations=%d, final_passed=False",
                    iteration,
                )

                if on_progress is not None:
                    on_progress(ProgressEvent(type="step_done", role="blue_team", step_name="generate_enhance", data={"total_iterations": iteration, "passed": False, "code_len": len(code), "mode": "enhance", "limit_hit": True}))
                return (code, iteration, False)

            failed_tests = self._build_failed_tests_from_report(normal_report)

            all_normal_failed = normal_report.passed == 0
            if on_progress is not None:
                on_progress(ProgressEvent(type="iteration_feedback", role="blue_team", step_name="enhance_iteration", data={
                    "iteration": iteration,
                    "failed_test_count": len(failed_tests),
                    "all_normal_failed": all_normal_failed,
                }))

            if all_normal_failed:
                _logger.warning("增强迭代 %d: 所有正常测试失败，蓝队可能破坏了代码", iteration)

            feedback_messages = _build_enhance_with_feedback_prompt(
                target, code, failed_tests,
                attack_script=attack_script, sandbox_logs=sandbox_logs,
                blood_bank=blood_bank,
            )
            self._llm.set_call_context({
                "caller": "blue_enhance_iter",
                "round": None,
            })
            _logger.info("蓝队增强 %d: 开始生成加固代码 (feedback)", iteration + 1)
            response = self._llm.chat(feedback_messages, temperature=0.3, max_tokens=4096)
            code = _extract_code(response)

            if pause_event is not None:
                pause_event.wait()

        return (code, effective_max, False)
