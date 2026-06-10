"""ASSEF API 服务入口点 —— 通过 uvicorn 启动 FastAPI 应用服务器

用法：
    python -m backend.assef.api [--record-prompts [输出目录]]

选项：
    --record-prompts: 启用提示词记录功能，可选指定输出目录（默认：logs/prompt_records）
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.assef.api.server import app
from backend.assef.recorder import get_prompt_recorder

if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="ASSEF API Server")
    parser.add_argument(
        "--record-prompts",
        nargs="?",
        const="logs/prompt_records",
        default=None,
        help="Enable prompt recording, optionally specify output directory (default: logs/prompt_records)",
    )
    args = parser.parse_args()

    if args.record_prompts:
        output_dir = args.record_prompts
        recorder = get_prompt_recorder(output_dir)
        app.state.prompt_recorder = recorder
        print(f"[recorder] Prompt recording enabled, output: {output_dir}")
    else:
        app.state.prompt_recorder = None

    uvicorn.run(app, host="0.0.0.0", port=8710)
