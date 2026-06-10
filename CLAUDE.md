# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

ASSEF (Adversarial System Security Evolution Framework) is an AI-driven security evaluation framework. Two core modes:

- **Mode A (Arena)**: Turn-based red-team vs blue-team adversarial loop. Red AI generates attacks, a constitution-driven judge rules on success, Blue AI produces minimal fixes, and a 3-color evaluator (red/yellow/green) scores each round.
- **Mode B (Benchmark)**: Concurrently evaluates multiple LLMs' ability to fix vulnerabilities across targets, producing a leaderboard with fix-success and pass rates.

## Commands

```bash
# Backend (conda 在 bash 终端不可用，直接使用 ASSEF 环境 Python)
conda activate ASSEF                                    # Python >= 3.13 required (仅 PowerShell/CMD 可用)
export PATH="D:/develop_tools/Anaconda3/envs/ASSEF:D:/develop_tools/Anaconda3/envs/ASSEF/Scripts:$PATH"  # bash 环境用这条
pip install -e .                                        # Editable install
python -m backend.assef.api                             # Start FastAPI on :8710
python -m backend.assef.api --record-prompts [dir]      # With prompt recording
python backend/assef_cli.py run [--target NAME] [--rounds N]  # CLI arena
python backend/assef_cli.py info                        # Show config summary
python backend/assef_cli.py history list|show|delete    # History management
pytest                                                  # Run all backend tests

# Frontend (start backend first, then:)
cd frontend && npm install && npm run dev               # Electron + React app
cd frontend && npm run build                            # Production build
cd frontend && npm run typecheck                        # TypeScript check
```

## Architecture

```text
Frontend (Electron + React + TypeScript + electron-vite + Tailwind + Zustand)
     │ HTTP REST + WebSocket
     ▼
Backend (FastAPI :8710)
  ├── Arena engine   → arena.py (round loop), benchmark.py (multi-model eval)
  ├── AI Agent layer → red_team.py (multi-strategy attack gen), blue_team.py (fix gen)
  ├── Judge layer    → constitution_agent.py (constitution→script), constitution_judge.py, judge.py
  ├── LLM client     → llm_client.py (ollama/openai/deepseek/anthropic/mock + streaming)
  ├── Sandbox        → process_sandbox.py (subprocess isolation + danger-pattern detection)
  ├── Core infra     → executor.py (background thread pool), progress.py (observer events)
  ├── History        → history/__init__.py (JSON persistence to repo-root history/)
  ├── Recorder       → recorder/__init__.py (JSONL prompt recording)
  └── Models         → config.py, target_spec.py, results.py, arena_result.py, etc.
```

## Key architectural patterns

- **Import style**: Package uses `from __future__ import annotations` throughout. Top-level `assef/__init__.py` re-exports all public classes — external code imports from `assef` (or `backend.assef` with `sys.path` adjustment for scripts).
- **CLI tool** (`backend/assef_cli.py`) and API server both use `sys.path.insert(0, ...)` to import `backend.assef.*` modules.
- **Streaming with phases**: `LLMClient.chat_stream_with_phase()` distinguishes `thinking` and `output` phases via an `on_phase` callback — used primarily for DeepSeek reasoning models.
- **WebSocket progress**: `ProgressDispatcher` (observer pattern) pushes `ProgressEvent`s to frontend via `/ws/task/{task_id}`. Arena and Benchmark each create their own dispatcher, stored in `_task_dispatchers`.
- **Background execution**: `BackgroundExecutor` singleton wraps `ThreadPoolExecutor` with pause/resume/cancel support via events. Both Arena and Benchmark tasks run through it.
- **Judge scripts**: `ConstitutionAgent` translates natural-language constitution rules into executable Python judge functions at runtime. The generated script is cached in `_script`. The actual execution runs through `Judge._execute_in_sandbox()` using subprocess with danger-pattern blocking.
- **Frontend state**: Single Zustand store (`useAppStore`) manages backend connection status, config, page routing, and history list. Arena-specific state lives in a separate `arenaSlice.ts`.

## Interaction preferences

- **Language**: 使用中文回复（代码、命令、专业术语除外）
- **Reference doc**: `AGENT_README.md` 包含详细的模块索引和最近变更记录，遇到架构问题时可查阅

## Important caveats

- **DeepSeek `reasoning_content`**: DeepSeek reasoning models return a `reasoning_content` field alongside `content`. The `is_reasoning_model` flag in backend config MUST be set to `true` for these models, otherwise thinking tokens leak into the response. See `llm_client.py` lines ~1006 and ~887.
- **PatchEvaluator removed** (2026-06-06): Patch evaluation logic was merged into `arena.py`; do not reference `patch_evaluator.py`.
- **Frontend dev requires backend**: The Electron app connects to `http://localhost:8710`. Start the backend first.
- **Config bootstrap**: If `config.json` is missing, code auto-copies from `config.default.json`.
- **Mock backend** is available for testing without real LLMs — set `"backend": "mock"` in a backend config entry.
