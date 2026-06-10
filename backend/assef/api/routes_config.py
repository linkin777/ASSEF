"""ASSEF 配置管理路由 —— 提供配置的读取与更新接口

路由前缀: /api/config
- GET  /api/config     —— 读取当前配置文件内容
- PUT  /api/config     —— 更新并持久化配置文件
"""

import json
from pathlib import Path

from fastapi import APIRouter, Request

from ..models.config import Config, load_config

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
async def get_config():
    """读取当前系统配置

    从 config.json 加载完整配置并返回。

    Returns:
        dict: 完整的配置数据字典
    """
    config = load_config("config.json")
    return config.model_dump(mode="json")


@router.put("")
async def update_config(request: Request):
    """更新系统配置并持久化到文件

    接收 JSON 格式的配置数据，校验后写入 config.json。

    Args:
        request: FastAPI 请求对象，请求体为 JSON 格式的完整配置

    Returns:
        dict: 更新后的配置数据字典

    Raises:
        由 Pydantic 模型校验触发的验证错误（FastAPI 自动处理）
    """
    data = await request.json()
    config = Config.model_validate(data)
    Path("config.json").write_text(
        json.dumps(config.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return config.model_dump(mode="json")
