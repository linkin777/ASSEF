import { create } from 'zustand'
import type { ProgressEvent, TaskStatus } from '../types'

interface ArenaState {
  // === 配置态 ===
  targetName: string
  redBackendIdx: number
  blueBackendIdx: number
  judgeBackendIdx: number
  maxRounds: number

  // === 运行态 ===
  taskId: string | null
  running: boolean
  paused: boolean
  connecting: boolean
  taskEnded: boolean
  error: string
  statusMessage: string

  // === 数据态 ===
  activeTaskId: string | null
  taskStatus: TaskStatus | null
  progressEvents: ProgressEvent[]

  // === UI 态 ===
  bottomTab: 'sandbox' | 'script' | 'diff'
  bottomOpen: boolean

  // === Actions ===
  setTargetName: (name: string) => void
  setRedBackendIdx: (idx: number) => void
  setBlueBackendIdx: (idx: number) => void
  setJudgeBackendIdx: (idx: number) => void
  setMaxRounds: (n: number) => void
  setTaskId: (id: string | null) => void
  setRunning: (v: boolean) => void
  setPaused: (v: boolean) => void
  setConnecting: (v: boolean) => void
  setTaskEnded: (v: boolean) => void
  setError: (msg: string) => void
  setStatusMessage: (msg: string) => void
  setActiveTask: (taskId: string | null) => void
  addProgressEvent: (event: ProgressEvent) => void
  clearProgressEvents: () => void
  setBottomTab: (tab: 'sandbox' | 'script' | 'diff') => void
  setBottomOpen: (open: boolean) => void
  reset: () => void
}

const initialState = {
  targetName: '',
  redBackendIdx: 0,
  blueBackendIdx: 0,
  judgeBackendIdx: 0,
  maxRounds: 10,
  taskId: null,
  running: false,
  paused: false,
  connecting: false,
  taskEnded: false,
  error: '',
  statusMessage: '',
  activeTaskId: null,
  taskStatus: null,
  progressEvents: [] as ProgressEvent[],
  bottomTab: 'sandbox' as const,
  bottomOpen: false,
}

export const useArenaStore = create<ArenaState>()((set) => ({
  ...initialState,

  setTargetName: (name) => set({ targetName: name }),
  setRedBackendIdx: (idx) => set({ redBackendIdx: idx }),
  setBlueBackendIdx: (idx) => set({ blueBackendIdx: idx }),
  setJudgeBackendIdx: (idx) => set({ judgeBackendIdx: idx }),
  setMaxRounds: (n) => set({ maxRounds: n }),
  setTaskId: (id) => set({ taskId: id }),
  setRunning: (v) => set({ running: v }),
  setPaused: (v) => set({ paused: v }),
  setConnecting: (v) => set({ connecting: v }),
  setTaskEnded: (v) => set({ taskEnded: v }),
  setError: (msg) => set({ error: msg }),
  setStatusMessage: (msg) => set({ statusMessage: msg }),
  setActiveTask: (taskId) => set({ activeTaskId: taskId, taskStatus: null }),
  addProgressEvent: (event) =>
    set((state) => ({ progressEvents: [...state.progressEvents, event] })),
  clearProgressEvents: () => set({ progressEvents: [] }),
  setBottomTab: (tab) => set({ bottomTab: tab }),
  setBottomOpen: (open) => set({ bottomOpen: open }),
  reset: () => set(initialState),
}))
