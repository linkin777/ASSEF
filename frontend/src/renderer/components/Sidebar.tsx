import { motion } from 'framer-motion'
import { useAppStore } from '../store'
import { useArenaStore } from '../store/arenaSlice'

interface NavItem {
  key: 'arena' | 'leaderboard' | 'config' | 'history'
  label: string
  icon: string
}

const navItems: NavItem[] = [
  { key: 'arena', label: '对抗竞技场', icon: 'A' },
  { key: 'leaderboard', label: '模型排行榜', icon: 'L' },
  { key: 'history', label: '历史记录', icon: 'H' },
  { key: 'config', label: '配置管理', icon: 'C' }
]

/**
 * 侧边导航栏组件。
 *
 * 提供竞技场、模型排行榜、配置管理三个页面的导航入口。
 * 当前活跃页面高亮显示，当竞技场任务运行时对应导航项会显示脉冲动画效果。
 *
 * @returns 侧边导航栏 JSX
 */
export default function Sidebar(): JSX.Element {
  const currentPage = useAppStore((s) => s.currentPage)
  const setCurrentPage = useAppStore((s) => s.setCurrentPage)
  const theme = useAppStore((s) => s.theme)
  const toggleTheme = useAppStore((s) => s.toggleTheme)
  const activeTaskId = useArenaStore((s) => s.activeTaskId)

  return (
    <aside className="flex h-full w-56 flex-col border-r border-border bg-sidebar">
      <div className="flex items-center gap-3 border-b border-border px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded bg-accent-cyan/10 text-lg font-bold text-accent-cyan">
          A
        </div>
        <span className="text-lg font-bold tracking-wider text-accent-cyan">
          ASSEF
        </span>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map((item) => {
          const isActive = currentPage === item.key
          const isRunning = item.key === 'arena' && activeTaskId !== null
          return (
            <button
              key={item.key}
              onClick={() => setCurrentPage(item.key)}
              className={`group flex w-full items-center gap-3 rounded-md px-3 py-3 text-sm transition-all duration-200 ${
                isActive
                  ? 'bg-accent-cyan/20 border-l-2 border-accent-cyan text-accent-cyan'
                  : 'border-l-2 border-transparent text-muted-foreground hover:bg-accent-cyan/10 hover:border-accent-cyan/50 hover:text-foreground'
              }`}
            >
              {isRunning ? (
                <motion.span
                  animate={{
                    boxShadow: [
                      '0 0 4px rgba(0,240,255,0.35)',
                      '0 0 14px rgba(0,240,255,0.65)',
                      '0 0 4px rgba(0,240,255,0.35)',
                    ],
                  }}
                  transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
                  className="flex h-7 w-7 items-center justify-center rounded text-xs font-bold bg-accent-cyan/20 text-accent-cyan"
                >
                  {item.icon}
                </motion.span>
              ) : (
                <span
                  className={`flex h-7 w-7 items-center justify-center rounded text-xs font-bold transition-all duration-200 ${
                    isActive
                      ? 'bg-accent-cyan/20 text-accent-cyan shadow-[0_0_8px_rgba(0,240,255,0.3)]'
                      : 'bg-card text-muted-foreground group-hover:shadow-[0_0_6px_rgba(0,240,255,0.15)]'
                  }`}
                >
                  {item.icon}
                </span>
              )}
              <span>{item.label}</span>
            </button>
          )
        })}
      </nav>

      <div className="border-t border-border px-5 py-3 space-y-2">
        <button
          onClick={toggleTheme}
          className="w-full rounded px-3 py-1.5 text-sm bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors"
        >
          {theme === 'dark' ? '☀️ 亮色' : '🌙 暗色'}
        </button>
        <span className="block text-xs text-muted-foreground">v0.1.0</span>
      </div>
    </aside>
  )
}
