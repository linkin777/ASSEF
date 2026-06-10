"""测试 BlueTeamAgent 蓝队代理的修复 Prompt 构建、代码提取和修复反馈功能。"""

import json
import pytest

from assef.agents import BlueTeamAgent
from assef.agents.blue_team import (
    _build_fix_prompt, _build_fix_with_feedback_prompt, _extract_code,
)
from assef.llm import LLMClient
from assef.models import TargetSpec, VerdictDetail, VerdictReport

MOCK_FAILING_FIX = '''\
import json
import sys

USERS = {"alice": {"role": "admin", "secret": "flag{admin_secret_123}"}}

def query_user(name):
    if name == "__ALL__":
        return None
    return USERS.get(name)

if __name__ == "__main__":
    input_data = json.loads(sys.stdin.read())
    name = input_data.get("name", "")
    result = query_user(name)
    print(json.dumps(result if result is not None else {"error": "not found"}))
'''.strip()

CORRECT_FIX = '''
import json
import sys

USERS = {
    "alice": {"role": "admin", "secret": "flag{admin_secret_123}"},
    "bob": {"role": "user", "secret": "flag{user_secret_456}"},
    "charlie": {"role": "user", "secret": "flag{diorama_words_789}"},
}

def query_user(name):
    if not isinstance(name, str) or not name:
        return None
    return USERS.get(name)

if __name__ == "__main__":
    input_data = json.loads(sys.stdin.read())
    name = input_data.get("name", "")
    result = query_user(name)
    print(json.dumps(result if result is not None else {"error": "not found"}))
'''.strip()


class MockJudge:
    def __init__(self, fail_times=0, attack_fail=False):
        self.call_count = 0
        self.fail_times = fail_times
        self.attack_fail = attack_fail

    def judge_normal(self, target, code):
        self.call_count += 1
        if self.call_count <= self.fail_times:
            return VerdictReport(
                total_tests=3, passed=2, failed=1, attack_success=False,
                details=[
                    VerdictDetail(test_name="alice", input={}, expected_output="...", actual_output="correct", passed=True, error=None),
                    VerdictDetail(test_name="bob", input={}, expected_output="...", actual_output="wrong", passed=False, error="Output mismatch"),
                    VerdictDetail(test_name="charlie", input={}, expected_output="...", actual_output="correct", passed=True, error=None),
                ],
            )
        return VerdictReport(
            total_tests=3, passed=3, failed=0, attack_success=False,
            details=[
                VerdictDetail(test_name="alice", input={}, expected_output="...", actual_output="correct", passed=True, error=None),
                VerdictDetail(test_name="bob", input={}, expected_output="...", actual_output="correct", passed=True, error=None),
                VerdictDetail(test_name="charlie", input={}, expected_output="...", actual_output="correct", passed=True, error=None),
            ],
        )

    def judge_attack(self, target, code, attack_inputs):
        if self.attack_fail:
            return VerdictReport(
                total_tests=1, passed=0, failed=1, attack_success=True,
                details=[VerdictDetail(test_name="attack_0", input={}, expected_output=None, actual_output="flag{...}", passed=True, error=None)],
            )
        return VerdictReport(
            total_tests=1, passed=1, failed=0, attack_success=False,
            details=[VerdictDetail(test_name="attack_0", input={}, expected_output=None, actual_output="BLOCKED", passed=False, error="Blocked")],
        )


def _make_mock_client(response: str) -> LLMClient:
    return LLMClient(backend="mock", mock_response=response)


def _make_target() -> TargetSpec:
    return TargetSpec.model_validate({
        "name": "test-target",
        "description": "test",
        "sandbox_type": "process",
        "sandbox_spec": {},
        "code": "print('hello')",
        "public_spec": "input: name, output: result",
        "attack_surface": "name",
        "success_criteria": {"attack": "flag{", "fix": "Remove __ALL__ backdoor"},
        "normal_tests": [
            {"name": "alice", "input": {"name": "alice"}, "expected_output": {"role": "admin", "secret": "flag{admin_secret_123}"}},
        ],
    })


