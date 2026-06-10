# AGENT_README v2.6

Last updated: 2026-06-10
Update reason: 新增ReportGenerator(ConstitutionAgent拆分); 全模块移除debug_logger依赖; LLM客户端类型安全加固(ChatCompletionChunk/cast); 前端shadcn/ui迁移+Arena组件重构+hooks拆分; CLAUDE.md初始化

## 📍 Quick Index

| 关键词 | 位置/摘要 | 最后验证 |
|---|---|---|
| 项目概述 | ASSEF: 对抗性系统安全自演进框架，AI驱动的红蓝对抗+多模型评测 | 2026-05-31 |
| 模式A-红蓝对抗 | `backend/assef/arena/arena.py` → Arena.run() 回合制攻击/防御/评估循环 | 2026-05-31 |
| 模式B-多模型评测 | `backend/assef/arena/benchmark.py` → BenchmarkRunner.run() LLM修复能力排行榜 | 2026-05-31 |
| LLM客户端 | `backend/assef/llm/llm_client.py` → LLMClient, 支持 ollama/openai/deepseek/anthropic/mock | 2026-05-31 |
| LLM流式调用 | `backend/assef/llm/llm_client.py` → LLMClient.chat_stream(on_token)/chat_stream_with_phase(on_phase,on_token) Ollama/OpenAI/DeepSeek/Mock | 2026-05-31 |
| DeepSeek reasoning | `backend/assef/llm/llm_client.py` → reasoning_content 字段独立存在, is_reasoning_model控制是否丢弃思考部分 | 2026-06-08 |
| is_reasoning_model | `config.json` 配置项, True=丢弃推理token(仅输出部分), False=思考混入回答, 必须正确设置! | 2026-06-08 |
| 宪法判官 | `backend/assef/judge/constitution_judge.py` → ConstitutionJudge, 动态生成判官脚本 | 2026-05-31 |
| 进度事件 | `backend/assef/core/progress.py` → ProgressEvent + ProgressDispatcher 观察者模式 | 2026-05-31 |
| 后台执行器 | `backend/assef/core/executor.py` → BackgroundExecutor 单例线程池, submit_task/pause/resume/cancel | 2026-05-31 |
| API服务 | `backend/assef/api/server.py` FastAPI :8710, routes: arena/benchmark/config/llm/task | 2026-05-31 |
| WebSocket进度 | `backend/assef/api/server.py` → /ws/task/{task_id} 实时ProgressEvent推送 | 2026-05-31 |
| Prompt录制 | `backend/assef/recorder/` → PromptRecorder, JSONL格式记录LLM调用链 | 2026-05-31 |
| 日志系统 | `backend/assef/logging_config.py` → ModuleFileHandler, 按模块写入 backend/logs/ | 2026-05-31 |
| 沙箱执行 | `backend/assef/sandbox/process_sandbox.py` → ProcessSandbox 子进程隔离执行 | 2026-05-31 |
| 补丁评估 | `backend/assef/arena/arena.py` → Arena.run() 内部 red/yellow/green 三色评估 (PatchEvaluator 已移除) | 2026-06-10 |
| 报告生成器 | `backend/assef/judge/report_generator.py` → ReportGenerator, 基于LLM生成竞技场分析报告 (从ConstitutionAgent拆分) | 2026-06-10 |
| 事件收集器 | `backend/assef/judge/event_collector.py` → EventCollector, 线程安全收集判官事件时间线 | 2026-06-10 |
| 前端框架 | Electron + React + TypeScript + electron-vite + shadcn/ui (Radix UI primitives), `frontend/` 目录 | 2026-06-10 |
| 前端Arena组件 | `frontend/.../components/arena/` → ArenaHeader / PreLaunch / Running / BottomPanel + columns/ (Red/Blue/Judge) + shared/ (AgentStream / DiffPanel / RoundCard 等) | 2026-06-10 |
| 前端UI组件 | `frontend/.../components/ui/` → button / select / tabs (shadcn/ui + Radix UI primitives + Tailwind) | 2026-06-10 |
| 配置文件 | `config.json` (用户) / `config.default.json` (默认模板) | 2026-05-31 |
| Python环境 | `D:\develop_tools\Anaconda3\envs\ASSEF` | 2026-05-31 |
| 测试框架 | pytest, `backend/tests/` 目录 | 2026-05-31 |
| 靶机示例 | `targets/doc_query.py` — IDOR漏洞文档查询服务 | 2026-05-31 |
| CLI命令工具 | `backend/assef_cli.py` → run/info/history 子命令, 终端精简输出 | 2026-06-06 |
| 历史记录持久化 | `backend/assef/history/__init__.py` → save/list/get/delete, JSON→history/ | 2026-06-06 |
| 历史记录API | `backend/assef/api/routes_history.py` → GET /api/history/list|detail, DELETE | 2026-06-06 |
| 前端HistoryPage | `frontend/src/renderer/pages/HistoryPage.tsx` → 分页浏览+展开详情+删除 | 2026-06-06 |
| 前端Hooks | `frontend/src/renderer/hooks/` → useArenaControl|useArenaData|useArenaWebSocket | 2026-06-06 |

