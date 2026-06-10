"""ASSEF FastAPI 应用工厂模块 —— 创建 FastAPI 实例并配置 CORS/WebSocket/路由

本模块负责：
- 创建 FastAPI 应用实例并挂载所有 API 路由（竞技场、基准测试、配置、LLM、任务控制）
- 配置 CORS 中间件（允许跨域请求）
- 提供 WebSocket 端点用于实时任务进度推送
- 提供健康检查端点
- 提供 main() 函数用于通过 uvicorn 命令行或直接调用启动服务器
"""

from __future__ import annotations

import asyncio
import argparse
import sys

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from ..recorder import get_prompt_recorder
from .routes_arena import router as arena_router
from .routes_benchmark import router as benchmark_router, _task_dispatchers
from .routes_history import router as history_router
from .routes_llm import router as llm_router
from .routes_task import router as task_router
from . import routes_config
from ..core.progress import ProgressEvent
from ..logging_config import get_logger

_logger = get_logger("api.server")

app = FastAPI(title="ASSEF API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(arena_router)
app.include_router(benchmark_router)
app.include_router(history_router)
app.include_router(routes_config.router)
app.include_router(llm_router)
app.include_router(task_router)


@app.get("/api/health")
async def health_check():
    """健康检查端点

    用于服务存活探针，始终返回 ok 状态和版本号。

    Returns:
        dict: {"status": "ok", "version": "0.1.0"}
    """
    return {"status": "ok", "version": "0.1.0"}


@app.websocket("/ws/task/{task_id}")
async def ws_task(websocket: WebSocket, task_id: str):
    """WebSocket 任务进度推送端点

    客户端连接后，服务端通过 ProgressDispatcher 注册回调，
    将任务执行过程中的所有 ProgressEvent 实时推送给客户端。
    连接断开会自动清理回调。

    Args:
        websocket: FastAPI WebSocket 连接对象
        task_id: 任务唯一标识符，用于查找对应的 ProgressDispatcher
    """
    await websocket.accept()
    _logger.info("WebSocket connected: task_id=%s client=%s", task_id, websocket.client)

    dispatcher = _task_dispatchers.get(task_id)
    if dispatcher is None:
        _logger.warning("WebSocket task not found: task_id=%s available=%s", task_id, list(_task_dispatchers.keys()))
        await websocket.send_json({
            "type": "error",
            "data": {"message": f"任务不存在: {task_id}"},
        })
        await websocket.close()
        return

    _logger.info("WebSocket dispatcher found: task_id=%s", task_id)
    loop = asyncio.get_running_loop()
    event_count = 0

    async def send_event(event: ProgressEvent) -> None:
        nonlocal event_count
        try:
            event_count += 1
            await websocket.send_json({
                "type": event.type,
                "role": event.role,
                "step_name": event.step_name,
                "content": event.content,
                "data": event.data,
                "timestamp": event.timestamp,
            })
        except Exception:
            pass

    def _on_progress(event: ProgressEvent) -> None:
        asyncio.run_coroutine_threadsafe(send_event(event), loop)

    dispatcher.register(_on_progress)

    try:
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        _logger.info("WebSocket disconnected: task_id=%s events_sent=%d", task_id, event_count)
    finally:
        dispatcher.unregister(_on_progress)
        _logger.info("WebSocket cleaned up: task_id=%s", task_id)


def main(record_prompts: str | None = None):
    """启动 ASSEF API 服务器

    配置可选的提示词记录功能后，通过 uvicorn 启动 FastAPI 应用。

    Args:
        record_prompts: 提示词记录输出目录路径，若为 None 则不启用记录功能
    """
    import uvicorn

    if record_prompts:
        recorder = get_prompt_recorder(record_prompts)
        app.state.prompt_recorder = recorder
        print(f"[recorder] Prompt recording enabled, output: {record_prompts}")
    else:
        app.state.prompt_recorder = None

    uvicorn.run("assef.api.server:app", host="0.0.0.0", port=8710, reload=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ASSEF API Server")
    parser.add_argument(
        "--record-prompts",
        nargs="?",
        const="logs/prompt_records",
        default=None,
        help="Enable prompt recording, optionally specify output directory (default: logs/prompt_records)",
    )
    args, _ = parser.parse_known_args()
    main(record_prompts=args.record_prompts)
