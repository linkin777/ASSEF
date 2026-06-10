# ASSEF — 对抗性系统安全自演进框架

**Adversarial System Security Evolution Framework**

ASSEF 是一个 AI 驱动的安全评测框架，核心能力是**自动化红蓝对抗**与**多模型安全修复能力评测**。它让 LLM 扮演红队（攻击方）和蓝队（防御方），在回合制对抗中自动发现并修复安全漏洞，同时提供排行榜来评估不同模型的修复能力。

---

## 核心特性

- **模式 A — 红蓝对抗（Arena）**：红队 AI 使用多策略生成攻击输入（边界值、注入、逻辑绕过、编码混淆等），宪法判官判定攻击是否成功；成功后蓝队 AI 自动生成修复代码，经三维评估后进入下一轮。形成「攻击 → 判定 → 修复 → 评估」的完整闭环。
- **模式 B — 多模型排行榜（Benchmark）**：并发评测多个 LLM 对同一批靶机的修复能力，生成修复成功率、通过率等指标排行榜。
- **宪法驱动裁判**：用自然语言编写裁判规则（宪法），系统自动将其翻译为可执行的判官脚本，确保判定一致且可解释。
- **沙箱安全执行**：靶机代码在子进程隔离环境中执行，内置危险模式检测和超时控制，防止恶意代码影响宿主机。
- **双端支持**：Electron 桌面应用（React + TypeScript）与 FastAPI REST API。

---

## 快速开始

### 环境要求

- Python >= 3.13
- Conda 虚拟环境（推荐）

### 安装步骤

```bash
# 1. 激活 Conda 环境
conda activate ASSEF

# 2. 安装项目依赖（以可编辑模式安装，方便开发）
pip install -e .

# 3. 生成用户配置文件
copy config.default.json config.json

# 4. 编辑 config.json，配置 LLM 后端
```

### 配置文件

`config.json` 是主要配置文件，各模块说明：

```json
{
  "llm_backends": [
    {
      "backend": "ollama",        // 后端类型: ollama / openai / deepseek / anthropic / mock
      "model": "qwen2.5:7b",
      "api_key": "",
      "base_url": "http://localhost:11434/api/chat",
      "max_retries": 3,
      "temperature": 0.7,
      "max_tokens": 2048
    }
  ],
  "game_rules": {
    "max_blue_retries": 2,        // 蓝队最大重试次数
    "max_arena_rounds": 10,       // 红蓝对抗最大轮数
    "red_strategy_mutation_threshold": 3  // 红队策略变异阈值
  },
  "constitution": {
    "preamble": "...",             // 裁判宪法规则（自然语言）
    "attack_success_criteria": "...",
    "fix_success_criteria": "...",
    "scoring_rules": "...",
    "constraints": "..."
  },
  "sandbox": {
    "timeout": 30.0,               // 沙箱执行超时（秒）
    "dangerous_patterns": [...]    // 危险代码模式列表
  },
  "targets": []                    // 靶机配置列表
}
```

> **Mock 后端**：无需真实 LLM，内置模拟响应，适合快速验证框架流程。

---

## 使用方式

### 启动 Electron 桌面应用（推荐）

```bash
cd frontend
npm install
npm run dev
```

### 启动 FastAPI 服务

```bash
python -m backend.assef.api
```

提供 REST API，适用于集成到其他系统或自动化脚本调用。

### 运行示例脚本

```bash
# 端到端红蓝对抗演示
python backend/examples/end_to_end_demo.py

# 竞技场模式演示
python backend/examples/arena_demo.py

# 多模型评测演示
python backend/examples/benchmark_demo.py

# 配置文件使用示例
python backend/examples/config_example.py
```

---

## 架构概览

```
┌──────────────────────────────────────────────────────┐
│               Frontend (Electron + React)             │
│          WebSocket / REST API ←→ Backend              │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│               Backend (FastAPI)                       │
│  Arena 引擎层  │  AI Agent 层  │  Judge 裁判层      │
│  LLM 接入层    │  Sandbox 沙箱层                      │
└──────────────────────────────────────────────────────┘

```

后端内部分层：

```
┌──────────────────────────────────────────────────────┐
│                  Arena 引擎层                         │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │Arena(对抗循环)│  │BenchmarkRunner│  │PatchEvaluator│ │
│  │             │  │  (多模型评测)  │  │ (三维评估)   │  │
│  └──────┬──────┘  └──────────────┘  └─────────────┘  │
└─────────┼────────────────────────────────────────────┘
          │
┌─────────▼────────────────────────────────────────────┐
│                   AI Agent 层                         │
│  ┌──────────────────┐    ┌──────────────────┐         │
│  │ RedTeamAgent     │    │ BlueTeamAgent    │         │
│  │ 多策略攻击生成器   │    │ 最小化修复代码生成器│         │
│  └──────────────────┘    └──────────────────┘         │
└─────────┬──────────────────────────┬──────────────────┘
          │                          │
┌─────────▼──────────────────────────▼──────────────────┐
│                    Judge 裁判层                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │Constitution  │  │Constitution  │  │ Judge        │ │
│  │Agent         │  │Judge         │  │ 沙箱执行+判定 │ │
│  │宪法→脚本翻译   │  │宪法驱动判定集成 │  │             │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────┬─────────────────────────────────────────────┘
          │
┌─────────▼────────────────────────────────────────────┐
│                    LLM 接入层                         │
│  ┌────────────────────────────────────────────────┐   │
│  │ LLMClient (ollama / openai / deepseek /        │   │
│  │           anthropic / mock)                    │   │
│  │ 同步调用 + 流式调用 + 错误分类 + 重试策略       │   │
│  └────────────────────────────────────────────────┘   │
└─────────┬─────────────────────────────────────────────┘
          │
┌─────────▼────────────────────────────────────────────┐
│                  Sandbox 沙箱层                       │
│  ┌────────────────────────────────────────────────┐   │
│  │ ProcessSandbox                                 │   │
│  │ 子进程隔离 + 危险模式检测 + 超时控制            │   │
│  └────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

### 数据流（红蓝对抗模式）

```
  红队生成攻击 ──► 宪法判官判定攻击 ──► 成功?
                                         │
                                       Yes
                                         │
                                         ▼
                                    蓝队生成修复
                                         │
                                         ▼
                              PatchEvaluator 三维评估
                              ├─ 红：历史攻击是否被拦截
                              ├─ 黄：正常功能是否保持
                              └─ 绿：代码变更是否最小化
                                         │
                                         ▼
                                    进入下一轮