## 🗂️ Directory Structure Summary

```
ASSEF/
├── backend/                      # 后端源码 (Python)
│   ├── assef/                    # 主源码包
│   │   ├── __init__.py           # 顶层导出所有公开API类
│   │   ├── __main__.py           # python -m backend.assef.api 入口
│   │   ├── logging_config.py     # ModuleFileHandler, 模块化日志→backend/logs/
│   │   ├── agents/               # AI Agent层
│   │   │   ├── red_team.py       # 红队: 多策略攻击输入生成器
│   │   │   └── blue_team.py      # 蓝队: 最小化安全修复代码生成器
│   │   ├── arena/                # 竞技引擎层
│   │   │   ├── arena.py          # Arena: 回合制红蓝对抗引擎 (重构, 移除PatchEvaluator依赖)
│   │   │   └── benchmark.py      # BenchmarkRunner: 多模型评测排行榜
│   │   ├── core/                 # 核心基础设施
│   │   │   ├── executor.py       # BackgroundExecutor 单例线程池
│   │   │   └── progress.py       # ProgressEvent/ProgressDispatcher 事件系统
│   │   ├── history/              # 历史记录持久化层
│   │   │   └── __init__.py       # save_arena_result|benchmark + list|get|delete, JSON→history/
│   │   ├── judge/                # 裁判层
│   │   │   ├── judge.py          # Judge: 沙箱执行+测试判定
│   │   │   ├── constitution_agent.py # ConstitutionAgent: 宪法→判官脚本翻译
│   │   │   ├── constitution_judge.py # ConstitutionJudge: 宪法驱动判定集成+事件收集委托
│   │   │   ├── event_collector.py # EventCollector: 线程安全判官事件时间线收集
│   │   │   └── report_generator.py # ReportGenerator: 基于LLM的竞技场分析报告生成
│   │   ├── llm/                  # LLM接入层
│   │   │   └── llm_client.py     # LLMClient: OpenAI兼容API + chat_stream流式
│   │   ├── models/               # 数据模型层
│   │   │   ├── config.py         # Config: LLM后端/游戏规则/宪法/靶机/沙箱配置
│   │   │   ├── target_spec.py    # TargetSpec/NormalTest/SuccessCriteria
│   │   │   ├── results.py        # SandboxResult/VerdictDetail/VerdictReport
│   │   │   ├── arena_result.py   # RoundRecord/ArenaResult
│   │   │   ├── benchmark_result.py # ModelScore/BenchmarkResult
│   │   │   ├── constitution.py   # Constitution 裁判宪法
│   │   │   ├── game_rules.py     # GameRules 红蓝对抗参数
│   │   │   └── recorder.py       # RecordEntry/Metrics/CallerType (dataclass)
│   │   ├── recorder/             # Prompt录制层
│   │   │   └── __init__.py       # PromptRecorder: JSONL写入 + useful回填 + metrics计算
│   │   ├── sandbox/              # 沙箱执行层
│   │   │   └── process_sandbox.py# ProcessSandbox: 子进程隔离+危险模式检测
│   │   └── api/                  # FastAPI服务层
│   │       ├── server.py         # FastAPI app, CORS, WebSocket, uvicorn :8710
│   │       ├── __main__.py       # python -m backend.assef.api 启动入口
│   │       ├── routes_arena.py   # POST /api/arena/start 启动红蓝对抗任务
│   │       ├── routes_benchmark.py # POST /api/benchmark/start 多模型评测
│   │       ├── routes_config.py  # GET/PUT /api/config 配置读写
│   │       ├── routes_history.py # GET /api/history/list|detail, DELETE 历史记录
│   │       ├── routes_llm.py     # POST /api/llm/test LLM连接测试
│   │       └── routes_task.py    # POST /api/task/{id}/pause|resume|cancel
│   ├── tests/                    # pytest测试 (每个源模块对应一个test文件)
│   │   └── conftest.py           # sys.path配置
│   ├── examples/                 # 使用示例脚本
│   └── assef_cli.py              # CLI工具: run(竞技场)|info(配置)|history list|show|delete
├── frontend/                     # 前端 (Electron + React + TypeScript)
│   ├── src/
│   │   ├── main/index.ts         # Electron主进程
│   │   ├── preload/index.ts      # 预加载脚本
│   │   └── renderer/             # React渲染进程
│   │       ├── api/client.ts     # HTTP客户端 (arena/benchmark/config/llm/task/history)
│   │       ├── api/websocket.ts  # WebSocket管理器 TaskWebSocketManager
│   │       ├── components/       # Sidebar.tsx, StatusBar.tsx, arena/ (ArenaHeader|Running|PreLaunch|BottomPanel|columns/), ui/ (button|select|tabs — shadcn/ui)
│   │       ├── hooks/            # useArenaControl|useArenaData|useArenaWebSocket
│   │       ├── lib/utils.ts      # shadcn/ui utility (cn() classname merge)
│   │       ├── pages/            # ArenaPage, ConfigPage, LeaderboardPage, HistoryPage
│   │       ├── store/            # index.ts (Zustand) + arenaSlice.ts
│   │       ├── types/index.ts    # TypeScript类型定义
│   │       └── App.tsx           # React根组件 + 路由
│   ├── electron-builder.yml      # Electron打包配置
│   └── package.json              # electron-vite, React, Tailwind, Recharts, Radix UI
├── targets/                      # 靶机代码示例
├── history/                      # 运行结果持久化目录 (arena_*/benchmark_* JSON)
├── config.json                   # 用户配置 (不存在时从default复制)
├── config.default.json           # 默认配置模板
└── pyproject.toml                # 项目元数据, [tool.setuptools.packages.find] where=["backend"]
```

