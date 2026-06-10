import { useCallback } from 'react'
import type { ArenaRequest, TargetConfig, LLMBackendConfig } from '../types'
import { startArena, pauseTask, resumeTask, cancelTask } from '../api/client'
import { useArenaStore } from '../store/arenaSlice'

interface UseArenaControlOptions {
  selectedTarget: TargetConfig | null
  backends: LLMBackendConfig[]
  connectWebSocket: (taskId: string) => void
  disconnectWebSocket: () => void
}

export function useArenaControl(options: UseArenaControlOptions) {
  const { selectedTarget, backends, connectWebSocket, disconnectWebSocket } = options

  const {
    redBackendIdx,
    blueBackendIdx,
    judgeBackendIdx,
    maxRounds,
    taskId,
    paused,
    running,
    connecting,
    error,
    statusMessage,

    setError,
    setStatusMessage,
    setConnecting,
    setTaskEnded,
    setBottomOpen,
    clearProgressEvents,
    setTaskId,
    setActiveTask,
    setRunning,
    setPaused,
  } = useArenaStore()

  const handleStart = useCallback(async () => {
    if (!selectedTarget) return
    setError('')
    setStatusMessage('正在启动竞技场...')
    setConnecting(true)
    setTaskEnded(false)
    setBottomOpen(true)
    clearProgressEvents()

    const redBackend = backends[redBackendIdx]
    const blueBackend = backends[blueBackendIdx]
    const judgeBackend = backends[judgeBackendIdx]

    const req: ArenaRequest = {
      target_name: selectedTarget.name,
      max_rounds: maxRounds,
      red_backend_name: redBackend?.backend ?? '',
      blue_backend_name: blueBackend?.backend ?? '',
      judge_backend_name: judgeBackend?.backend ?? '',
    }

    try {
      const res = await startArena(req)
      setTaskId(res.task_id)
      setActiveTask(res.task_id)
      setRunning(true)
      setPaused(false)
      setStatusMessage('已连接，等待任务进度...')

      connectWebSocket(res.task_id)
      setConnecting(false)
    } catch (err) {
      const msg = err instanceof Error ? err.message : '启动失败'
      setError(msg)
      setStatusMessage(`启动失败: ${msg}`)
      setConnecting(false)
    }
  }, [
    selectedTarget, maxRounds, backends,
    redBackendIdx, blueBackendIdx, judgeBackendIdx,
    clearProgressEvents, setActiveTask,
    setError, setStatusMessage, setConnecting, setTaskEnded,
    setBottomOpen, setTaskId, setRunning, setPaused,
    connectWebSocket,
  ])

  const handlePauseResume = useCallback(async () => {
    const currentTaskId = taskId
    if (!currentTaskId) return
    try {
      if (paused) {
        await resumeTask(currentTaskId)
        setPaused(false)
        setStatusMessage('已恢复')
      } else {
        await pauseTask(currentTaskId)
        setPaused(true)
        setStatusMessage('已暂停')
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '操作失败'
      setError(msg)
    }
  }, [taskId, paused, setPaused, setStatusMessage, setError])

  const handleStop = useCallback(async () => {
    const currentTaskId = taskId
    if (!currentTaskId) return
    setStatusMessage('正在停止...')
    try {
      await cancelTask(currentTaskId)
      disconnectWebSocket()
      setRunning(false)
      setPaused(false)
      setConnecting(false)
      setTaskEnded(true)
      setActiveTask(null)
      setTaskId(null)
      setStatusMessage('已停止')
    } catch (err) {
      const msg = err instanceof Error ? err.message : '停止失败'
      setError(msg)
    }
  }, [taskId, setActiveTask, setStatusMessage, setError,
      setRunning, setPaused, setConnecting, setTaskEnded,
      setTaskId, disconnectWebSocket])

  const handleReturn = useCallback(() => {
    disconnectWebSocket()
    setTaskEnded(false)
    clearProgressEvents()
    setError('')
    setStatusMessage('')
    setRunning(false)
    setPaused(false)
    setConnecting(false)
    setTaskId(null)
    setActiveTask(null)
  }, [clearProgressEvents, setError, setStatusMessage, setTaskEnded,
      disconnectWebSocket, setRunning, setPaused, setConnecting,
      setTaskId, setActiveTask])

  return {
    handleStart,
    handlePauseResume,
    handleStop,
    handleReturn,
    running,
    paused,
    connecting,
    error,
    statusMessage,
  }
}
