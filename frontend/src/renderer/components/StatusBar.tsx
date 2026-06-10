import { useEffect } from 'react'
import { useAppStore } from '../store'

/**
 * 底部状态栏组件。
 *
 * 显示后端连接状态（已连接/已断开），通过定时轮询 /api/health 接口检测。
 * 连接正常时显示绿色指示灯，断开时显示红色脉冲指示灯。
 *
 * @returns 状态栏 JSX
 */
export default function StatusBar(): JSX.Element {
  const backendConnected = useAppStore((s) => s.backendConnected)
  const setBackendConnected = useAppStore((s) => s.setBackendConnected)

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch('/api/health')
        setBackendConnected(res.ok)
      } catch {
        setBackendConnected(false)
      }
    }

    checkHealth()
    const interval = setInterval(checkHealth, 5000)
    return () => clearInterval(interval)
  }, [setBackendConnected])

  return (
    <footer className="flex h-8 items-center justify-between border-t border-border bg-secondary px-4 text-xs">
      <div className="flex items-center gap-2">
        <span
          className={`inline-block h-2 w-2 rounded-full ${
            backendConnected
              ? 'bg-green-500 shadow-[0_0_6px_rgba(0,255,65,0.6)]'
              : 'animate-pulse bg-red-500 shadow-[0_0_6px_rgba(255,0,0,0.6)]'
          }`}
        />
        <span className={backendConnected ? 'text-muted-foreground' : 'text-red-400'}>
          {backendConnected ? '已连接' : '已断开'}
        </span>
      </div>
      <span className="text-muted-foreground/70">ASSEF v0.1.0</span>
    </footer>
  )
}
