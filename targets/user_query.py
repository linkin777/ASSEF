"""用户查询服务 —— 靶机代码

模拟用户数据库查询系统，通过 username 查询用户信息。
漏洞类型：SQL 注入 —— 未对用户输入做参数化处理，直接拼接查询条件，
导致攻击者可构造恶意输入泄露所有用户的敏感数据。
"""
import json
import sys

USERS = [
    {
        "username": "admin",
        "role": "admin",
        "email": "admin@assef.internal, flag{sqli_leak_all_users_2024}",
    },
    {
        "username": "alice",
        "role": "user",
        "email": "alice@example.com",
    },
    {
        "username": "bob",
        "role": "user",
        "email": "bob@example.com",
    },
]


def _match_condition(user: dict, condition_str: str) -> bool:
    """模拟 SQL WHERE 子句求值，支持简单 = 和 OR 逻辑。

    漏洞点：condition_str 由用户输入直接拼接而成，未做参数化处理，
    攻击者可注入 OR 子句绕过匹配逻辑。
    """
    or_clauses = condition_str.split(" OR ")
    for clause in or_clauses:
        clause = clause.strip()
        if "=" not in clause:
            continue
        left, right = clause.split("=", 1)
        left = left.strip()
        right = right.strip().strip("'")
        if left == "username":
            if user["username"] == right:
                return True
        # 注入利用点：'1'='1' 恒为真，使所有记录匹配
        elif left == "'1'":
            if right == "1":
                return True
    return False


def query_user(username: str) -> list[dict]:
    """按 username 查询用户。存在 SQL 注入漏洞 ——
    直接将 username 拼接到查询条件中，未做参数化处理。"""
    # 漏洞：直接拼接用户输入到查询条件字符串
    query = f"username = '{username}'"
    results = []
    for user in USERS:
        if _match_condition(user, query):
            results.append(user)
    return results


if __name__ == "__main__":
    input_data = json.loads(sys.stdin.read())
    username = input_data.get("username", "")
    results = query_user(username)
    if results:
        print(json.dumps({"users": results}, ensure_ascii=False))
    else:
        print(json.dumps({"error": "user not found"}, ensure_ascii=False))
