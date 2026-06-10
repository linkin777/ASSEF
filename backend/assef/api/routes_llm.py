"""ASSEF LLM 连接测试路由 —— 提供大模型后端连接验证接口

路由前缀: /api/llm
- POST /api/llm/test —— 测试指定 LLM 后端的连接可用性
"""

from fastapi import APIRouter

from ..llm.llm_client import LLMClient
from ..models.config import LLMBackendConfig

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.post("/test")
async def test_llm_connection(config: LLMBackendConfig) -> dict:
    """测试 LLM 后端连接

    使用给定的后端配置创建客户端并发起连接测试。

    Args:
        config: LLM 后端配置（含 backend、model、endpoint、api_key 等字段）

    Returns:
        dict: {"ok": bool, "message": str} —— ok 表示连接成功，message 包含验证信息或错误描述
    """
    try:
        client = LLMClient.from_config(config)
        is_ok, message = client.test_connection()
        return {"ok": is_ok, "message": message}
    except Exception as e:
        return {"ok": False, "message": str(e)}
