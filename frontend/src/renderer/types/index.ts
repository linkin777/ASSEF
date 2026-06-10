/**
 * Electron 预加载脚本暴露给渲染进程的 API 接口
 * 通过 contextBridge 在 window.electronAPI 上提供安全的 IPC 通信
 */
export interface ElectronAPI {
  platform: string
  logToFile: (module: string, level: string, message: string, data?: unknown) => Promise<void>
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}

/**
 * LLM 后端类型，支持 Ollama、OpenAI、DeepSeek、Anthropic 及本地 Mock
 */
export type LLMBackendType = 'ollama' | 'openai' | 'deepseek' | 'anthropic' | 'mock'

/**
 * 沙箱执行环境类型：本地进程或 Docker 容器
 */
export type SandboxType = 'process' | 'docker'

/**
 * 任务运行状态类型
 */
export type TaskStatusType = 'running' | 'paused' | 'completed' | 'cancelled' | 'error' | 'unknown'

/**
 * LLM 后端连接配置
 * 包含后端类型、模型名称、API 密钥、请求地址及生成参数
 */
export interface LLMBackendConfig {
  backend: LLMBackendType
  model: string
  api_key: string
  base_url: string
  max_retries: number
  temperature: number
  max_tokens: number
  mock_response: string
}

/**
 * 游戏规则配置
 * 控制竞技场中红蓝双方的策略参数、轮次限制和性能约束
 */
export interface GameRulesConfig {
  max_blue_retries: number
  performance_degrade_limit: number
  code_bloat_limit: number
  red_strategy_mutation_threshold: number
  max_arena_rounds: number
  self_adversary_attempts: number
  blue_self_iteration_limit: number
  red_max_plans_early: number
  red_max_plans_late: number
}

/**
 * 宪法配置
 * 定义攻击/修复成功标准、评分规则和约束条件的核心规则文本
 */
export interface ConstitutionConfig {
  preamble: string
  attack_success_criteria: string
  fix_success_criteria: string
  scoring_rules: string
  constraints: string
}

/**
 * 沙箱执行环境配置
 */
export interface SandboxConfig {
  timeout: number
  dangerous_patterns: string[]
  description: string
}

/**
 * 成功标准配置，分别定义攻击和修复的成功判断条件
 */
export interface SuccessCriteriaConfig {
  attack: string
  fix: string
}

/**
 * 普通测试用例配置，用于验证代码功能正确性
 */
export interface NormalTestConfig {
  name: string
  input: Record<string, unknown>
  expected_output: Record<string, unknown>
}

/**
 * 目标系统配置
 * 描述一个完整的被测试目标，包括代码、沙箱环境、攻击面和测试用例
 */
export interface TargetConfig {
  name: string
  description: string
  sandbox_type: SandboxType
  sandbox_spec: Record<string, unknown>
  code_path: string
  code: string
  public_spec: string
  attack_surface: string
  success_criteria: SuccessCriteriaConfig
  normal_tests: NormalTestConfig[]
}

/**
 * 应用全局配置
 * 聚合 LLM 后端、游戏规则、宪法、沙箱和目标系统的完整配置
 */
export interface Config {
  llm_backends: LLMBackendConfig[]
  game_rules: GameRulesConfig
  constitution: ConstitutionConfig
  sandbox: SandboxConfig
  targets: TargetConfig[]
}

/**
 * 竞技场任务请求参数
 * 定义一场红蓝对抗的基本设置
 */
export interface ArenaRequest {
  target_name: string
  max_rounds: number
  red_backend_name: string
  blue_backend_name: string
  judge_backend_name: string
}

/**
 * 基准测试任务请求参数
 * 支持多目标、多后端批量测试
 */
export interface BenchmarkRequest {
  target_names: string[]
  backend_names: string[]
}

/**
 * 任务进度事件
 * 通过 WebSocket 实时推送，描述任务执行过程中的每个步骤
 */
export interface ProgressEvent {
  type: string
  role: string
  step_name: string
  content: string
  data: Record<string, unknown>
  timestamp: number
}

/**
 * 任务状态信息
 * 包含任务 ID、类型、运行状态及可能的错误信息
 */
export interface TaskStatus {
  task_id: string
  task_type: string
  status: TaskStatusType
  error: {
    message: string
    detail: string
  } | null
  started_at: number
}

/**
 * API 请求错误类
 * 封装 HTTP 状态码和错误详情，用于统一的错误处理
 */
export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, message: string, detail?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail || ''
  }
}

/**
 * 历史记录摘要，用于列表展示
 */
export interface HistoryRecordSummary {
  record_id: string
  record_type: 'arena' | 'benchmark'
  created_at: string
  target_name?: string
  total_rounds?: number
  red_score?: number
  blue_score?: number
  target_names?: string[]
  model_names?: string[]
  total_combinations?: number
}

/**
 * 历史记录列表响应
 */
export interface HistoryListResponse {
  items: HistoryRecordSummary[]
  total: number
  page: number
  page_size: number
}

/**
 * 历史记录筛选类型
 */
export type HistoryTypeFilter = 'all' | 'arena' | 'benchmark'
