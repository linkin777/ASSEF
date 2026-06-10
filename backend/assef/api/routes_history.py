"""ASSEF 历史记录路由 —— 提供历史记录的查询、详情和删除接口

路由前缀: /api/history
- GET /api/history/list —— 分页列出历史记录
- GET /api/history/detail/{record_id} —— 获取单条记录完整内容
- DELETE /api/history/{record_id} —— 删除指定记录
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..history import list_records, get_detail, delete_record
from ..logging_config import get_logger

_logger = get_logger("api.history")

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/list")
async def history_list(
    type: str | None = Query(None, description="筛选类型: arena 或 benchmark"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
):
    """分页获取历史记录列表

    Args:
        type: 可选筛选类型（arena / benchmark），不传则返回全部
        page: 页码（从 1 开始）
        page_size: 每页条数（1-100）

    Returns:
        dict: {"items": [...], "total": int, "page": int, "page_size": int}
    """
    return list_records(record_type=type, page=page, page_size=page_size)


@router.get("/detail/{record_id}")
async def history_detail(record_id: str):
    """获取指定历史记录的完整内容

    Args:
        record_id: 记录 ID（文件名不含扩展名）

    Returns:
        dict: 完整记录数据

    Raises:
        HTTPException: 404 - 记录不存在
    """
    data = get_detail(record_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"记录 {record_id} 不存在")
    return data


@router.delete("/{record_id}")
async def history_delete(record_id: str):
    """删除指定历史记录

    Args:
        record_id: 记录 ID（文件名不含扩展名）

    Returns:
        dict: {"status": "deleted", "record_id": str}

    Raises:
        HTTPException: 404 - 记录不存在
    """
    if not delete_record(record_id):
        raise HTTPException(status_code=404, detail=f"记录 {record_id} 不存在")
    return {"status": "deleted", "record_id": record_id}
