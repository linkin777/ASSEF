import { useEffect, useMemo, useCallback, useState } from 'react'
import { AnimatePresence } from 'framer-motion'
import { getConfig } from '../api/client'
import { useAppStore } from '../store'
import { useArenaStore } from '../store/arenaSlice'
import { useArenaData } from '../hooks/useArenaData'
import { useArenaWebSocket } from '../hooks/useArenaWebSocket'
import { useArenaControl } from '../hooks/useArenaControl'
import ArenaPreLaunch from '../components/arena/ArenaPreLaunch'
import ArenaRunning from '../components/arena/ArenaRunning'

/**
 * 红蓝对抗竞技场页面编排层。
 *
 * 职责：
 * - 加载全局配置
 * - 组合子组件（ArenaPreLaunch / ArenaRunning）
 * - 连接 hooks（useArenaData / useArenaWebSocket / useArenaControl）
 * - 管理 PreLaunch ↔ Running 切换
 */
export default function ArenaPage(): JSX.Element {
  // === 全局配置 ===
  const config = useAppStore((s) => s.config)
  const setConfig = useAppStore((s) => s.setConfig)

  // === Arena 状态 ===
  const running = useArenaStore((s) => s.running)
  const connecting = useArenaStore((s) => s.connecting)
  const taskEnded = useArenaStore((s) => s.taskEnded)
  const progressEvents = useArenaStore((s) => s.progressEvents)
  const targetName = useArenaStore((s) => s.targetName)
  const setTargetName = useArenaStore((s) => s.setTargetName)
  const redBackendIdx = useArenaStore((s) => s.redBackendIdx)
  const blueBackendIdx = useArenaStore((s) => s.blueBackendIdx)
  const judgeBackendIdx = useArenaStore((s) => s.judgeBackendIdx)
  const maxRounds = useArenaStore((s) => s.maxRounds)
  const error = useArenaStore((s) => s.error)

  // === 加载配置 ===
  useEffect(() => {
    if (!config) {
      getConfig()
        .then((cfg) => setConfig(cfg))
        .catch(() => {
          // 错误处理将在组件中显示
        })
    }
  }, [config, setConfig])

  // === 派生数据 ===
  const targets = config?.targets ?? []
  const backends = config?.llm_backends ?? []

  useEffect(() => {
    if (targets.length > 0 && !targetName) {
      setTargetName(targets[0].name)
    }
  }, [targets, targetName, setTargetName])

  const selectedTarget = useMemo(
    () => targets.find((t) => t.name === targetName) ?? null,
    [targets, targetName]
  )

  const derivedData = useArenaData(progressEvents, config, selectedTarget)

  // === WebSocket ===
  const [wsTaskId, setWsTaskId] = useState<string | null>(null)

  const handleWsEvent = useCallback(() => {
    // WebSocket 事件处理已内置于 useArenaWebSocket 的 connect 回调中
  }, [])

  const { connect, disconnect } = useArenaWebSocket({
    taskId: wsTaskId,
    onEvent: handleWsEvent,
    addProgressEvent: useArenaStore.getState().addProgressEvent,
    setStatusMessage: useArenaStore.getState().setStatusMessage,
    setError: useArenaStore.getState().setError,
    setRunning: useArenaStore.getState().setRunning,
    setPaused: useArenaStore.getState().setPaused,
    setTaskEnded: useArenaStore.getState().setTaskEnded,
  })

  // === 控制逻辑 ===
  const {
    handleStart,
    handlePauseResume,
    handleStop,
    handleReturn,
  } = useArenaControl({
    selectedTarget,
    backends,
    connectWebSocket: (taskId: string) => {
      setWsTaskId(taskId)
      connect(taskId)
    },
    disconnectWebSocket: disconnect,
  })

  // === 视图状态 ===
  const showResults = running || connecting || taskEnded || progressEvents.length > 0

  const redModelName = backends[redBackendIdx]?.model ?? ''
  const blueModelName = backends[blueBackendIdx]?.model ?? ''
  const judgeModelName = backends[judgeBackendIdx]?.model ?? ''

  // === 加载中 ===
  if (!config) {
    return (
      <div className="flex h-full flex-col items-center justify-center bg-surface-primary">
        <div className="w-8 h-8 border-2 border-accent-cyan border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-muted-foreground">加载配置中...</p>
        {error && <p className="text-red-400 text-sm mt-2">{error}</p>}
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-surface-primary text-foreground overflow-hidden">
      <AnimatePresence mode="wait">
        {!showResults ? (
          <ArenaPreLaunch
            key="prelaunch"
            targets={targets}
            backends={backends}
            onStart={handleStart}
            loading={connecting}
          />
        ) : (
          <ArenaRunning
            key="running"
            data={derivedData}
            config={config}
            redModelName={redModelName}
            blueModelName={blueModelName}
            judgeModelName={judgeModelName}
            maxRounds={maxRounds}
            onPauseResume={handlePauseResume}
            onStop={handleStop}
            onReturn={handleReturn}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
