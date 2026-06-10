"""测试 ConstitutionJudge 宪法判官的脚本生成、攻击判定和正常功能测试。"""

import importlib.util
from pathlib import Path
import pytest
from assef.llm import LLMClient
from assef.models import Constitution
from assef.judge import ConstitutionJudge
from assef.models import TargetSpec

MOCK_JUDGE_SCRIPT = '''
def judge(inputs):
    results = []
    attack_success = False
    for inp in inputs:
        actual = inp.get("actual_output", "")
        passed = "flag{" in actual
        if passed:
            attack_success = True
        results.append({"name": inp["name"], "passed": passed, "reason": "found flag" if passed else "no flag"})
    return {"attack_success": attack_success, "results": results}
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


class TestConstitutionJudge:
    """测试 ConstitutionJudge 的初始化脚本生成、攻击判定（漏洞/修复）和正常功能测试。"""

    def test_initialization_generates_script(self):
        target = _build_target()
        mock_llm = LLMClient(backend="mock", mock_response=MOCK_JUDGE_SCRIPT)
        cj = ConstitutionJudge(Constitution.default(), target, mock_llm)
        assert cj.judge_script is None
        cj._ensure_script()
        assert cj.judge_script is not None
        assert "def judge(" in cj.judge_script

    def test_judge_attack_with_vulnerable_code(self):
        target = _build_target()
        mock_llm = LLMClient(backend="mock", mock_response=MOCK_JUDGE_SCRIPT)
        cj = ConstitutionJudge(Constitution.default(), target, mock_llm)
        report = cj.judge_attack(target.code, [{"name": "__ALL__"}])
        assert report.attack_success is True
        assert report.passed >= 1

    def test_judge_attack_with_fixed_code(self):
        target = _build_target()
        mock_llm = LLMClient(backend="mock", mock_response=MOCK_JUDGE_SCRIPT)
        cj = ConstitutionJudge(Constitution.default(), target, mock_llm)
        fixed_code = '''
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
        report = cj.judge_attack(fixed_code, [{"name": "__ALL__"}])
        assert report.attack_success is False

    def test_judge_normal(self):
        target = _build_target()
        mock_llm = LLMClient(backend="mock", mock_response=MOCK_JUDGE_SCRIPT)
        cj = ConstitutionJudge(Constitution.default(), target, mock_llm)
        report = cj.judge_normal(target.code)
        assert report.total_tests == 2
