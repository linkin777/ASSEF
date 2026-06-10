# ASSEF — 让 AI 自己攻防，自动发现并修复安全漏洞

**Adversarial System Security Evolution Framework**

ASSEF 是一个 AI 驱动的安全评测框架。它的核心思路很简单：**让一个 AI 扮演黑客，另一个 AI 扮演防御者，在自动化的回合制对抗中不断发现漏洞并修复**。同时，它还能横向对比多个 AI 模型的安全修复能力，生成排行榜。

---

## 它解决什么问题？

传统的安全测试依赖人工渗透和手动修复，效率低、覆盖面窄。ASSEF 将这个过程自动化：

- **持续攻击**：AI 红队不断尝试各种攻击策略，不会遗漏边界情况
- **即时修复**：发现漏洞后，AI 蓝队立即生成修复代码
- **客观评判**：由宪法（自然语言规则）驱动的判官确保判定标准一致
- **模型选型**：想知道哪个 AI 模型修漏洞最靠谱？Benchmark 模式给你答案

---

## 两种工作模式

### 模式 A · 红蓝对抗

就像一个永不疲倦的安全演习：

```
红队发起攻击 → 判官裁定是否成功 → 蓝队修复漏洞 → 评估修复质量 → 下一轮
```

每一轮自动循环，直到代码足够安全或达到设定的轮次上限。修复质量从三个维度评估：

- 🔴 历史攻击是否被成功拦截
- 🟡 正常功能是否完好无损
- 🟢 代码变更是否最小化（只改该改的）

### 模式 B · 多模型排行榜

同一个漏洞，不同 AI 模型来修，谁更靠谱？Benchmark 模式并发评测多个 LLM，输出修复成功率和通过率排行榜。

---

## 快速开始

**前置条件**：Python ≥ 3.13 + Conda（推荐）

```bash
# 1. 激活环境
conda activate ASSEF

# 2. 安装
pip install -e .

# 3. 创建配置文件
copy config.default.json config.json

# 4. 编辑 config.json，至少配置一个 LLM 后端即可运行
```

> 💡 **想先试试？** 将后端设为 `"mock"` 即可在不接入任何 LLM 的情况下跑通整个流程。

### 启动应用

```bash
# 桌面应用（Electron，更直观）
cd frontend && npm install && npm run dev

# 或者只启动 API 服务（适合脚本调用）
python -m backend.assef.api
```

### 运行示例

```bash
python backend/examples/end_to_end_demo.py    # 完整红蓝对抗演示
python backend/examples/arena_demo.py         # 竞技场模式
python backend/examples/benchmark_demo.py     # 多模型评测
```

---

## 整体架构

ASSEF 由五个核心层组成，各司其职：

| 层级 | 职责 | 一句话描述 |
| --- | --- | --- |
| **Arena 引擎** | 指挥中心 | 控制红蓝对抗的回合节奏，调度各方行动 |
| **AI Agent** | 攻防大脑 | 红队生成攻击策略，蓝队生成修复代码 |
| **Judge 裁判** | 公正评判 | 根据宪法规则裁定攻击是否成功、修复是否有效 |
| **LLM 接入** | 模型适配 | 统一对接 OpenAI、DeepSeek、Anthropic、Ollama 等多种后端 |
| **Sandbox 沙箱** | 安全隔离 | 在子进程中执行靶机代码，防止恶意代码逃逸 |

**前后端关系**：

- 后端：FastAPI (Python)，负责所有 AI 逻辑和沙箱执行
- 前端：Electron + React (TypeScript)，通过 WebSocket 实时展示对抗过程

---

## 内置靶机

项目自带一个演示靶机 `targets/doc_query.py` — 一个存在 **IDOR 漏洞**（不安全直接对象引用）的文档查询服务。内部文档含敏感信息，却没有权限校验，是典型的安全缺陷示例。

添加新靶机只需在 `targets/` 下创建 Python 文件并在 `config.json` 中注册即可。

---

## 目录一览

```
ASSEF/
├── backend/                  # Python 后端
│   ├── assef/                #   主源码
│   │   ├── agents/           #   AI 红队 & 蓝队
│   │   ├── arena/            #   回合对抗 & 多模型评测引擎
│   │   ├── core/             #   任务调度 & 进度系统
│   │   ├── judge/            #   宪法驱动裁判
│   │   ├── llm/              #   统一 LLM 客户端
│   │   ├── models/           #   数据模型
│   │   ├── sandbox/          #   安全沙箱
│   │   └── api/              #   FastAPI 服务
│   ├── tests/                #   测试
│   └── examples/             #   示例脚本
├── frontend/                 # Electron + React 桌面应用
├── targets/                  # 靶机代码
├── config.default.json       # 默认配置
└── pyproject.toml            # 项目元数据
```

---

## 支持的 LLM 后端

| 后端 | 说明 |
|---|---|
| `ollama` | 本地部署，免费且私密 |
| `openai` | GPT-4 / GPT-4o 等 |
| `deepseek` | DeepSeek 推理模型 |
| `anthropic` | Claude 系列 |
| `mock` | 模拟响应，无需联网 |

在 `config.json` 的 `llm_backends` 中添加即可切换。

---

## 开发

```bash
pytest          # 运行所有测试
```

---

## 许可证

MIT
