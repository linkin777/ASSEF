"""演示 ASSEF 模式A —— 红蓝对抗斗兽场：使用 Mock LLM 运行完整 Arena 对抗流程并输出回合详情。"""

import importlib.util
import json
import time
from pathlib import Path

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


example_path = Path(__file__).parent / "simple_user_query.py"
spec_mod = importlib.util.spec_from_file_location("simple_user_query", example_path)
module = importlib.util.module_from_spec(spec_mod)
spec_mod.loader.exec_module(module)
data = module.SIMPLE_USER_QUERY_DATA

target = TargetSpec.model_validate(data)

constitution = Constitution.default()

judge_llm = LLMClient(backend="mock", mock_response=MOCK_JUDGE_SCRIPT)
cj = ConstitutionJudge(constitution, target, judge_llm)

attack_script = 'print(json.dumps(query_user("__ALL__")))'
red_llm = LLMClient(backend="mock", mock_response=attack_script)
red_team = RedTeamAgent(red_llm)

blue_llm = LLMClient(backend="mock", mock_response=CORRECT_FIX)
blue_team = BlueTeamAgent(blue_llm)

rules = GameRules(max_arena_rounds=3, max_blue_retries=2)

arena = Arena(cj, red_team, blue_team, rules)

print("=" * 60)
print("ASSEF 模式A —— 红蓝对抗斗兽场")
print("=" * 60)
print(f"靶机: {target.name}")
print(f"回合数: {rules.max_arena_rounds}")
print(f"宪法: {constitution.preamble[:60]}...")
print()

result = arena.run(target)

for record in result.rounds:
    print(f"--- 第 {record.round_num} 回合 ---")
    print(f"红队攻击脚本: {record.attack_script[:200]}...")
    if record.successful_attacks:
        print(f"成功攻击: {json.dumps(record.successful_attacks, ensure_ascii=False)[:200]}...")
    print(f"攻击结果: {'成功' if record.attack_success else '被拦截'}")
    if record.attack_output:
        print(f"输出: {record.attack_output[:200]}...")
    if record.defense_code:
        print(f"蓝队防御: {'通过' if record.defense_passed else '未通过'} (重试{record.blue_retries}次)")
        print(f"三色评估: {'🔴' if record.eval_red else '❌'}"
              f"{'🟡' if record.eval_yellow else '❌'}"
              f"{'🟢' if record.eval_green else '❌'}")
        print(f"性价比指数: {record.cost_score}")
    print()

print("=" * 60)
print(f"最终比分")
print(f"红队: {result.red_score} 分 vs 蓝队: {result.blue_score} 分")
print(f"总回合: {result.total_rounds}")
