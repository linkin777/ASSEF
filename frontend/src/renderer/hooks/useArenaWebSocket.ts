import { useRef, useCallback, useEffect } from 'react'
import type { ProgressEvent } from '../types'
import { TaskWebSocketManager } from '../api/websocket'

const ROLE_LABELS: Record<string, string> = {
  red: '红队',
  blue: '蓝队',
  judge: '判官',
  arena: '系统',
}

const STEP_LABELS: Record<string, string> = {
  attack_plan: '攻击脚本',
  judge_attack: '判官判定',
  judge_defense: '防御评估',
  generate_fix: '蓝队修复',
  generate_enhance: '蓝队增强',
  setup_judge: '初始化判官',
  generate_attack: '红队攻击',
  try_defense: '尝试防御',
  round: '回合',
  setup: '初始化',
}

interface UseArenaWebSocketOptions {
  taskId: string | null
  onEvent: (event: ProgressEvent) => void
  addProgressEvent: (event: ProgressEvent) => void
  setStatusMessage: (msg: string) => void
  setError: (msg: string) => void
  setRunning: (v: boolean) => void
  setPaused: (v: boolean) => void
  setTaskEnded: (v: boolean) => void
}

export function useArenaWebSocket(options: UseArenaWebSocketOptions) {
  const {
    taskId,
    onEvent,
    addProgressEvent,
    setStatusMessage,
    setError,
    setRunning,
    setPaused,
    setTaskEnded,
  } = options

  const wsRef = useRef<TaskWebSocketManager | null>(null)

  // 创建 WebSocket 连接
  const connect = useCallback((tid: string) => {
    const manager = new TaskWebSocketManager()
    wsRef.current = manager
    manager.connect(tid, (event: ProgressEvent) => {
      // 先调用外部 onEvent
      onEvent(event)

      // 再处理内置的事件分发（状态更新）
      addProgressEvent(event)

      if (event.type === 'info') {
        setStatusMessage(event.content)
      }
      if (event.type === 'error') {
        setError(`错误: ${event.content}`)
        setStatusMessage(`错误: ${event.content}`)
      }
      if (event.type === 'task_done') {
        setRunning(false)
        setPaused(false)
        setTaskEnded(true)
        const errData = event.data?.error
        if (typeof errData === 'string' && errData) {
          setError(`任务失败: ${errData}`)
          setStatusMessage(`任务失败: ${errData}`)
        } else if (event.data?.cancelled) {
          setStatusMessage('任务已取消')
        } else if (event.data?.result) {
          setStatusMessage('任务完成')
        }
      }
      if (event.type === 'step_start' || event.type === 'step_done') {
        const label = STEP_LABELS[event.step_name] || event.step_name
        const role = ROLE_LABELS[event.role] || event.role
        setStatusMessage(`${role} - ${label} ${event.type === 'step_start' ? '开始' : '完成'}`)
      }
    })
  }, [onEvent, addProgressEvent, setStatusMessage, setError, setRunning, setPaused, setTaskEnded])

  // 断开连接
  const disconnect = useCallback(() => {
    wsRef.current?.disconnect()
    wsRef.current = null
  }, [])

  // 组件卸载时自动清理
  useEffect(() => {
    return () => {
      disconnect()
    }
  }, [disconnect])

  return { connect, disconnect, wsRef }
}