class TestBuildFixPrompt:
    def test_prompt_contains_code(self):
        target = _make_target()
        prompt = _build_fix_prompt(target)
        user_content = prompt[1]["content"]
        assert target.code in user_content

    def test_prompt_contains_public_spec(self):
        target = _make_target()
        prompt = _build_fix_prompt(target)
        user_content = prompt[1]["content"]
        assert target.public_spec in user_content

    def test_prompt_contains_normal_tests(self):
        target = _make_target()
        prompt = _build_fix_prompt(target)
        user_content = prompt[1]["content"]
        assert "alice" in user_content
        assert "expected_output" in user_content

    def test_prompt_contains_fix_goal(self):
        target = _make_target()
        prompt = _build_fix_prompt(target)
        user_content = prompt[1]["content"]
        assert target.success_criteria.fix in user_content

    def test_system_prompt_has_rules(self):
        target = _make_target()
        prompt = _build_fix_prompt(target)
        system = prompt[0]["content"]
        assert "minimal changes" in system.lower()

    def test_prompt_includes_attacks_to_block(self):
        target = _make_target()
        attacks = [{"name": "__ALL__"}, {"name": "'; drop"}]
        prompt = _build_fix_prompt(target, successful_attacks=attacks)
        user_content = prompt[1]["content"]
        assert "Attacks to Block" in user_content
        assert "__ALL__" in user_content

    def test_prompt_includes_blood_bank(self):
        target = _make_target()
        blood_bank = [{"name": "__ALL__"}, {"name": "admin"}]
        prompt = _build_fix_prompt(target, blood_bank=blood_bank)
        user_content = prompt[1]["content"]
        assert "Historical Attack Blood Bank" in user_content
        assert "admin" in user_content

    def test_prompt_with_both_attacks_and_blood_bank(self):
        target = _make_target()
        attacks = [{"name": "__ALL__"}]
        blood_bank = [{"name": "admin"}]
        prompt = _build_fix_prompt(target, successful_attacks=attacks, blood_bank=blood_bank)
        user_content = prompt[1]["content"]
        assert "Attacks to Block" in user_content
        assert "Historical Attack Blood Bank" in user_content

    def test_prompt_without_attacks_is_backward_compatible(self):
        target = _make_target()
        prompt = _build_fix_prompt(target)
        user_content = prompt[1]["content"]
        assert "Attacks to Block" not in user_content
        assert "Historical Attack Blood Bank" not in user_content


class TestBuildFixWithFeedbackPrompt:
    """测试带反馈的修复 Prompt 构建：包含失败测试详情、根因分析、攻击和血库。"""

    def test_feedback_prompt_contains_previous_code(self):
        target = _make_target()
        prompt = _build_fix_with_feedback_prompt(target, "print('bad')", [])
        user_content = prompt[1]["content"]
        assert "Your Previous Fix Code" in user_content
        assert "print('bad')" in user_content

    def test_feedback_prompt_contains_failed_test_details(self):
        target = _make_target()
        failed = [{"test_name": "alice", "input": {"name": "alice"}, "expected_output": '{"role": "admin"}', "actual_output": "wrong", "error": "Output mismatch"}]
        prompt = _build_fix_with_feedback_prompt(target, "print('bad')", failed)
        user_content = prompt[1]["content"]
        assert "Failed Test Details" in user_content
        assert "alice" in user_content
        assert "Output mismatch" in user_content

    def test_feedback_prompt_contains_root_cause_guidance(self):
        target = _make_target()
        prompt = _build_fix_with_feedback_prompt(target, "print('bad')", [])
        user_content = prompt[1]["content"]
        assert "ROOT CAUSE" in user_content

    def test_feedback_prompt_includes_attacks(self):
        target = _make_target()
        attacks = [{"name": "__ALL__"}]
        prompt = _build_fix_with_feedback_prompt(target, "print('bad')", [], successful_attacks=attacks)
        user_content = prompt[1]["content"]
        assert "Successful Attacks" in user_content

    def test_feedback_prompt_includes_blood_bank(self):
        target = _make_target()
        blood_bank = [{"name": "admin"}]
        prompt = _build_fix_with_feedback_prompt(target, "print('bad')", [], blood_bank=blood_bank)
        user_content = prompt[1]["content"]
        assert "Historical Attack Blood Bank" in user_content

    def test_feedback_prompt_uses_correct_system_prompt(self):
        target = _make_target()
        prompt = _build_fix_with_feedback_prompt(target, "print('bad')", [])
        system = prompt[0]["content"]
        assert "previous fix failed" in system.lower()


