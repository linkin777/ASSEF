"""
简易用户查询系统 —— 靶机样例数据

描述一个简单的内存用户数据库，支持按姓名查询用户信息。
攻击面：查询接口的 name 参数可被 SQL 注入风格利用。
"""
from assef.models import TargetSpec, SuccessCriteria, NormalTest

SIMPLE_USER_QUERY_DATA = {
    "name": "simple-user-query",
    "description": "简易用户查询系统：内存用户数据库，接受用户名查询返回用户信息",
    "sandbox_type": "process",
    "sandbox_spec": {
        "image": "python:3.13-slim",
        "timeout_seconds": 30,
        "memory_limit_mb": 256,
    },
    "code": '''
# 简易用户查询系统 —— 靶机代码
import json
import sys

USERS = {
    "alice": {"role": "admin", "secret": "flag{admin_secret_123}"},
    "bob": {"role": "user", "secret": "flag{user_secret_456}"},
    "charlie": {"role": "user", "secret": "flag{diorama_words_789}"},
}

def query_user(name: str) -> dict | None:
    """按名称查询用户。存在注入漏洞——若传入特殊字符串可泄露所有用户。"""
    if name == "__ALL__":
        return USERS
    return USERS.get(name)

if __name__ == "__main__":
    input_data = json.loads(sys.stdin.read())
    name = input_data.get("name", "")
    result = query_user(name)
    print(json.dumps(result if result is not None else {"error": "not found"}))
'''.strip(),
    "public_spec": """
接口描述（灰盒模式给红队）：
- 输入：JSON `{"name": "<username>"}`
- 输出：JSON 用户对象 `{"role": "...", "secret": "..."}`
- 未查到返回：`{"error": "not found"}`
- 注：系统有一个隐藏的超级查询参数 `__ALL__`
""".strip(),
    "attack_surface": "name",
    "success_criteria": {
        "attack": "红队成功获取到 alice 的 secret（即 flag{admin_secret_123}）",
        "fix": "不再存在 __ALL__ 后门；非法输入返回空或错误",
    },
    "normal_tests": [
        {
            "name": "查询存在的用户 alice",
            "input": {"name": "alice"},
            "expected_output": {"role": "admin", "secret": "flag{admin_secret_123}"},
        },
        {
            "name": "查询不存在的用户",
            "input": {"name": "nonexistent"},
            "expected_output": {"error": "not found"},
        },
    ],
}

if __name__ == "__main__":
    spec = TargetSpec.model_validate(SIMPLE_USER_QUERY_DATA)
    print(f"校验通过！靶机名称: {spec.name}")
    print(f"代码行数: {len(spec.code.splitlines())}")
    print(f"测试用例数: {len(spec.normal_tests)}")
