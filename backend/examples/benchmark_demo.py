"""演示 ASSEF 模式B —— 多模型修 Bug 评测排行榜：使用 Mock LLM 对比不同模型的修复通过率和排行榜。"""

import importlib.util
import json
from pathlib import Path

from assef.arena import BenchmarkRunner
from assef.judge import Judge
from assef.llm import LLMClient
from assef.models import TargetSpec
from assef.models.config import LLMBackendConfig


GOOD_FIX = '''
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


BAD_FIX = '''
import json
import sys

USERS = {}

if __name__ == "__main__":
    input_data = json.loads(sys.stdin.read())
    name = input_data.get("name", "")
    print(json.dumps({"error": "not found"}))
'''.strip()


example_path = Path(__file__).parent / "simple_user_query.py"
spec_mod = importlib.util.spec_from_file_location("simple_user_query", example_path)
module = importlib.util.module_from_spec(spec_mod)
spec_mod.loader.exec_module(module)
data = module.SIMPLE_USER_QUERY_DATA

target = TargetSpec.model_validate(data)

good_model = LLMClient(backend="mock", model="GPT-4o-mini", mock_response=GOOD_FIX)
bad_model = LLMClient(backend="mock", model="Poor-Local-Model", mock_response=BAD_FIX)

good_config = LLMBackendConfig(backend="mock", model="GPT-4o-mini", mock_response=GOOD_FIX)
good_model_from_config = LLMClient.from_config(good_config)
assert good_model_from_config._backend == "mock"

print("=" * 60)
print("ASSEF 模式B —— 多模型修Bug评测排行榜")
print("=" * 60)
print(f"靶机数量: 1")
print(f"模型数量: 2")
print(f"LLMClient.from_config() 已演示")
print()

runner = BenchmarkRunner(Judge())
results = runner.run([target], [bad_model, good_model])

print(runner.leaderboard(results))

print("=" * 60)
print("详细报告")
print("=" * 60)

for br in results:
    for score in br.scores:
        status = "PASS" if score.fix_pass_rate == 1.0 else "FAIL"
        print(f"\n模型: {score.model_name} [{status}]")
        print(f"  通过率: {score.fix_pass_rate:.2%}")
        print(f"  代码膨胀率: {score.code_bloat_ratio:.2f}x")
        print(f"  耗时: {score.avg_time_seconds:.4f}s")
        print(f"  测试详情:")
        for d in score.details:
            s = "PASS" if d["passed"] else "FAIL"
            err = f" ({d['error']})" if d.get("error") else ""
            print(f"    [{s}] {d['test_name']}{err}")
