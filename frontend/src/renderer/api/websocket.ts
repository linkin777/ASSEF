import type { ProgressEvent } from '../types'
import { createLogger } from '../utils/logger'

const logger = createLogger('websocket')

const WS_BASE_URL = 'ws://localhost:8710'
const MAX_RETRIES = 3
const RETRY_DELAYS = [1000, 2000, 4000]

/**
 * 任务进度 WebSocket 连接管理器
 *
 * 负责管理与后端之间的 WebSocket 长连接，接收任务实时进度事件。
 * 具备自动重连机制：在连接意外断开时，会以渐进式延迟（1秒、2秒、4秒）
 * 最多重试 3 次。主动调用 disconnect() 断开时不会触发重连。
 */
export class TaskWebSocketManager {
  private ws: WebSocket | null = null
  private taskId: string | null = null
  private onEvent: ((event: ProgressEvent) => void) | null = null
  private retryCount = 0
  private retryTimer: ReturnType<typeof setTimeout> | null = null
  private intentionalClose = false

  /**
   * 建立任务进度 WebSocket 连接
   *
   * 在连接前会先断开已有连接，重置重试计数，然后创建新的 WebSocket 连接。
   * @param taskId - 要监听进度的任务 ID
   * @param onEvent - 接收到进度事件时的回调函数
   */
  connect(taskId: string, onEvent: (event: ProgressEvent) => void): void {
    this.disconnect()
    this.taskId = taskId
    this.onEvent = onEvent
    this.intentionalClose = false
    this.retryCount = 0
    this.createConnection()
  }

  /**
   * 主动断开 WebSocket 连接
   *
   * 标记为主动关闭，清除重试定时器，移除所有事件监听器并关闭连接。
   * 主动断开不会触发自动重连。
   */
  disconnect(): void {
    this.intentionalClose = true
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer)
      this.retryTimer = null
    }
    if (this.ws !== null) {
      this.ws.onclose = null
      this.ws.onerror = null
      this.ws.onmessage = null
      this.ws.close()
      this.ws = null
    }
    this.taskId = null
    this.onEvent = null
    this.retryCount = 0
  }

  /**
   * 创建新的 WebSocket 连接并绑定事件处理器
   *
   * 连接成功后重置重试计数。接收到消息时解析为 ProgressEvent 并回调。
   * 连接关闭时若非主动关闭则自动触发重连。
   */
  private createConnection(): void {
    if (this.taskId === null) return

    const url = `${WS_BASE_URL}/ws/task/${this.taskId}`
    logger.info('Connecting', { url })
    this.ws = new WebSocket(url)

    this.ws.onopen = (): void => {
      this.retryCount = 0
      logger.info('Connected', { url })
    }

    this.ws.onmessage = (event: MessageEvent): void => {
      try {
        const data = JSON.parse(event.data as string) as ProgressEvent
        logger.debug('Event', { type: data.type, role: data.role, step: data.step_name })
        this.onEvent?.(data)
      } catch {
        return
      }
    }

    this.ws.onclose = (): void => {
      logger.info('Closed', { intentional: this.intentionalClose, retries: this.retryCount })
      if (this.intentionalClose) return
      this.attemptReconnect()
    }

    this.ws.onerror = (): void => {
      logger.error('Error', { url })
    }
  }

  /**
   * 尝试重新连接 WebSocket
   *
   * 使用渐进式延迟策略：第1次重试等待1秒，第2次2秒，第3次4秒。
   * 最多重试 MAX_RETRIES（3）次，超过则放弃重连。
   */
  private attemptReconnect(): void {
    if (this.intentionalClose) return
    if (this.retryCount >= MAX_RETRIES) return

    const delay = RETRY_DELAYS[this.retryCount]
    this.retryCount++

    this.retryTimer = setTimeout(() => {
      this.retryTimer = null
      this.createConnection()
    }, delay)
  }
}
