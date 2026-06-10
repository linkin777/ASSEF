import { useEffect } from 'react'
import Sidebar from './components/Sidebar'
import StatusBar from './components/StatusBar'
import ArenaPage from './pages/ArenaPage'
import LeaderboardPage from './pages/LeaderboardPage'
import ConfigPage from './pages/ConfigPage'
import HistoryPage from './pages/HistoryPage'
import { useAppStore } from './store'

/**
 * 应用根组件，负责页面路由和整体布局。
 *
 * 根据全局状态中的 currentPage 决定显示哪个子页面（竞技场/排行榜/配置），
 * 并组合 Sidebar 侧边导航栏和 StatusBar 底部状态栏。
 *
 * @returns 完整的应用布局 JSX
 */
function App(): JSX.Element {
  const currentPage = useAppStore((s) => s.currentPage)
  const theme = useAppStore((s) => s.theme)

  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [theme])

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      {/* 标题栏 - 可拖拽区域 */}
      <div
        className="flex h-8 shrink-0 items-center bg-background border-b border-border"
        style={{ WebkitAppRegion: 'drag' } as React.CSSProperties}
      >
        <span
          className="px-4 text-sm font-semibold text-foreground"
          style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}
        >
          ASSEF
        </span>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-auto p-6">
          <div style={{ display: currentPage === 'arena' ? 'block' : 'none' }}>
            <ArenaPage />
          </div>
          <div style={{ display: currentPage === 'leaderboard' ? 'block' : 'none' }}>
            <LeaderboardPage />
          </div>
          <div style={{ display: currentPage === 'config' ? 'block' : 'none' }}>
            <ConfigPage />
          </div>
          <div style={{ display: currentPage === 'history' ? 'block' : 'none' }}>
            <HistoryPage />
          </div>
        </main>
      </div>
      <StatusBar />
    </div>
  )
}

export default App