## 🔑 Key Components

### LLMClient (`backend/assef/llm/llm_client.py`)
- 职责: OpenAI兼容API的统一LLM调用客户端
- 支持后端: ollama, openai, deepseek, anthropic, mock
- 同步调用: `chat(messages, **kwargs)` → str
- 流式调用: `chat_stream(messages, on_token, **kwargs)` → str (含相位版`chat_stream_with_phase`)
- 录制回调: `on_call_record` 参数注入, 将调用详情传给PromptRecorder
- 关键类: `LLMClient`, `LLMErrorCode`, `classify_error_code()`, `LLMConnectionError`
- 依赖: openai, requests

#### DeepSeek API `reasoning_content` 处理详解
- **背景**: DeepSeek 推理模型（如 deepseek-v4-flash）的 API 响应比标准 OpenAI 多出 `reasoning_content` 字段，包含模型思考过程
- **非流式** `_chat_openai_compat()` (`backend/assef/llm/llm_client.py` 第887行):
  - `response.choices[0].message` 同时有 `.content`（回答）和 `.reasoning_content`（思考过程）
  - 代码走 `msg.content or ""`，**不会混入 reasoning_content**
  - 若 `msg.content` 为空且 `is_reasoning_model=True` → 记录警告但**不**回退到 reasoning_content（思考内容对代码生成无意义）
  - 若 `msg.content` 为空且 `is_reasoning_model=False` → 回退到 `reasoning_content` 作为响应（此时思考内容被当作输出）
