"""测试 RedTeamAgent 红队代理的攻击脚本生成、Prompt 构建和防御摘要功能。"""

import pytest

from assef.llm import LLMClient
from assef.models import TargetSpec
from assef.agents import RedTeamAgent
from assef.agents.red_team import (
    _extract_attack_script,
    _build_attack_prompt,
    _summarize_defense,
)
from assef.models import GameRules
from assef.models import RoundRecord


def _make_target() -> TargetSpec:
    return TargetSpec.model_validate({
        "name": "test",
        "description": "test target",
        "sandbox_type": "process",
        "sandbox_spec": {},
        "code": "print('ok')",
        "public_spec": "input name, output user data",
        "attack_surface": "backdoor_vuln_EXPLOIT_HERE",
        "success_criteria": {"attack": "flag{", "fix": "remove backdoor"},
        "normal_tests": [{"name": "test1", "input": {"name": "alice"}, "expected_output": {"role": "user"}}],
    })


def _make_record(
    round_num: int,
    attack_script: str = "",
    attack_success: bool = False,
    attack_output: str = "output",
    defense_code: str | None = None,
) -> RoundRecord:
    successful = [{"payload": "test"}] if attack_success else []
    return RoundRecord(
        round_num=round_num,
        attack_script=attack_script,
        successful_attacks=successful,
        attack_success=attack_success,
        attack_output=attack_output,
        defense_code=defense_code,
        defense_passed=defense_code is not None,
        eval_red=attack_success,
        eval_yellow=True,
        eval_green=True,
        cost_score=0.5,
        blue_retries=0,
    )


class TestBuildAttackPrompt:
    def test_prompt_contains_public_spec(self):
        target = _make_target()
        prompt = _build_attack_prompt(target, None, GameRules(), 1)
        user_content = prompt[1]["content"]
        assert "input name, output user data" in user_content

    def test_prompt_contains_description(self):
        target = _make_target()
        prompt = _build_attack_prompt(target, None, GameRules(), 1)
        user_content = prompt[1]["content"]
        assert "test target" in user_content

    def test_prompt_contains_normal_tests(self):
        target = _make_target()
        prompt = _build_attack_prompt(target, None, GameRules(), 1)
        user_content = prompt[1]["content"]
        assert "test1" in user_content
        assert "alice" in user_content

    def test_prompt_does_not_contain_attack_surface(self):
        target = _make_target()
        prompt = _build_attack_prompt(target, None, GameRules(), 1)
        user_content = prompt[1]["content"]
        assert target.attack_surface not in user_content

    def test_prompt_contains_sandbox_env(self):
        target = _make_target()
        prompt = _build_attack_prompt(target, None, GameRules(), 1)
        user_content = prompt[1]["content"]
        assert "Sandbox Execution Environment" in user_content
        assert "json.loads(sys.stdin.read())" in user_content
        assert "Dangerous patterns BLOCKED" in user_content

    def test_prompt_with_history_shows_all_rounds(self):
        target = _make_target()
        history = [
            _make_record(1, attack_script="import sys\nprint('attack1')", attack_success=True, attack_output="secret"),
            _make_record(2, attack_script="import sys\nprint('attack2')", attack_success=False, attack_output="not found"),
            _make_record(3, attack_script="import sys\nprint('attack3')", attack_success=True, attack_output="flag", defense_code="def code here"),
        ]
        prompt = _build_attack_prompt(target, history, GameRules(), 2)
        user_content = prompt[1]["content"]
        assert "Round 1" in user_content
        assert "Round 2" in user_content
        assert "Round 3" in user_content
        assert "SUCCESS" in user_content
        assert "BLOCKED" in user_content

    def test_prompt_shows_full_history_not_just_last_3(self):
        target = _make_target()
        history = [_make_record(i, attack_script=f"print('round{i}')") for i in range(1, 6)]
        prompt = _build_attack_prompt(target, history, GameRules(), 4)
        user_content = prompt[1]["content"]
        assert "Round 1" in user_content
        assert "Round 5" in user_content

    def test_prompt_includes_round_summary_preamble(self):
        target = _make_target()
        history = [_make_record(1, attack_script="print('test')", attack_success=True, attack_output="secret", defense_code="code")]
        prompt = _build_attack_prompt(target, history, GameRules(), 2)
        user_content = prompt[1]["content"]
        assert "Blood bank has" in user_content
        assert "Blue has defended" in user_content

    def test_prompt_includes_defense_code_status(self):
        target = _make_target()
        defense_code = "print('ok')\n# fixed"
        prompt = _build_attack_prompt(target, None, GameRules(), 1, defense_code=defense_code)
        user_content = prompt[1]["content"]
        assert "Current Defense Code Status" in user_content

    def test_prompt_omits_defense_status_when_empty(self):
        target = _make_target()
        prompt = _build_attack_prompt(target, None, GameRules(), 1, defense_code="")
        user_content = prompt[1]["content"]
        assert "Current Defense Code Status" not in user_content

    def test_system_prompt_instructs_python_script_generation(self):
        target = _make_target()
        prompt = _build_attack_prompt(target, None, GameRules(), 1)
        system = prompt[0]["content"]
        assert "Python attack script" in system
        assert "json.loads(sys.stdin.read())" in system
        assert "executable" in system


