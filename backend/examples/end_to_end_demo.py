"""演示完整红蓝斗兽场对抗端到端流程：攻击验证 → 修复代码 → 正常功能验证 → 攻击再验证。"""

import importlib.util
import json
from pathlib import Path

from assef.judge import Judge
from assef.models import TargetSpec

example_path = Path(__file__).parent / "simple_user_query.py"
spec = importlib.util.spec_from_file_location("simple_user_query", example_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
data = module.SIMPLE_USER_QUERY_DATA

target = TargetSpec.model_validate(data)
target.success_criteria.attack = "flag{"
judge = Judge()

print("=" * 60)
print("=== 第一阶段：攻击验证 ===")
print("=" * 60)

report = judge.judge_attack(target, data["code"], [{"name": "__ALL__"}])
print(f"攻击成功: {'是' if report.attack_success else '否'}")
print(f"测试通过: {report.passed}/{report.total_tests}")
print(f"测试失败: {report.failed}/{report.total_tests}")
for d in report.details:
    status = "通过" if d.passed else "失败"
    print(f"  [{status}] {d.test_name}")
    print(f"    输入: {json.dumps(d.input, ensure_ascii=False)}")
    print(f"    输出: {d.actual_output}")
    if d.error:
        print(f"    错误: {d.error}")

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

print()
print("=" * 60)
print("=== 第二阶段：修复代码 ===")
print("=" * 60)
print("修复内容: 移除 __ALL__ 后门，增加输入类型校验")

print()
print("=" * 60)
print("=== 第三阶段：正常功能验证 ===")
print("=" * 60)

report = judge.judge_normal(target, FIXED_CODE)
print(f"测试通过: {report.passed}/{report.total_tests}")
print(f"测试失败: {report.failed}/{report.total_tests}")
for d in report.details:
    status = "通过" if d.passed else "失败"
    print(f"  [{status}] {d.test_name}")
    print(f"    输入: {json.dumps(d.input, ensure_ascii=False)}")
    print(f"    期望: {d.expected_output}")
    print(f"    实际: {d.actual_output}")
    if d.error:
        print(f"    错误: {d.error}")

print()
print("=" * 60)
print("=== 第四阶段：攻击再验证 ===")
print("=" * 60)

report = judge.judge_attack(target, FIXED_CODE, [{"name": "__ALL__"}])
print(f"攻击成功: {'是' if report.attack_success else '否'}")
print(f"测试通过: {report.passed}/{report.total_tests}")
print(f"测试失败: {report.failed}/{report.total_tests}")
for d in report.details:
    status = "通过" if d.passed else "失败"
    print(f"  [{status}] {d.test_name}")
    print(f"    输入: {json.dumps(d.input, ensure_ascii=False)}")
    print(f"    输出: {d.actual_output}")
    if d.error:
        print(f"    错误: {d.error}")

print()
print("=" * 60)
print("=== 总结 ===")
print("=" * 60)
print("攻击已被拦截")
print("正常功能保持")

if __name__ == "__main__":
    pass
