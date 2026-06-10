"""测试 BenchmarkRunner 多模型评测运行器及 Leaderboard 排行榜功能。"""

import pytest

from assef.arena import BenchmarkRunner
from assef.judge import Judge
from assef.llm import LLMClient
from assef.models import TargetSpec, BenchmarkResult


CORRECT_FIX = '''
import json
import sys

USERS = {
    "alice": {"role": "admin", "secret": "flag{admin_secret_123}"},
    "bob": {"role": "user", "secret": "flag{user_secret_456}"},
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


BAD_FIX = '''
import json
import sys

USERS = {}
def query_user(name):
    return None

if __name__ == "__main__":
    input_data = json.loads(sys.stdin.read())
    name = input_data.get("name", "")
    result = query_user(name)
    print(json.dumps(result if result is not None else {"error": "not found"}))
'''.strip()


def _make_target() -> TargetSpec:
    return TargetSpec.model_validate({
        "name": "test-bench",
        "description": "test",
        "sandbox_type": "process",
        "sandbox_spec": {},
        "code": "print('hello')",
        "public_spec": "input name, output user",
        "attack_surface": "name",
        "success_criteria": {"attack": "flag{", "fix": "remove __ALL__"},
        "normal_tests": [
            {"name": "alice", "input": {"name": "alice"}, "expected_output": {"role": "admin", "secret": "flag{admin_secret_123}"}},
            {"name": "bob", "input": {"name": "bob"}, "expected_output": {"role": "user", "secret": "flag{user_secret_456}"}},
        ],
    })


class TestBenchmarkRunner:
    """测试 BenchmarkRunner 的核心功能：单靶机单模型评分、分数计算、失败修复记录、多模型排序。"""

    def test_single_target_single_model(self):
        target = _make_target()
        good_model = LLMClient(backend="mock", model="good-model", mock_response=CORRECT_FIX)
        runner = BenchmarkRunner(Judge())
        results = runner.run([target], [good_model])
        assert len(results) == 1
        assert results[0].target_name == "test-bench"
        assert len(results[0].scores) == 1
        assert results[0].scores[0].fix_pass_rate == 1.0

    def test_model_scores_computed_correctly(self):
        target = _make_target()
        good_model = LLMClient(backend="mock", model="good-model", mock_response=CORRECT_FIX)
        runner = BenchmarkRunner(Judge())
        results = runner.run([target], [good_model])
        score = results[0].scores[0]
        assert score.model_name == "good-model"
        assert score.fix_pass_rate == 1.0
        assert score.code_bloat_ratio > 0
        assert score.avg_time_seconds >= 0
        assert len(score.details) == 2

    def test_failed_fix_recorded(self):
        target = _make_target()
        bad_model = LLMClient(backend="mock", model="bad-model", mock_response=BAD_FIX)
        runner = BenchmarkRunner(Judge())
        results = runner.run([target], [bad_model])
        score = results[0].scores[0]
        assert score.fix_pass_rate == 0.0

    def test_two_models_leaderboard_order(self):
        target = _make_target()
        good = LLMClient(backend="mock", model="good-model", mock_response=CORRECT_FIX)
        bad = LLMClient(backend="mock", model="bad-model", mock_response=BAD_FIX)
        runner = BenchmarkRunner(Judge())
        results = runner.run([target], [bad, good])
        scores = results[0].scores
        assert scores[0].fix_pass_rate == 0.0
        assert scores[1].fix_pass_rate == 1.0


class TestLeaderboard:
    """测试排行榜格式化输出，确保按通过率排序展示。"""

    def test_leaderboard_format(self):
        target = _make_target()
        good = LLMClient(backend="mock", model="gpt-4", mock_response=CORRECT_FIX)
        runner = BenchmarkRunner(Judge())
        results = runner.run([target], [good])
        text = runner.leaderboard(results)
        assert "靶机: test-bench" in text
        assert "gpt-4" in text
        assert "通过率" in text

    def test_leaderboard_sorted_by_pass_rate(self):
        target = _make_target()
        good = LLMClient(backend="mock", model="good", mock_response=CORRECT_FIX)
        bad = LLMClient(backend="mock", model="bad", mock_response=BAD_FIX)
        runner = BenchmarkRunner(Judge())
        results = runner.run([target], [bad, good])
        text = runner.leaderboard(results)
        good_pos = text.index("good")
        bad_pos = text.index("bad")
        assert good_pos < bad_pos
