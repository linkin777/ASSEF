import { AnimatePresence, motion } from 'framer-motion'
import type { ProgressEvent } from '../../types'
import DiffPanel from './shared/DiffPanel'

const ROLE_COLORS: Record<string, string> = {
  red: '#ff4444',
  blue: '#4488ff',
  judge: '#ffaa00',
  arena: '#00f0ff',
}

const ROLE_LABELS: Record<string, string> = {
  red: '红队',
  blue: '蓝队',
  judge: '判官',
  arena: '系统',
}

function safeString(data: Record<string, unknown>, key: string, fallback = ''): string {
  const v = data[key]
  return typeof v === 'string' ? v : fallback
}

function formatTime(ts: number): string {
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

interface CodeVersion {
  round: number
  code: string
  timestamp: number
}

interface BottomPanelProps {
  bottomTab: 'sandbox' | 'script' | 'diff'
  bottomOpen: boolean
  sandboxLogs: ProgressEvent[]
  judgeScript: string
  fixedCodeVersions: CodeVersion[]
  originalCode: string
  onTabChange: (tab: 'sandbox' | 'script' | 'diff') => void
  onToggle: () => void
}

export default function BottomPanel({
  bottomTab,
  bottomOpen,
  sandboxLogs,
  judgeScript,
  fixedCodeVersions,
  originalCode,
  onTabChange,
  onToggle,
}: BottomPanelProps): JSX.Element {
  return (
    <div className="flex-shrink-0 border-t border-border/50">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-2 bg-muted/60 hover:bg-card/60 transition-colors"
      >
        <div className="flex items-center gap-3">
          {([
            { key: 'sandbox' as const, label: '沙盒日志', icon: '📋' },
            { key: 'script' as const, label: '判词脚本', icon: '📜' },
            { key: 'diff' as const, label: '代码版本历史', icon: '🔍' },
          ]).map((tab) => (
            <button
              key={tab.key}
              onClick={(e) => {
                e.stopPropagation()
                onTabChange(tab.key)
                if (!bottomOpen) onToggle()
              }}
              className={`text-xs px-2 py-1 rounded transition-colors ${
                bottomTab === tab.key
                  ? 'bg-muted text-foreground'
                  : 'text-muted-foreground hover:text-foreground/80'
              }`}
            >
              {tab.icon} {tab.label}
            </button>
          ))}
        </div>
        <span className="text-muted-foreground text-xs">{bottomOpen ? '▼' : '▲'}</span>
      </button>
      <AnimatePresence>
        {bottomOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-3 max-h-64 overflow-y-auto">
              {bottomTab === 'sandbox' && (
                <div className="space-y-1">
                  {sandboxLogs.length === 0 ? (
                    <div className="text-xs text-muted-foreground text-center py-4">{'等待日志...'}</div>
                  ) : (
                    sandboxLogs.map((log, i) => {
                      const stdout = safeString(log.data, 'stdout', '')
                      const stderr = safeString(log.data, 'stderr', '')
                      const exitCode = log.data.exit_code !== undefined ? Number(log.data.exit_code) : undefined
                      const elapsed = safeString(log.data, 'elapsed', '') || (log.data.elapsed_time != null ? String(log.data.elapsed_time) : '')

                      return (
                        <div
                          key={i}
                          className={`text-xs px-2 py-1 rounded font-mono ${
                            log.type === 'error'
                              ? 'text-red-400 bg-red-900/10'
                              : 'text-muted-foreground bg-card/30'
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            <span className="text-muted-foreground/70">{formatTime(log.timestamp)}</span>
                            <span
                              className="mr-1"
                              style={{ color: ROLE_COLORS[log.role] || '#888' }}
                            >
                              [{ROLE_LABELS[log.role] || log.role}]
                            </span>
                            {exitCode !== undefined && (
                              <span className={exitCode === 0 ? 'text-green-400' : 'text-red-400'}>
                                exit={exitCode}
                              </span>
                            )}
                            {elapsed && (
                              <span className="text-muted-foreground">{elapsed}</span>
                            )}
                          </div>
                          {stdout && (
                            <pre className="mt-1 text-foreground bg-muted rounded p-1 max-h-24 overflow-y-auto whitespace-pre-wrap break-all">
                              {stdout.slice(0, 500)}
                            </pre>
                          )}
                          {stderr && (
                            <pre className="mt-1 text-red-300 bg-red-900/20 rounded p-1 max-h-24 overflow-y-auto whitespace-pre-wrap break-all">
                              {stderr.slice(0, 500)}
                            </pre>
                          )}
                          {!stdout && !stderr && (
                            <span>{log.content}</span>
                          )}
                        </div>
                      )
                    })
                  )}
                </div>
              )}

              {bottomTab === 'script' && (
                <div className="relative">
                  {judgeScript ? (
                      <>
                        <pre className="bg-muted text-foreground text-xs p-2 overflow-auto max-h-56 font-mono leading-relaxed rounded">
                          {judgeScript}
                        </pre>
                        <button
                          onClick={async () => {
                            try {
                              await navigator.clipboard.writeText(judgeScript)
                            } catch {
                              return
                            }
                          }}
                          className="absolute top-2 right-2 px-2 py-1 text-xs rounded bg-muted hover:bg-muted/80 text-foreground transition-colors"
                        >
                          {'复制'}
                        </button>
                      </>
                    ) : (
                      <div className="text-xs text-muted-foreground py-8 text-center">{'等待判官脚本生成...'}</div>
                    )}
                </div>
              )}

              {bottomTab === 'diff' && (
                <DiffPanel
                  versions={fixedCodeVersions}
                  originalCode={originalCode}
                />
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
