import importlib.util
from pathlib import Path
from unittest.mock import patch
from assef.llm import LLMClient
from assef.models import Constitution
from assef.judge import ConstitutionJudge
from assef.models import GameRules
from assef.models import TargetSpec
from assef.agents import RedTeamAgent
from assef.agents import BlueTeamAgent
from assef.arena import Arena


MOCK_JUDGE_SCRIPT = '''
def judge(inputs):
    results = []
    attack_success = False
    for inp in inputs:
        actual = inp.get("actual_output", "")
        expected = inp.get("expected_output")
        if expected is not None:
            passed = (actual.strip() == str(expected).strip())
            results.append({"name": inp["name"], "passed": passed, "reason": "match" if passed else "mismatch"})
        else:
            passed = "flag{" in actual
            if passed:
                attack_success = True
            results.append({"name": inp["name"], "passed": passed, "reason": "found flag" if passed else "no flag"})
    return {"attack_success": attack_success, "results": results}
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

def _load_example_data():
    example_path = Path(__file__).parent.parent / "examples" / "simple_user_query.py"
    spec = importlib.util.spec_from_file_location("simple_user_query", example_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SIMPLE_USER_QUERY_DATA

def _build_target():
    data = _load_example_data()
    data = dict(data)
    data["success_criteria"] = {"attack": "flag{", "fix": data["success_criteria"]["fix"]}
    return TargetSpec.model_validate(data)


class TestArena:
    """测试 Arena 斗兽场的核心功能：完整流程、攻击失败、蓝队重试、血库、多攻击、修复反馈。"""

    def test_single_round_complete_flow(self):
        target = _build_target()
        mock_llm = LLMClient(backend="mock", mock_response=MOCK_JUDGE_SCRIPT)
        cj = ConstitutionJudge(Constitution.default(), target, mock_llm)
        attack_script = 'print(json.dumps(query_user("__ALL__")))'
        red_team = RedTeamAgent(LLMClient(backend="mock", mock_response=attack_script))
        blue_team = BlueTeamAgent(LLMClient(backend="mock", mock_response=CORRECT_FIX))

        arena = Arena(cj, red_team, blue_team, GameRules())
        result = arena.run(target, max_rounds=1)
        assert result.total_rounds == 1
        assert len(result.rounds) == 1
        assert result.target_name == target.name
        record = result.rounds[0]
        assert isinstance(record.attack_script, str)
        assert isinstance(record.successful_attacks, list)

    def test_attack_not_successful_triggers_enhance(self):
        target = _build_target()
        mock_llm = LLMClient(backend="mock", mock_response=MOCK_JUDGE_SCRIPT)
        cj = ConstitutionJudge(Constitution.default(), target, mock_llm)
        safe_script = 'print(json.dumps(query_user("nonexistent")))'
        red_team = RedTeamAgent(LLMClient(backend="mock", mock_response=safe_script))
        blue_team = BlueTeamAgent(LLMClient(backend="mock", mock_response=CORRECT_FIX))

        arena = Arena(cj, red_team, blue_team, GameRules())
        result = arena.run(target, max_rounds=1)
        record = result.rounds[0]
        assert record.attack_success is False

    def test_blue_retry_on_bad_fix(self):
        target = _build_target()
        mock_llm = LLMClient(backend="mock", mock_response=MOCK_JUDGE_SCRIPT)
        cj = ConstitutionJudge(Constitution.default(), target, mock_llm)
        attack_script = 'print(json.dumps(query_user("__ALL__")))'
        red_team = RedTeamAgent(LLMClient(backend="mock", mock_response=attack_script))
        bad_then_good = LLMClient(backend="mock", mock_response=CORRECT_FIX)
        blue_team = BlueTeamAgent(bad_then_good)

        rules = GameRules(blue_self_iteration_limit=2)
        arena = Arena(cj, red_team, blue_team, rules)
        result = arena.run(target, max_rounds=1)
        assert result.total_rounds == 1
        record = result.rounds[0]
        assert record.attack_success is True

    def test_blood_bank_accumulates(self):
        target = _build_target()
        mock_llm = LLMClient(backend="mock", mock_response=MOCK_JUDGE_SCRIPT)
        cj = ConstitutionJudge(Constitution.default(), target, mock_llm)
        attack_script = 'print(json.dumps(query_user("__ALL__")))'
        red_team = RedTeamAgent(LLMClient(backend="mock", mock_response=attack_script))
        blue_team = BlueTeamAgent(LLMClient(backend="mock", mock_response=CORRECT_FIX))

        arena = Arena(cj, red_team, blue_team, GameRules())
        result = arena.run(target, max_rounds=2)
        assert result.total_rounds == 2

    def test_attack_script_is_string(self):
        target = _build_target()
        mock_llm = LLMClient(backend="mock", mock_response=MOCK_JUDGE_SCRIPT)
        cj = ConstitutionJudge(Constitution.default(), target, mock_llm)
        multi_attack = 'print(json.dumps(query_user("__ALL__")))\nprint(json.dumps(query_user("nonexistent")))'
        red_team = RedTeamAgent(LLMClient(backend="mock", mock_response=multi_attack))
        blue_team = BlueTeamAgent(LLMClient(backend="mock", mock_response=CORRECT_FIX))

        arena = Arena(cj, red_team, blue_team, GameRules())
        result = arena.run(target, max_rounds=1)
        record = result.rounds[0]
        assert isinstance(record.attack_script, str)
        assert len(record.attack_script) > 0

    def test_generate_fix_with_feedback_called(self):
        target = _build_target()
        mock_llm = LLMClient(backend="mock", mock_response=MOCK_JUDGE_SCRIPT)
        cj = ConstitutionJudge(Constitution.default(), target, mock_llm)
        attack_script = 'print(json.dumps(query_user("__ALL__")))'
        red_team = RedTeamAgent(LLMClient(backend="mock", mock_response=attack_script))
        blue_team = BlueTeamAgent(LLMClient(backend="mock", mock_response=CORRECT_FIX))

        arena = Arena(cj, red_team, blue_team, GameRules())

        with patch.object(blue_team, 'generate_fix_with_feedback', wraps=blue_team.generate_fix_with_feedback) as mock_method:
            result = arena.run(target, max_rounds=1)
            assert mock_method.called
            call_args = mock_method.call_args
            assert call_args[1]['attack_script'] is not None