- **流式无相位** `_chat_openai_compat_stream()` (第962行):
  - 第1006行: `token = delta.content or (getattr(delta, 'reasoning_content', '') if not self._is_reasoning_model else '') or ''`
  - `is_reasoning_model=True`: 推理token被**静默丢弃**（重要：不然会混入回答），最终返回仅含输出部分
  - `is_reasoning_model=False`: 推理token被当作普通内容token，**思考过程和回答会混在一起**
- **流式带相位** `_chat_openai_compat_stream_with_phase()` (第1033行):
  - 通过 `on_phase("thinking")` / `on_phase("output")` 区分两阶段
  - 前端可据此展示"正在思考…"等UI状态
  - 最终返回 `content_only`（已剔除思考部分的纯净回答）
- **测试验证** (2026-06-08，`backend/test_deepseek_api.py`):
  - 非流式: `msg.content`="你好。"(3字符) / `reasoning_content`="我们要求用中文说你好..."(38字符) — 两者独立共存
  - 流式无相位 `is_reasoning_model=True`: 仅收集到2个输出token（思考被正确跳过）
  - 流式无相位 `is_reasoning_model=False`: 收集到51个token（思考+回答全部混入）
  - 流式带相位: thinking→output 两阶段切换正常，返回仅含输出部分
- **关键结论**: `is_reasoning_model` 配置必须正确设置！设为 `False` 会导致思考内容泄露到代码生成结果中

### Arena (`backend/assef/arena/arena.py`)
- 职责: 模式A核心——回合制红蓝对抗循环
- 流程: RedTeam攻击 → ConstitutionJudge判定 → 成功→BlueTeam防御 → PatchEvaluator三色评估 → 下一轮
- 支持: cancel_event/pause_event 中途控制
- 关键方法: `Arena.run(target, max_rounds, on_progress, cancel_event, pause_event)` → `ArenaResult`
- 依赖: ConstitutionJudge, RedTeamAgent, BlueTeamAgent, PatchEvaluator, Judge(feedback)

### ConstitutionJudge (`backend/assef/judge/constitution_judge.py`)
- 职责: 基于宪法动态生成判官脚本，统一裁判攻击/防御结果
- 关键方法: `judge_attack(code, attack_inputs)` → VerdictReport, `judge_defense(...)` , `generate_summary_report(...)` → str
- 内部委托: ConstitutionAgent (生成脚本), Judge (执行脚本), ReportGenerator (分析报告)
- 特性: 判官脚本懒生成(首次调用时生成)，缓存在 `_script` 字段

### ConstitutionAgent (`backend/assef/judge/constitution_agent.py`)
- 职责: 将Constitution规则文本翻译为可执行Python判官函数 `judge(inputs) → dict`
- 输出格式: `{"attack_success": bool, "results": [...]}`
- 脚本限制: 仅内置模块, 无副作用, 无import

### Judge (`backend/assef/judge/judge.py`)
- 职责: 沙箱执行代码+逐条比对测试结果
- 关键方法: `judge_normal(target, code)` → VerdictReport, `judge_attack(code, attack_inputs)` → VerdictReport
- 内部: `_execute_in_sandbox()` 临时文件+subprocess执行