class TestSummarizeDefense:
    def test_no_defense(self):
        record = _make_record(1, defense_code=None)
        result = _summarize_defense(record)
        assert result == "No defense submitted"

    def test_defense_without_original(self):
        record = _make_record(1, defense_code="line1\nline2\nline3")
        result = _summarize_defense(record)
        assert "3 lines" in result
        assert "from original" not in result

    def test_defense_with_original(self):
        record = _make_record(1, defense_code="line1\nline2\nline3")
        result = _summarize_defense(record, original_code_length=1)
        assert "+2" in result


class TestExtractAttackScript:
    """测试从 LLM 响应中提取攻击脚本。"""

    def test_extract_plain_code(self):
        result = _extract_attack_script("import sys\nprint('hello')")
        assert result == "import sys\nprint('hello')"

    def test_extract_from_markdown_python_block(self):
        result = _extract_attack_script("```python\nimport sys\nprint('hello')\n```")
        assert result == "import sys\nprint('hello')"

    def test_extract_from_markdown_plain_block(self):
        result = _extract_attack_script("```\nimport sys\nprint('hello')\n```")
        assert result == "import sys\nprint('hello')"

    def test_extract_empty_string(self):
        result = _extract_attack_script("")
        assert result == ""

    def test_extract_whitespace_only(self):
        result = _extract_attack_script("   \n  \t  ")
        assert result == ""


class TestRedTeamAgent:
    """测试 RedTeamAgent 攻击生成：返回字符串、带历史记录、Markdown 提取、进度事件。"""

    def test_generate_attack_returns_string(self):
        target = _make_target()
        mock_llm = LLMClient(backend="mock", mock_response="import sys\nprint('attack')")
        agent = RedTeamAgent(mock_llm)
        result = agent.generate_attack(target)
        assert isinstance(result, str)
        assert result == "import sys\nprint('attack')"

    def test_generate_attack_with_history(self):
        target = _make_target()
        mock_llm = LLMClient(backend="mock", mock_response="import sys\nprint('new_attack')")
        agent = RedTeamAgent(mock_llm)
        history = [_make_record(1, attack_script="print('old')", attack_success=False, attack_output="not found")]
        result = agent.generate_attack(target, history)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_attack_extracts_code_from_markdown(self):
        target = _make_target()
        mock_llm = LLMClient(backend="mock", mock_response="```python\nimport sys\nprint('attack')\n```")
        agent = RedTeamAgent(mock_llm)
        result = agent.generate_attack(target)
        assert result == "import sys\nprint('attack')"

    def test_generate_attack_round_num_from_history(self):
        target = _make_target()
        history = [_make_record(i, attack_script=f"print('round{i}')") for i in range(1, 4)]
        mock_llm = LLMClient(backend="mock", mock_response="import sys\nprint('attack')")
        agent = RedTeamAgent(mock_llm)
        result = agent.generate_attack(target, history=history)
        assert isinstance(result, str)

    def test_generate_attack_progress_events(self):
        target = _make_target()
        mock_llm = LLMClient(backend="mock", mock_response="import sys\nprint('attack')")
        agent = RedTeamAgent(mock_llm)
        events = []

        def on_progress(event):
            events.append(event)

        result = agent.generate_attack(target, on_progress=on_progress)
        assert len(events) == 2
        assert events[0].type == "step_start"
        assert events[1].type == "step_done"
        assert result == "import sys\nprint('attack')"
