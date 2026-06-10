"""测试红蓝判三方输出集成验证：红队攻击脚本、蓝队修复代码、判官判定、端到端全流程。"""

import json
import pytest

from assef.llm import LLMClient
from assef.models import TargetSpec, Constitution, GameRules
from assef.agents import RedTeamAgent, BlueTeamAgent
from assef.judge import ConstitutionJudge
from assef.sandbox import ProcessSandbox


VULNERABLE_CODE = '''
import json
import sys

USERS = {
    "admin": {"flag": "SECRET_FLAG{admin_access}", "data": "admin_data"},
    "guest": {"info": "public_data"}
}

def lookup(name):
    return USERS.get(name, {"error": "not found"})

if __name__ == "__main__":
    data = json.loads(sys.stdin.read())
    result = lookup(data.get("name", ""))
    print(json.dumps(result))
'''.strip()

FIXED_CODE = '''
import json
import sys

USERS = {
    "admin": {"flag": "SECRET_FLAG{admin_access}", "data": "admin_data"},
    "guest": {"info": "public_data"}
}

def lookup(name):
    if name == "admin":
        return {"error": "access denied"}
    return USERS.get(name, {"error": "not found"})

if __name__ == "__main__":
    data = json.loads(sys.stdin.read())
    result = lookup(data.get("name", ""))
    print(json.dumps(result))
'''.strip()

MOCK_JUDGE_SCRIPT = '''
def judge(inputs):
    results = []
    for inp in inputs:
        actual = inp.get("actual_output", "")
        passed = "SECRET_FLAG" in actual or "admin_data" in actual
        results.append({"name": inp["name"], "passed": passed, "reason": "attack leaked sensitive data" if passed else "attack blocked"})
    attack_success = any(r["passed"] for r in results)
    return {"attack_success": attack_success, "results": results}
'''.strip()

MOCK_ATTACK_SCRIPT = 'print(json.dumps(lookup("admin")))'

MOCK_FIX_CODE_MARKDOWN = f'''Here is the fixed code:

```python
{FIXED_CODE}
```

This fix blocks admin access.'''


def _make_target() -> TargetSpec:
    return TargetSpec.model_validate({
        "name": "test-vuln-system",
        "description": "A simple user lookup system with a vulnerability",
        "sandbox_type": "process",
        "sandbox_spec": {},
        "code": VULNERABLE_CODE,
        "public_spec": 'Input: JSON {"name": "..."}, Output: JSON user data or error',
        "attack_surface": "name parameter can be abused to access admin data",
        "success_criteria": {
            "attack": "SECRET_FLAG",
            "fix": "Block admin access to sensitive data"
        },
        "normal_tests": [
            {"name": "query guest", "input": {"name": "guest"}, "expected_output": {"info": "public_data"}},
            {"name": "query nonexistent", "input": {"name": "nobody"}, "expected_output": {"error": "not found"}},
        ],
    })


def test_red_team_attack_script():
    print("\n=== 红队输出验证: test_red_team_attack_script ===")

    target = _make_target()

    call_records = []

    def record_cb(record):
        call_records.append(record)

    mock_llm = LLMClient(
        backend="mock",
        mock_response=MOCK_ATTACK_SCRIPT,
        on_call_record=record_cb,
    )
    agent = RedTeamAgent(mock_llm)
    script = agent.generate_attack(target)

    print(f"红队攻击脚本长度: {len(script)}")
    assert isinstance(script, str), "返回应是字符串"
    assert len(script) >= 1, "攻击脚本不应为空"
    assert "lookup" in script or "print" in script, "攻击脚本应包含函数调用"
    print(f"  攻击脚本:\n{script}")

    assert len(call_records) >= 1, "on_call_record应被调用"
    rec = call_records[0]
    print(f"on_call_record回调: backend={rec.get('backend')}, call_context={rec.get('call_context')}")
    assert rec.get("backend") == "mock"
    assert rec.get("call_context", {}).get("caller") == "red_team"

    print("=== 红队输出验证通过 ===\n")


def test_blue_team_fix():
    print("\n=== 蓝队输出验证: test_blue_team_fix ===")

    target = _make_target()

    call_records = []

    def record_cb(record):
        call_records.append(record)

    mock_llm = LLMClient(
        backend="mock",
        mock_response=MOCK_FIX_CODE_MARKDOWN,
        on_call_record=record_cb,
    )
    agent = BlueTeamAgent(mock_llm)
    fixed = agent.generate_fix(target)

    print(f"蓝队修复代码长度: {len(fixed)} 字符")
    print(f"修复代码内容:\n{fixed}")

    assert isinstance(fixed, str), "返回应是字符串"
    assert len(fixed) > 0, "修复代码不应为空"
    assert "def lookup" in fixed, "修复代码应包含函数定义"
    assert "access denied" in fixed, "修复代码应包含access denied逻辑"

    assert len(call_records) >= 1, "on_call_record应被调用"
    rec = call_records[0]
    assert rec.get("call_context", {}).get("caller") == "blue_team"

    from assef.agents.blue_team import _extract_code
    extracted = _extract_code(FIXED_CODE)
    assert extracted == FIXED_CODE
    print("markdown代码块提取验证通过")

    print("=== 蓝队输出验证通过 ===\n")


