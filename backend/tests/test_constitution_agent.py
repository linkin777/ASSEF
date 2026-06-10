import pytest
from assef.llm import LLMClient
from assef.models import Constitution
from assef.judge import ConstitutionAgent
from assef.judge.report_generator import ReportGenerator
from assef.judge.constitution_agent import _extract_function, _validate_script
from assef.models import TargetSpec

MOCK_JUDGE_SCRIPT = '''
def judge(inputs):
    results = []
    attack_success = False
    for inp in inputs:
        passed = "flag{" in inp.get("actual_output", "")
        if passed:
            attack_success = True
        results.append({"name": inp["name"], "passed": passed, "reason": "found flag" if passed else "no flag"})
    return {"attack_success": attack_success, "results": results}
'''.strip()

DANGEROUS_SCRIPT_OUTSIDE_FUNC = "import os\nos.system('rm -rf /')\n\ndef judge(inputs):\n    return {'attack_success': False, 'results': []}"

DANGEROUS_SCRIPT_INSIDE_FUNC = "def judge(inputs):\n    os.system('rm -rf /')\n    return {'attack_success': False, 'results': []}"

LLM_RESPONSE_NO_CODE_BLOCK = """Based on the constitution, I will create a judge function. The key idea is to check if the actual_output contains sensitive information.

Since we cannot use subprocess or os.system in the sandbox, and we need to avoid all dangerous patterns like eval, exec, and open, the function will use pure Python builtins only. We also cannot import os, sys, requests, or any other modules.

def judge(inputs, original_code_len=0, new_code_len=0):
    results = []
    attack_success = False
    for inp in inputs:
        actual = inp.get("actual_output", "")
        if "flag{" in actual:
            attack_success = True
            results.append({"name": inp["name"], "passed": True, "reason": "flag found in output"})
        else:
            results.append({"name": inp["name"], "passed": False, "reason": "no flag detected"})

    defense_passed = False
    return {
        "attack_success": attack_success,
        "defense_passed": defense_passed,
        "results": results,
        "cost_score": 0.0,
    }"""

LLM_RESPONSE_DANGEROUS_IN_CODE_BLOCK = """```python
def judge(inputs):
    import os
    results = []
    attack_success = False
    for inp in inputs:
        passed = "flag{" in inp.get("actual_output", "")
        if passed:
            attack_success = True
        results.append({"name": inp["name"], "passed": passed, "reason": "found flag" if passed else "no flag"})
    return {"attack_success": attack_success, "results": results}
```"""

LLM_RESPONSE_WITH_EXPLANATION = """Here is the judge function. Note that I avoid using subprocess and os.system.

```python
def judge(inputs):
    results = []
    attack_success = False
    for inp in inputs:
        passed = "flag{" in inp.get("actual_output", "")
        if passed:
            attack_success = True
        results.append({"name": inp["name"], "passed": passed, "reason": "found flag" if passed else "no flag"})
    return {"attack_success": attack_success, "results": results}
```"""


def _make_target() -> TargetSpec:
    return TargetSpec.model_validate({
        "name": "test",
        "description": "test target",
        "sandbox_type": "process",
        "sandbox_spec": {},
        "code": "print('ok')",
        "public_spec": "input name, output user",
        "attack_surface": "name",
        "success_criteria": {"attack": "flag{", "fix": "remove backdoor"},
        "normal_tests": [{"name": "alice", "input": {"name": "alice"}, "expected_output": {"role": "user"}}],
    })


class TestExtractFunction:
    """测试从 LLM 响应中提取 Python 代码函数。"""

    def test_extract_from_markdown(self):
        code = _extract_function("```python\nprint('hello')\n```")
        assert code == "print('hello')"

    def test_extract_no_markdown(self):
        code = _extract_function("print('hello')")
        assert code == "print('hello')"

    def test_extract_from_llm_response_with_dangerous_keywords_in_text(self):
        code = _extract_function(LLM_RESPONSE_WITH_EXPLANATION)
        assert "def judge(" in code
        assert "subprocess" not in code
        assert "os.system" not in code

    def test_extract_dangerous_outside_func_stripped(self):
        code = _extract_function(DANGEROUS_SCRIPT_OUTSIDE_FUNC)
        assert "def judge(" in code
        assert "os.system" not in code
        assert "import os" not in code


class TestValidateScript:
    """测试判官脚本安全验证：合法脚本通过，危险脚本被拒绝。"""

    def test_valid_script_passes(self):
        assert _validate_script(MOCK_JUDGE_SCRIPT) is True

    def test_dangerous_script_inside_func_rejected(self):
        assert _validate_script(DANGEROUS_SCRIPT_INSIDE_FUNC) is False

    def test_missing_judge_function_rejected(self):
        assert _validate_script("x = 1") is False


