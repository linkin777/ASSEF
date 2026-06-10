"""ASSEF 任务控制路由 —— 提供后台任务的暂停/恢复/取消/查询接口

路由前缀: /api/task
- POST /api/task/{task_id}/pause   —— 暂停指定任务
- POST /api/task/{task_id}/resume  —— 恢复指定任务
- POST /api/task/{task_id}/cancel  —— 取消指定任务
- GET  /api/task/{task_id}         —— 查询单个任务状态
- GET  /api/task                   —— 查询所有任务状态
"""

from fastapi import APIRouter

from ..core.executor import BackgroundExecutor

router = APIRouter(prefix="/api/task", tags=["task"])


@router.post("/{task_id}/pause")
async def pause_task(task_id: str):
    """暂停指定任务

    Args:
        task_id: 任务唯一标识符

    Returns:
        dict: {"ok": bool} 操作是否成功
    """
    ok = BackgroundExecutor().pause_task(task_id)
    return {"ok": ok}


@router.post("/{task_id}/resume")
async def resume_task(task_id: str):
    """恢复指定任务

    Args:
        task_id: 任务唯一标识符

    Returns:
        dict: {"ok": bool} 操作是否成功
    """
    ok = BackgroundExecutor().resume_task(task_id)
    return {"ok": ok}


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """取消指定任务

    Args:
        task_id: 任务唯一标识符

    Returns:
        dict: {"ok": bool} 操作是否成功
    """
    ok = BackgroundExecutor().cancel_task(task_id)
    return {"ok": ok}


@router.get("/{task_id}")
async def get_task(task_id: str):
    """查询单个任务的当前状态

    Args:
        task_id: 任务唯一标识符

    Returns:
        dict: 任务状态信息（含运行状态、进度等）
    """
    return BackgroundExecutor().get_task_status(task_id)


@router.get("")
async def get_all_tasks():
    """查询所有后台任务的当前状态

    Returns:
        list[dict]: 所有任务的状态信息列表
    """
    return BackgroundExecutor().get_all_tasks()
