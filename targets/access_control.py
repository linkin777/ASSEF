"""访问控制系统 —— 靶机代码

一个基于角色的访问控制系统，根据 resource_id 和 role 判断是否有权限访问资源。
漏洞类型：逻辑绕过 —— role 参数直接来自用户输入，未做服务端身份校验，
攻击者可篡改 role 字段越权访问管理员资源。
"""
import json
import sys

RESOURCES = {
    "public_info": {
        "name": "公开信息",
        "content": "这是一个所有人都可以访问的公开页面。",
        "required_role": "user",
    },
    "user_profile": {
        "name": "用户资料",
        "content": "这是你的个人资料页面。",
        "required_role": "user",
    },
    "admin_data": {
        "name": "管理员面板",
        "content": "管理员仪表盘数据 —— 系统运行正常，当前在线用户 42 人。",
        "required_role": "admin",
    },
    "admin_secrets": {
        "name": "管理员机密",
        "content": "机密信息：flag{access_control_bypass_2024}",
        "required_role": "admin",
    },
}

ROLE_HIERARCHY = {
    "admin": ["admin", "user"],
    "user": ["user"],
}


def get_resource(resource_id: str, role: str) -> dict | None:
    """按 resource_id 和 role 查询资源。

    漏洞：role 参数直接来自用户输入，未做服务端身份验证。
    正常用户只能传入 role="user"，但攻击者可篡改为 role="admin" 越权。
    """
    resource = RESOURCES.get(resource_id)
    if resource is None:
        return None
    allowed_roles = ROLE_HIERARCHY.get(role, [])
    if resource["required_role"] in allowed_roles:
        return resource
    return None


if __name__ == "__main__":
    input_data = json.loads(sys.stdin.read())
    resource_id = input_data.get("resource_id", "")
    role = input_data.get("role", "user")
    result = get_resource(resource_id, role)
    if result is None:
        if resource_id not in RESOURCES:
            print(json.dumps({"error": "resource not found"}))
        else:
            print(json.dumps({"error": "access denied"}))
    else:
        print(json.dumps(result))