class TestConstitutionAgent:
    """测试 ConstitutionAgent 生成判官脚本及危险脚本拒绝功能。"""

    def test_generate_judge_script_with_mock_llm(self):
        constitution = Constitution.default()
        target = _make_target()
        mock_llm = LLMClient(backend="mock", mock_response=MOCK_JUDGE_SCRIPT)
        agent = ConstitutionAgent(mock_llm)
        script = agent.generate_judge_script(constitution, target)
        assert "def judge(" in script

    def test_dangerous_inside_func_raises(self):
        constitution = Constitution.default()
        target = _make_target()
        mock_llm = LLMClient(backend="mock", mock_response=DANGEROUS_SCRIPT_INSIDE_FUNC)
        agent = ConstitutionAgent(mock_llm)
        with pytest.raises(ValueError, match="validation"):
            agent.generate_judge_script(constitution, target)

    def test_llm_response_with_explanation_accepted(self):
        constitution = Constitution.default()
        target = _make_target()
        mock_llm = LLMClient(backend="mock", mock_response=LLM_RESPONSE_WITH_EXPLANATION)
        agent = ConstitutionAgent(mock_llm)
        script = agent.generate_judge_script(constitution, target)
        assert "def judge(" in script
        assert "subprocess" not in script
        assert "os.system" not in script

    def test_empty_response_retries_then_fails(self):
        constitution = Constitution.default()
        target = _make_target()
        mock_llm = LLMClient(backend="mock", mock_response="")
        agent = ConstitutionAgent(mock_llm)
        with pytest.raises(ValueError, match="empty"):
            agent.generate_judge_script(constitution, target)

    def test_no_code_block_with_dangerous_keywords_in_text_accepted(self):
        constitution = Constitution.default()
        target = _make_target()
        mock_llm = LLMClient(backend="mock", mock_response=LLM_RESPONSE_NO_CODE_BLOCK)
        agent = ConstitutionAgent(mock_llm)
        script = agent.generate_judge_script(constitution, target)
        assert "def judge(" in script
        assert "subprocess" not in script
        assert "os.system" not in script
        assert "import os" not in script

    def test_dangerous_in_code_block_raises(self):
        constitution = Constitution.default()
        target = _make_target()
        mock_llm = LLMClient(backend="mock", mock_response=LLM_RESPONSE_DANGEROUS_IN_CODE_BLOCK)
        agent = ConstitutionAgent(mock_llm)
        with pytest.raises(ValueError, match="validation"):
            agent.generate_judge_script(constitution, target)


class TestGenerateSummaryReport:
    """测试 ReportGenerator.generate_summary_report 报告生成功能。"""

    def test_generate_summary_report_returns_string(self):
        mock_response = """# 攻防对抗分析报告

## 1. 对抗双方策略分析
红队采用了SQL注入攻击策略...
蓝队通过参数化查询进行防御...

## 2. 关键攻防事件时间线
- 轮次1: 红队成功利用SQL注入获取flag
- 轮次2: 蓝队修复漏洞，攻击被拦截

## 3. 成功率统计与趋势分析
攻击成功率: 50%，防御成功率随时间提升

## 4. 系统漏洞与防御弱点评估
存在SQL注入漏洞，蓝队初次修复不完善

## 5. 优化建议
建议加强输入校验，使用参数化查询"""
        mock_llm = LLMClient(backend="mock", mock_response=mock_response)
        generator = ReportGenerator(mock_llm)

        constitution_text = "攻击成功判定：红队获取flag"
        arena_result = {
            "target_name": "user-query",
            "total_rounds": 2,
            "red_score": 10.0,
            "blue_score": 15.0,
        }
        events = [
            {
                "timestamp": "2025-01-01T00:00:00",
                "round_num": 1,
                "event_type": "ATTACK_GENERATED",
                "role": "red_team",
                "summary": "生成SQL注入攻击脚本",
            },
            {
                "timestamp": "2025-01-01T00:00:01",
                "round_num": 1,
                "event_type": "ATTACK_JUDGED",
                "role": "judge",
                "summary": "攻击成功",
            },
        ]

        report = generator.generate_summary_report("user-query", constitution_text, arena_result, events)
        assert isinstance(report, str)
        assert len(report) > 0
        assert "策略分析" in report
        assert "事件时间线" in report
        assert "成功率" in report
        assert "漏洞" in report
        assert "优化建议" in report

    def test_generate_summary_report_with_empty_events(self):
        mock_response = "报告内容：无事件记录的空报告"
        mock_llm = LLMClient(backend="mock", mock_response=mock_response)
        generator = ReportGenerator(mock_llm)

        report = generator.generate_summary_report("test-target", "", {}, [])
        assert isinstance(report, str)
        assert len(report) > 0
