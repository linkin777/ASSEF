import { create } from 'zustand'
import type { Config, HistoryRecordSummary, HistoryTypeFilter } from '../types'

/**
 * 应用页面键值类型，对应主导航中的四个页面
 */
type PageKey = 'arena' | 'leaderboard' | 'config' | 'history'

/**
 * 应用全局状态接口
 *
 * 包含后端连接状态、全局配置、当前页面和历史记录等共享状态，
 * 以及用于更新这些状态的操作方法。
 */
interface AppState {
  /** 后端服务是否已连接 */
  backendConnected: boolean
  /** 应用全局配置 */
  config: Config | null
  /** 当前选中的页面 */
  currentPage: PageKey
  /** 当前主题 */
  theme: 'light' | 'dark'
  /** 历史记录列表 */
  historyRecords: HistoryRecordSummary[]
  /** 历史记录总数 */
  historyTotal: number
  /** 历史记录当前页 */
  historyPage: number
  /** 历史记录筛选类型 */
  historyTypeFilter: HistoryTypeFilter
  /** 历史记录加载状态 */
  historyLoading: boolean
  /** 设置后端连接状态 */
  setBackendConnected: (connected: boolean) => void
  /** 设置应用全局配置 */
  setConfig: (config: Config) => void
  /** 切换当前页面 */
  setCurrentPage: (page: PageKey) => void
  /** 切换主题（light / dark） */
  toggleTheme: () => void
  /** 设置历史记录列表数据 */
  setHistoryRecords: (records: HistoryRecordSummary[], total: number, page: number) => void
  /** 设置历史记录筛选类型 */
  setHistoryTypeFilter: (filter: HistoryTypeFilter) => void
  /** 设置历史记录加载状态 */
  setHistoryLoading: (loading: boolean) => void
}

/**
 * 应用全局 Zustand 状态管理 store
 *
 * 管理整个前端应用的共享状态，包括后端连接、
 * 全局配置、页面导航和历史记录等核心数据。组件通过此 store 实现跨页面状态共享。
 */
export const useAppStore = create<AppState>()((set) => ({
  backendConnected: false,
  config: null,
  currentPage: 'arena',
  theme: 'dark',
  historyRecords: [],
  historyTotal: 0,
  historyPage: 1,
  historyTypeFilter: 'all',
  historyLoading: false,
  setBackendConnected: (connected: boolean) => set({ backendConnected: connected }),
  setConfig: (config: Config) => set({ config }),
  setCurrentPage: (page: PageKey) => set({ currentPage: page }),
  toggleTheme: () => set((s) => ({ theme: s.theme === 'dark' ? 'light' : 'dark' })),
  setHistoryRecords: (records: HistoryRecordSummary[], total: number, page: number) =>
    set({ historyRecords: records, historyTotal: total, historyPage: page }),
  setHistoryTypeFilter: (filter: HistoryTypeFilter) =>
    set({ historyTypeFilter: filter, historyPage: 1 }),
  setHistoryLoading: (loading: boolean) => set({ historyLoading: loading }),
}))