class TestExtractCode:
    """测试从 LLM 响应中提取修复代码。"""

    def test_extract_code_from_markdown(self):
        response = "```python\nprint('hello')\n```"
        assert _extract_code(response) == "print('hello')"

    def test_extract_code_no_lang_specifier(self):
        response = "```\nprint('hello')\n```"
        assert _extract_code(response) == "print('hello')"

    def test_extract_code_no_markdown(self):
        response = "print('hello')"
        assert _extract_code(response) == "print('hello')"


class TestBlueTeamAgent:
    """测试 BlueTeamAgent 修复生成：Mock 模式、危险模式检测、正常测试通过、攻击拦截。"""

    def test_generate_fix_with_mock_llm(self):
        target = _make_target()
        agent = BlueTeamAgent(_make_mock_client(CORRECT_FIX))
        result = agent.generate_fix(target)
        assert "query_user" in result
        assert "__ALL__" not in result

    def test_fix_code_has_no_dangerous_patterns(self):
        target = _make_target()
        agent = BlueTeamAgent(_make_mock_client(CORRECT_FIX))
        result = agent.generate_fix(target)
        dangerous = ["os.system", "subprocess", "__import__", "eval("]
        for pattern in dangerous:
            assert pattern not in result.lower(), f"Dangerous pattern found: {pattern}"

    def test_fix_code_passes_normal_tests(self):
        target = _make_target()
        agent = BlueTeamAgent(_make_mock_client(CORRECT_FIX))
        fixed_code = agent.generate_fix(target)

        from assef.judge import Judge
        judge = Judge()
        report = judge.judge_normal(target, fixed_code)
        assert report.passed == report.total_tests, f"Tests failed: {[d.error for d in report.details if not d.passed]}"

    def test_fix_code_blocks_attack(self):
        target = _make_target()
        agent = BlueTeamAgent(_make_mock_client(CORRECT_FIX))
        fixed_code = agent.generate_fix(target)

        from assef.judge import Judge
        judge = Judge()
        report = judge.judge_attack(target, fixed_code, [{"name": "__ALL__"}])
        assert report.attack_success is False


class TestGenerateFixWithFeedback:
    """测试带反馈的修复迭代：一次通过、失败重试成功、达到最大迭代次数、攻击拦截、血库。"""

    def test_passes_on_first_try(self):
        target = _make_target()
        agent = BlueTeamAgent(_make_mock_client(CORRECT_FIX))
        judge = MockJudge(fail_times=0)
        code, iterations, passed = agent.generate_fix_with_feedback(target, judge)
        assert passed is True
        assert iterations == 1
        assert "query_user" in code

    def test_retries_on_failure_then_succeeds(self):
        target = _make_target()
        agent = BlueTeamAgent(_make_mock_client(CORRECT_FIX))
        judge = MockJudge(fail_times=1)
        code, iterations, passed = agent.generate_fix_with_feedback(target, judge, max_iterations=3)
        assert passed is True
        assert iterations == 2

    def test_fails_after_max_iterations(self):
        target = _make_target()
        agent = BlueTeamAgent(_make_mock_client(MOCK_FAILING_FIX))
        judge = MockJudge(fail_times=5)
        code, iterations, passed = agent.generate_fix_with_feedback(target, judge, max_iterations=2)
        assert passed is False
        assert iterations == 2

    def test_with_attack_inputs_blocks_attacks(self):
        target = _make_target()
        agent = BlueTeamAgent(_make_mock_client(CORRECT_FIX))
        judge = MockJudge(fail_times=0, attack_fail=False)
        attack_inputs = [{"name": "__ALL__"}]
        code, iterations, passed = agent.generate_fix_with_feedback(
            target, judge, attack_inputs=attack_inputs,
        )
        assert passed is True

    def test_with_blood_bank_passed(self):
        target = _make_target()
        agent = BlueTeamAgent(_make_mock_client(CORRECT_FIX))
        judge = MockJudge(fail_times=0)
        blood_bank = [{"name": "__ALL__"}]
        code, iterations, passed = agent.generate_fix_with_feedback(
            target, judge, blood_bank=blood_bank,
        )
        assert passed is True

    def test_generate_fix_still_works(self):
        target = _make_target()
        agent = BlueTeamAgent(_make_mock_client(CORRECT_FIX))
        result = agent.generate_fix(target)
        assert "query_user" in result
