import type {
  ArenaRequest,
  BenchmarkRequest,
  Config,
  HistoryListResponse,
  LLMBackendConfig,
  TaskStatus,
} from '../types'
import { ApiError } from '../types'

const BASE_URL = 'http://localhost:8710'

/**
 * 通用 HTTP 请求封装，自动处理 JSON 序列化与错误转换
 * @param path - API 路径
 * @param options - fetch 请求选项
 * @returns 解析后的 JSON 响应
 */
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${path}`
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
    },
    ...options,
  })

  if (!res.ok) {
    let detail = ''
    try {
      const errorBody = await res.json()
      detail = errorBody.detail || ''
    } catch {
      detail = res.statusText
    }
    throw new ApiError(res.status, `请求失败: ${res.status} ${res.statusText}`, detail)
  }

  return res.json() as Promise<T>
}

/**
 * 获取应用全局配置
 * @returns 完整的配置对象
 */
export async function getConfig(): Promise<Config> {
  return request<Config>('/api/config')
}

/**
 * 更新应用全局配置
 * @param config - 新的完整配置对象
 * @returns 更新后的配置对象
 */
export async function updateConfig(config: Config): Promise<Config> {
  return request<Config>('/api/config', {
    method: 'PUT',
    body: JSON.stringify(config),
  })
}

/**
 * 启动竞技场（红蓝对抗）任务
 * @param req - 竞技场请求参数，包含目标、轮次、红方/蓝方/裁判后端
 * @returns 包含 task_id 和状态的新任务信息
 */
export async function startArena(req: ArenaRequest): Promise<{ task_id: string; status: string }> {
  return request<{ task_id: string; status: string }>('/api/arena/start', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

/**
 * 启动基准测试任务
 * @param req - 基准测试请求参数，包含目标列表和后端列表
 * @returns 包含 task_id 和状态的新任务信息
 */
export async function startBenchmark(
  req: BenchmarkRequest
): Promise<{ task_id: string; status: string }> {
  return request<{ task_id: string; status: string }>('/api/benchmark/start', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

/**
 * 测试 LLM 后端连接是否正常
 * @param config - LLM 后端配置
 * @returns 包含 ok 标志和消息的测试结果
 */
export async function testLLM(config: LLMBackendConfig): Promise<{ ok: boolean; message: string }> {
  return request<{ ok: boolean; message: string }>('/api/llm/test', {
    method: 'POST',
    body: JSON.stringify(config),
  })
}

/**
 * 暂停指定任务
 * @param taskId - 任务 ID
 * @returns 操作结果
 */
export async function pauseTask(taskId: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/task/${taskId}/pause`, {
    method: 'POST',
  })
}

/**
 * 恢复已暂停的任务
 * @param taskId - 任务 ID
 * @returns 操作结果
 */
export async function resumeTask(taskId: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/task/${taskId}/resume`, {
    method: 'POST',
  })
}

/**
 * 取消指定任务
 * @param taskId - 任务 ID
 * @returns 操作结果
 */
export async function cancelTask(taskId: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/task/${taskId}/cancel`, {
    method: 'POST',
  })
}

/**
 * 获取单个任务的详细状态
 * @param taskId - 任务 ID
 * @returns 任务状态对象
 */
export async function getTaskStatus(taskId: string): Promise<TaskStatus> {
  return request<TaskStatus>(`/api/task/${taskId}`)
}

/**
 * 获取所有任务的状态列表
 * @returns 任务状态数组
 */
export async function getAllTasks(): Promise<TaskStatus[]> {
  return request<TaskStatus[]>('/api/task')
}

/**
 * 检查后端服务健康状态
 * @returns 后端是否健康可用
 */
export async function checkHealth(): Promise<boolean> {
  try {
    const res = await request<{ status: string }>('/api/health')
    return res.status === 'ok'
  } catch {
    return false
  }
}

/**
 * 获取历史记录列表
 * @param type - 筛选类型
 * @param page - 页码
 * @param pageSize - 每页条数
 * @returns 分页列表响应
 */
export async function getHistoryList(
  type?: string,
  page: number = 1,
  pageSize: number = 20
): Promise<HistoryListResponse> {
  const params = new URLSearchParams()
  if (type) params.set('type', type)
  params.set('page', String(page))
  params.set('page_size', String(pageSize))
  return request<HistoryListResponse>(`/api/history/list?${params.toString()}`)
}

/**
 * 获取历史记录详情
 * @param recordId - 记录 ID
 * @returns 完整记录数据
 */
export async function getHistoryDetail(recordId: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/api/history/detail/${recordId}`)
}

/**
 * 删除历史记录
 * @param recordId - 记录 ID
 * @returns 操作结果
 */
export async function deleteHistory(recordId: string): Promise<{ status: string; record_id: string }> {
  return request<{ status: string; record_id: string }>(`/api/history/${recordId}`, {
    method: 'DELETE',
  })
}