### API Server (`backend/assef/api/server.py`)
- 职责: FastAPI服务, 为Electron前端提供REST API + WebSocket
- 端口: 8710, 启动: `python -m backend.assef.api` 或 `assef-server`
- 路由: /api/arena (红蓝对抗), /api/benchmark (评测), /api/config (配置), /api/llm (LLM测试), /api/task (任务控制)
- WebSocket: `/ws/task/{task_id}` 实时推送ProgressEvent (step_start/step_done/llm_token/score_update/task_done)
- 录制: `--record-prompts [dir]` 参数启用Prompt录制到JSONL

### PromptRecorder (`backend/assef/recorder/__init__.py`)
- 职责: 记录所有LLM调用的messages/response/duration到JSONL文件
- 输出: `logs/prompt_records/prompt_records_{date}.jsonl`
- 关键方法: `record(entry)` 追加写入, `update_useful(call_id, bool)` 回填useful标记, `compute_metrics(response, caller)` 计算格式/意图指标
- 数据模型: `RecordEntry` (timestamp/caller/backend/model/messages/response/duration_ms/metrics)
- 调用链: Arena每条attack/fix调用LLM时通过 `on_call_record` 回调触发

### LoggingConfig (`backend/assef/logging_config.py`)
- 职责: 模块化日志系统, ModuleFileHandler按模块写入不同文件
- 输出: `backend/logs/` 目录, 每个模块一个log文件 (arena/arena.log, llm/llm_client.log, etc.)
- 控制台: stderr输出, 默认WARNING级别, 设置 `ASSEF_DEBUG=1` 环境变量启用DEBUG
- 获取: `get_logger("api.arena")` → `logging.Logger`

### RedTeamAgent (`backend/assef/agents/red_team.py`)
- 职责: 多策略攻击输入生成 (illegal_value/boundary/injection/logic_bypass/encoding_confusion)
- 关键方法: `generate_attack(target, history, on_progress)` → list[dict] 攻击计划
- 策略: 基于攻击策略树的变异，历史感知(blood bank, defense count)

### BlueTeamAgent (`backend/assef/agents/blue_team.py`)
- 职责: 针对已知漏洞生成最小化修复代码
- 关键方法: `generate_fix(target, successful_attacks, blood_bank)` → str 修复代码
- 反馈循环: `generate_fix_with_feedback()` 基于测试失败自我迭代修复

### PatchEvaluator — 已移除 (2026-06-06)
- 补丁评估逻辑已合并到 `arena.py` Arena.run() 内部

### ReportGenerator (`backend/assef/judge/report_generator.py`)
- 职责: 基于竞技场对抗结果和事件时间线，通过 LLM 生成结构化的中文分析报告
- 关键方法: `generate_summary_report(target_name, constitution_text, arena_result_dict, events)` → str
- 从 `ConstitutionAgent` 拆分而来（ConstitutionAgent 专注于判官脚本生成）
- 依赖: LLMClient

### EventCollector (`backend/assef/judge/event_collector.py`)
- 职责: 线程安全收集判官系统运行过程中的各类事件（攻击生成/沙箱执行/判定/防御/评分/回合结束）
- 事件类型: `EventType` 枚举 — ATTACK_GENERATED, SANDBOX_EXECUTED, ATTACK_JUDGED, DEFENSE_GENERATED, DEFENSE_EVALUATED, SCORE_UPDATED, ROUND_ENDED, ARENA_FINISHED
- 关键方法: `collect(event_type, role, summary, **kwargs)` 追加事件, `get_events()` 返回时间线快照

### ProcessSandbox (`backend/assef/sandbox/process_sandbox.py`)
- 职责: 子进程隔离执行靶机代码，危险模式检测+超时控制
- 关键方法: `execute(code, input_data, timeout)` → SandboxResult

