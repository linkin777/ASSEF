import importlib.util
from pathlib import Path

import pytest

from assef.judge import Judge
from assef.models import TargetSpec

FIXED_CODE = '''
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


def _build_target(attack_keyword="flag{"):
    data = _load_example_data()
    data = dict(data)
    data["success_criteria"] = {
        "attack": attack_keyword,
        "fix": data["success_criteria"]["fix"],
    }
    return TargetSpec.model_validate(data)


class TestJudgeAttack:
    """测试判官攻击判定：有漏洞代码攻击成功，修复后代码攻击被拦截。"""

    def test_attack_succeeds_with_vulnerable_code(self):
        target = _build_target()
        judge = Judge()
        vulnerable_code = _load_example_data()["code"]
        report = judge.judge_attack(target, vulnerable_code, [{"name": "__ALL__"}])
        assert report.attack_success is True
        assert report.passed >= 1

    def test_attack_blocked_with_fixed_code(self):
        target = _build_target()
        judge = Judge()
        report = judge.judge_attack(target, FIXED_CODE, [{"name": "__ALL__"}])
        assert report.attack_success is False


class TestJudgeNormal:
    def test_normal_tests_pass_with_fixed_code(self):
        target = _build_target()
        judge = Judge()
        report = judge.judge_normal(target, FIXED_CODE)
        assert report.passed == 2
        assert report.failed == 0

    def test_normal_tests_pass_with_vulnerable_code(self):
        target = _build_target()
        judge = Judge()
        vulnerable_code = _load_example_data()["code"]
        report = judge.judge_normal(target, vulnerable_code)
        assert report.passed == 2
        assert report.failed == 0