def test_judge_attack():
    print("\n=== 判官输出验证: test_judge_attack ===")

    target = _make_target()
    constitution = Constitution.default()

    call_records = []

    def record_cb(record):
        call_records.append(record)

    mock_llm = LLMClient(
        backend="mock",
        mock_response=MOCK_JUDGE_SCRIPT,
        on_call_record=record_cb,
    )

    sandbox = ProcessSandbox(timeout=30.0)
    cj = ConstitutionJudge(constitution, target, mock_llm)

    attack_inputs = [{"name": "admin"}, {"name": "guest"}]
    report = cj.judge_attack(target.code, attack_inputs)

    print(f"判定报告:")
    print(f"  total_tests={report.total_tests}, passed={report.passed}, failed={report.failed}")
    print(f"  attack_success={report.attack_success}")

    for detail in report.details:
        print(f"  测试: {detail.test_name}, passed={detail.passed}, error={detail.error}")
        actual_preview = detail.actual_output[:150] if detail.actual_output else "(empty)"
        print(f"    actual_output: {actual_preview}")

    assert report.total_tests >= 1, "至少应有一个测试"
    assert isinstance(report.attack_success, bool), "attack_success应为布尔值"

    assert len(call_records) >= 1, "on_call_record应被调用"
    rec = call_records[-1]
    print(f"on_call_record回调: caller={rec.get('call_context', {}).get('caller')}")

    sandbox_result = sandbox.execute(target.code, {"name": "admin"})
    print(f"\nProcessSandbox直接执行:")
    print(f"  exit_code={sandbox_result.exit_code}, timed_out={sandbox_result.timed_out}")
    print(f"  stdout: {sandbox_result.stdout}")
    assert sandbox_result.exit_code == 0
    assert "SECRET_FLAG" in sandbox_result.stdout

    print("=== 判官输出验证通过 ===\n")


def test_e2e_full_flow():
    print("\n" + "=" * 60)
    print("=== 端到端集成测试: test_e2e_full_flow ===")
    print("=" * 60)

    target = _make_target()
    constitution = Constitution.default()

    print("\n[步骤1] 红队生成攻击脚本...")
    red_llm = LLMClient(backend="mock", mock_response=MOCK_ATTACK_SCRIPT)
    red_agent = RedTeamAgent(red_llm)
    attack_script = red_agent.generate_attack(target)

    print(f"  攻击脚本长度: {len(attack_script)}")
    print(f"  攻击脚本:\n{attack_script}")

    assert isinstance(attack_script, str), "攻击脚本应为字符串"
    assert len(attack_script) > 0, "攻击脚本不应为空"

    print("\n[步骤2] 沙箱执行联合代码...")
    from assef.judge.judge import _execute_in_sandbox
    combined_code = target.code + "\n\n" + attack_script
    stdout, stderr, exit_code, timed_out, elapsed = _execute_in_sandbox(combined_code, {})
    print(f"  沙箱结果: exit_code={exit_code}, timed_out={timed_out}, elapsed={elapsed:.3f}s")
    print(f"  stdout: {stdout[:200]}")
    print(f"  stderr: {stderr[:200]}")

    print("\n[步骤3] 判官判定攻击...")
    judge_llm = LLMClient(backend="mock", mock_response=MOCK_JUDGE_SCRIPT)
    cj = ConstitutionJudge(constitution, target, judge_llm)
    cj.ensure_script()

    exec_result = [{
        "name": "attack_execution",
        "input": {},
        "expected_output": None,
        "actual_output": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "elapsed_time": elapsed,
    }]
    local_env = {}
    exec(cj.judge_script, {"__builtins__": __builtins__}, local_env)
    judge_func = local_env.get("judge")
    judge_result = judge_func(exec_result)
    attack_success = judge_result.get("attack_success", False)
    print(f"  判官结果: attack_success={attack_success}")
    print(f"  judge函数返回: {judge_result}")

    print("\n[步骤4] 蓝队生成修复代码...")
    blue_llm = LLMClient(backend="mock", mock_response=FIXED_CODE)
    blue_agent = BlueTeamAgent(blue_llm)
    fixed_code = blue_agent.generate_fix(target)

    print(f"  修复代码长度: {len(fixed_code)} 字符")
    assert "access denied" in fixed_code, "修复代码应包含access denied逻辑"

    print("\n[步骤5] 判官判定修复后防御...")
    fix_judge_llm = LLMClient(backend="mock", mock_response=MOCK_JUDGE_SCRIPT)
    fix_cj = ConstitutionJudge(constitution, target, fix_judge_llm)
    fix_cj.ensure_script()

    defense_report = fix_cj.judge_defense(
        fixed_code,
        [{"attack_script": attack_script[:500], "attack_output": stdout[:200]}],
        len(target.code.splitlines()),
        len(fixed_code.splitlines()),
    )
    print(f"  防御结果: defense_passed={defense_report.defense_passed}, cost_score={defense_report.cost_score:.3f}")
    print(f"  测试详情: passed={defense_report.passed}/{defense_report.total_tests}, failed={defense_report.failed}")

    print("\n[验证] 全链路结果汇总:")
    print(f"  攻击成功 (攻击脚本直接执行): {attack_success}")
    print(f"  修复代码非空: {len(fixed_code) > 0}")
    print(f"  判官脚本已生成: {fix_cj.judge_script is not None}")
    print(f"  防御评估通过: {defense_report.defense_passed}")

    assert len(fixed_code) > 0, "修复代码不应为空"
    assert fix_cj.judge_script is not None, "判官脚本应已生成"

    print("=" * 60)
    print("=== 端到端集成测试完成 ===\n")