### ProgressDispatcher (`backend/assef/core/progress.py`)
- 职责: 观察者模式事件广播——step_start/step_done/llm_token/judge_test_result/info/error/score_update/task_done
- 用途: 为API WebSocket和前端UI提供实时进度数据流

### BackgroundExecutor (`backend/assef/core/executor.py`)
- 职责: 单例ThreadPoolExecutor, submit_task/pause_task/resume_task/cancel_task/get_task_status
- 特性: 支持cancel_event + pause_event, 任务状态字典 `_tasks`

### CLI Tool (`backend/assef_cli.py`)
- 职责: 命令行红蓝对抗工具, 终端精简输出 + 详细日志记录到 backend/logs/
- 子命令: `run [--target NAME] [--rounds N]` 启动竞技场, `info` 展示配置, `history list|show|delete` 历史记录
- 依赖: Arena, ConstitutionJudge, LLMClient, history 模块

### History Module (`backend/assef/history/__init__.py`)
- 职责: ArenaResult/BenchmarkResult 持久化为 JSON 文件到项目根 `history/` 目录
- 命名规则: `arena_{target}_{YYYYMMDD_HHMMSS}.json` / `benchmark_{YYYYMMDD_HHMMSS}.json`
- API: `save_arena_result()` / `save_benchmark_result()` / `list_records()` (分页) / `get_detail()` / `delete_record()`

### History API (`backend/assef/api/routes_history.py`)
- 职责: 历史记录的 REST API 接口, 前缀 `/api/history`
- 端点: `GET /api/history/list` (分页+类型筛选), `GET /api/history/detail/{id}`, `DELETE /api/history/{id}`

### Frontend (`frontend/`)
- 技术栈: Electron + React 18 + TypeScript + electron-vite + Tailwind CSS + Zustand + Recharts + shadcn/ui (Radix UI primitives)
- 页面: ArenaPage (红蓝对抗实时监控), ConfigPage (LLM/靶机配置), HistoryPage (历史浏览), LeaderboardPage (多模型评测矩阵)
- API通信: `client.ts` HTTP调用后端 :8710, `websocket.ts` WebSocket实时精度
- 启动: `cd frontend && npm run dev`
- Arena 架构: PreLaunch (靶机/轮次配置) → Running (左右布局: Red/Blue/Judge 三列 + BottomPanel/DefenseChart) + 实时 WebSocket → 完成
- 数据流: `useArenaControl` (启动/暂停/取消) → `useArenaWebSocket` (WS 监听) → `arenaSlice` (Zustand slice) → `useArenaData` (computed) → 组件渲染
- shadcn/ui: `components/ui/` 提供 button / select / tabs，基于 Radix UI primitives，通过 `lib/utils.ts` 的 `cn()` 合并 Tailwind 类名

## 📝 Recent Changes