```

---

## 项目结构

```
ASSEF/
├── backend/                        # Python 后端
│   ├── assef/                      # 主源码包
│   │   ├── agents/                 # AI Agent 层
│   │   │   ├── red_team.py         #   红队：多策略攻击生成器
│   │   │   └── blue_team.py        #   蓝队：修复代码生成器
│   │   ├── arena/                  # 竞技引擎层
│   │   │   ├── arena.py            #   回合制红蓝对抗引擎
│   │   │   ├── benchmark.py        #   多模型评测排行榜
│   │   │   └── patch_evaluator.py  #   三维补丁评估
│   │   ├── core/                   # 核心基础设施
│   │   │   ├── executor.py         #   后台线程池（异步任务管理）
│   │   │   └── progress.py         #   进度事件系统（观察者模式）
│   │   ├── judge/                  # 裁判层
│   │   │   ├── judge.py            #   沙箱执行 + 测试判定
│   │   │   ├── constitution_agent.py  # 宪法 → 判官脚本翻译
│   │   │   └── constitution_judge.py  # 宪法驱动判定集成
│   │   ├── llm/                    # LLM 接入层
│   │   │   └── llm_client.py       #   统一 LLM 客户端
│   │   ├── models/                 # 数据模型层
│   │   │   ├── config.py           #   配置模型
│   │   │   ├── target_spec.py      #   靶机规格
│   │   │   ├── results.py          #   沙箱/判定结果
│   │   │   ├── arena_result.py     #   对抗结果
│   │   │   ├── benchmark_result.py #   评测结果
│   │   │   ├── constitution.py     #   宪法模型
│   │   │   └── game_rules.py       #   游戏规则
│   │   ├── sandbox/                # 沙箱执行层
│   │   │   └── process_sandbox.py  #   子进程隔离执行
│   │   └── api/                    # FastAPI 服务层
│   │       └── server.py           #   REST API 服务
│   ├── tests/                      # pytest 测试（每个模块对应一个测试文件）
│   │   └── conftest.py
│   └── examples/                   # 使用示例脚本
├── frontend/                       # Electron + React + TypeScript 桌面应用
│   └── src/
│       ├── main/                   # Electron 主进程
│       ├── preload/                # 预加载脚本
│       └── renderer/               # React 渲染进程
│           ├── pages/              # 页面组件
│           ├── components/         # 通用组件
│           ├── api/                # 后端 API 客户端
│           └── store/              # 状态管理
├── targets/                        # 靶机代码示例
│   └── doc_query.py                #   IDOR 漏洞文档查询服务
├── config.json                     # 用户配置（不存在时从 default 复制）
├── config.default.json             # 默认配置模板
├── pyproject.toml                  # 项目元数据
└── AGENT_README.md                 # AI Agent 知识库（供 AI 编码助手使用）
```

---

## 靶机示例

项目内置了一个演示靶机 `targets/doc_query.py`，是一个存在 **IDOR（不安全的直接对象引用）** 漏洞的文档查询服务：

- 公开文档（`public_001`, `public_002`）可被任意用户查询
- 内部文档（`internal_001`, `internal_002`）包含敏感信息（数据库密码、部署密钥）
- 漏洞点：未校验用户是否有权限访问内部级别文档

你可以基于此模板创建新的靶机，然后在 `config.json` 的 `targets` 数组中注册。

---

## 开发指南

### 运行测试

```bash
pytest
```

测试文件位于 `backend/tests/`，每个模块有对应的独立测试文件。

### 添加新靶机

1. 在 `targets/` 目录下创建 Python 文件（参考 `doc_query.py`）
2. 实现靶机逻辑，包含已知漏洞
3. 在 `config.json` 的 `targets` 数组中添加配置
4. 定义正常测试用例和攻击成功判定条件

### 添加新的 LLM 后端

在 `config.json` 的 `llm_backends` 数组中添加配置对象：

```json
{
  "backend": "openai",
  "model": "gpt-4",
  "api_key": "sk-xxx",
  "base_url": "https://api.openai.com/v1",
  "max_retries": 3,
  "temperature": 0.7,
  "max_tokens": 2048
}
```

目前支持的后端类型：`ollama`、`openai`、`deepseek`、`anthropic`、`mock`

---

## 技术栈

| 模块 | 技术 |
|---|---|
| 后端语言 | Python 3.13+ |
| 后端框架 | FastAPI + Uvicorn |
| 桌面应用 | Electron + React + TypeScript + Vite |
| LLM 客户端 | OpenAI SDK、requests |
| 沙箱 | subprocess 子进程隔离 |
| 测试 | pytest |
| 数据模型 | Pydantic v2 |

---

## 许可证

本项目基于 MIT 许可证开源。