| 日期 | 变更ID | 摘要 | 影响范围 |
|---|---|---|---|
| 2026-06-10 | cleanup-types | ReportGenerator 从 ConstitutionAgent 拆分为独立模块; 全模块移除 debug_logger/agent_log 依赖; `constitution_judge.py` 新增 `generate_summary_report()` 委托; 蓝队 agent_log 清理; LLM 客户端类型安全加固 (ChatCompletionChunk 类型检查 / cast / assert / 错误码兜底); executor 类型修复 (cast / getattr); `route_benchmark.py` 和 `route_arena.py` 小幅调整 | judge/, agents/, llm/, core/, api/routes_* |
| 2026-06-08 | frontend-shadcn | 前端 shadcn/ui 迁移: 新增 `components/ui/` (button/select/tabs), `lib/utils.ts`, 移除 Ant Design 依赖(从 package.json 清除); Arena 组件重构: ArenaHeader / PreLaunch / Running / BottomPanel + 三列 (Red/Blue/Judge) + shared (AgentStream / DiffPanel / RoundCard 等); hooks 拆分: useArenaControl / useArenaData / useArenaWebSocket; arenaSlice Zustand store; CLAUDE.md 初始化 | frontend/components, hooks, store, pages, types, package.json, tailwind.config.js |
| 2026-06-06 | history-cli | 新增 assef_cli.py CLI工具 (run/info/history); history/ 历史记录持久化模块 (JSON); routes_history.py API; 前端 HistoryPage 分页浏览; 前端 hooks 拆分 (useArenaControl/Data/WebSocket); arena/agents/llm 大幅重构; patch_evaluator.py 移除合并入 arena.py | CLI, history/, api/routes_history, frontend/pages/hooks/store, arena, agents, llm |
| 2026-05-31 | arch-migration | Streamlit UI移除, 替换为 FastAPI(:8710) + Electron前端; 新增 recorder(Prompt录制JSONL) + logging_config(模块化日志) + WebSocket进度推送; 路由: routes_arena/benchmark/config/llm/task | 全部架构层: UI/API/recorder/logging |
| 2026-05-30 | restructure-paths | 项目结构重组: src/ → backend/, tests/ → backend/tests/, examples/ → backend/examples/; pyproject.toml 增加 where=["backend"]; __main__.py 改用 sys.path + from backend.assef... 导入 | 全部路径引用, pyproject.toml, __main__.py |
| 2026-05-29 | refactor-async | LLMClient新增chat_stream()流式调用; 全部Agent/Judge/Arena支持on_progress回调; arena_page改为BackgroundExecutor+500ms轮询; leaderboard_page改为ThreadPoolExecutor并发 | llm/, agents/, judge/, arena/, core/, ui/ |
| 2026-05-29 | init | 项目初始化，完整分层架构 | 全部模块 |

## ⚠️ Known Issues / Notes

| 描述 | 发现日期 | 状态 |
|---|---|---|
| Python要求 ≥3.13，使用 `D:\develop_tools\Anaconda3\envs\ASSEF` 环境 | 2026-05-29 | 注意 |
| `config.json` 不存在时从 `config.default.json` 自动复制 | 2026-05-29 | 设计如此 |
| Mock后端用于无LLM环境下的测试验证 | 2026-05-29 | 设计如此 |
| PatchEvaluator (`backend/assef/arena/patch_evaluator.py`) 已移除，补丁评估逻辑合并入 arena.py | 2026-06-06 | 注意 |
| `history/` 目录存储 arena/benchmark 运行结果 JSON，切勿手动编辑 | 2026-06-06 | 注意 |
| DeepSeek `reasoning_content` 会混入流式输出，必须设 `is_reasoning_model=True` 才能正确过滤思考部分 | 2026-06-08 | 重要 |
| 若 `is_reasoning_model=False` 且 `msg.content` 为空，非流式会回退到 `reasoning_content`（思考内容作为输出） | 2026-06-08 | 注意 |
| Arena和Benchmark均通过BackgroundExecutor异步执行 | 2026-05-31 | 设计如此 |
| FastAPI服务端口8710, 通过 `python -m backend.assef.api` 或 `assef-server` 启动 | 2026-05-31 | 注意 |
| Prompt录制通过 `--record-prompts` 参数启用, 输出到JSONL文件 | 2026-05-31 | 设计如此 |
| 前端先启动后端(8710), 再 `cd frontend && npm run dev` 启动Electron | 2026-05-31 | 注意 |
| 前端组件使用 shadcn/ui + Radix UI primitives (button/select/tabs)，不再使用 Ant Design | 2026-06-10 | 设计如此 |
| `Arena._judge.generate_summary_report()` 已替代 `Arena._judge._agent.generate_summary_report()`（报告生成从 ConstitutionAgent 移至 ConstitutionJudge 委托） | 2026-06-10 | 注意 |
| `event_collector.py` 和 `report_generator.py` 为新增 judge 模块文件，测试文件在 `backend/tests/test_event_collector.py` | 2026-06-10 | 新增 |
