import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { Config } from '../../types'
import { useArenaStore } from '../../store/arenaSlice'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../ui/tabs'
import ArenaHeader from './ArenaHeader'
import RedTeamColumn from './columns/RedTeamColumn'
import JudgeColumn from './columns/JudgeColumn'
import BlueTeamColumn from './columns/BlueTeamColumn'
import DiffPanel from './shared/DiffPanel'
import type { ArenaDerivedData } from '../../hooks/useArenaData'

interface ArenaRunningProps {
  data: ArenaDerivedData
  config: Config
  redModelName: string
  blueModelName: string
  judgeModelName: string
  maxRounds: number
  onPauseResume: () => void
  onStop: () => void
  onReturn: () => void
}

export default function ArenaRunning({ data, config, redModelName, blueModelName, judgeModelName, maxRounds, onPauseResume, onStop, onReturn }: ArenaRunningProps) {
  const running = useArenaStore((s) => s.running)
  const paused = useArenaStore((s) => s.paused)
  const connecting = useArenaStore((s) => s.connecting)
  const taskEnded = useArenaStore((s) => s.taskEnded)
  const statusMessage = useArenaStore((s) => s.statusMessage)
  const error = useArenaStore((s) => s.error)
  const bottomTab = useArenaStore((s) => s.bottomTab)
  const bottomOpen = useArenaStore((s) => s.bottomOpen)
  const setBottomTab = useArenaStore((s) => s.setBottomTab)
  const setBottomOpen = useArenaStore((s) => s.setBottomOpen)
  const progressEvents = useArenaStore((s) => s.progressEvents)

  const isTerminal = !running && !connecting

  // 移动端 tab 状态
  const [mobileTab, setMobileTab] = useState('red')

  const sandboxLogs = progressEvents.filter(
    (e) => (e.type === 'info' || e.type === 'error') && (e.step_name.includes('sandbox') || e.data.sandbox)
  )

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex-1 flex flex-col min-h-0 overflow-hidden"
    >
      {/* 顶部工具栏 */}
      <ArenaHeader
        taskEnded={taskEnded}
        connecting={connecting}
        running={running}
        statusMessage={statusMessage}
        currentRound={data.currentRound}
        maxRounds={maxRounds}
        paused={paused}
        redScore={data.redScore}
        blueScore={data.blueScore}
        error={error}
        onPauseResume={onPauseResume}
        onStop={onStop}
        onReturn={onReturn}
        isTerminal={isTerminal}
      />

      {/* 桌面端：lg+ 三列布局 */}
      <div className="hidden lg:flex flex-1 gap-3 px-3 py-3 min-h-0 overflow-hidden">
        <RedTeamColumn
          targetCodeSummary={data.targetCodeSummary}
          attackSuccessCriteria={config.constitution?.attack_success_criteria ?? ''}
          attackScriptRounds={data.attackScriptRounds}
          redStreamText={data.redStreamText}
          isRunning={running}
          roundInfos={data.roundInfos}
          redModelName={redModelName}
        />
        <JudgeColumn
          judgeScript={data.judgeScript}
          scoringRules={config.constitution?.scoring_rules ?? ''}
          allTestResults={data.allTestResults}
          judgeModelName={judgeModelName}
        />
        <BlueTeamColumn
          blueStreamText={data.blueStreamText}
          isRunning={running}
          fixedCodeVersions={data.fixedCodeVersions}
          roundInfos={data.roundInfos}
          allTestResults={data.allTestResults}
          latestFixedCode={data.latestFixedCode}
          redScore={data.redScore}
          blueScore={data.blueScore}
          defenseData={data.defenseData}
          blueModelName={blueModelName}
        />
      </div>

      {/* 中等屏幕：md 双列布局 */}
      <div className="hidden md:flex lg:hidden flex-col flex-1 min-h-0 overflow-hidden">
        <div className="flex-1 flex gap-3 px-3 pt-3 min-h-0 overflow-hidden">
          <RedTeamColumn
            targetCodeSummary={data.targetCodeSummary}
            attackSuccessCriteria={config.constitution?.attack_success_criteria ?? ''}
            attackScriptRounds={data.attackScriptRounds}
            redStreamText={data.redStreamText}
            isRunning={running}
            roundInfos={data.roundInfos}
            redModelName={redModelName}
          />
          <BlueTeamColumn
            blueStreamText={data.blueStreamText}
            isRunning={running}
            fixedCodeVersions={data.fixedCodeVersions}
            roundInfos={data.roundInfos}
            allTestResults={data.allTestResults}
            latestFixedCode={data.latestFixedCode}
            redScore={data.redScore}
            blueScore={data.blueScore}
            defenseData={data.defenseData}
            blueModelName={blueModelName}
          />
        </div>
        <div className="flex-shrink-0 px-3 pb-3 pt-3 max-h-64 overflow-y-auto">
          <JudgeColumn
            judgeScript={data.judgeScript}
            scoringRules={config.constitution?.scoring_rules ?? ''}
            allTestResults={data.allTestResults}
            judgeModelName={judgeModelName}
          />
        </div>
      </div>

      {/* 移动端：sm 单列 + Tab 切换 */}
      <div className="flex md:hidden flex-1 flex-col min-h-0 overflow-hidden">
        <div className="flex-shrink-0 px-3 pt-3">
          <Tabs value={mobileTab} onValueChange={setMobileTab} className="w-full">
            <TabsList className="w-full grid grid-cols-3 bg-card/50">
              <TabsTrigger value="red" className="text-xs data-[state=active]:bg-red-500/20 data-[state=active]:text-team-red">
                红队
              </TabsTrigger>
              <TabsTrigger value="judge" className="text-xs data-[state=active]:bg-yellow-500/20 data-[state=active]:text-team-yellow">
                判官
              </TabsTrigger>
              <TabsTrigger value="blue" className="text-xs data-[state=active]:bg-blue-500/20 data-[state=active]:text-team-blue">
                蓝队
              </TabsTrigger>
            </TabsList>
            <div className="flex-1 overflow-y-auto pt-3">
              <TabsContent value="red" className="mt-0">
                <RedTeamColumn
                  targetCodeSummary={data.targetCodeSummary}
                  attackSuccessCriteria={config.constitution?.attack_success_criteria ?? ''}
                  attackScriptRounds={data.attackScriptRounds}
                  redStreamText={data.redStreamText}
                  isRunning={running}
                  roundInfos={data.roundInfos}
                  redModelName={redModelName}
                />
              </TabsContent>
              <TabsContent value="judge" className="mt-0">
                <JudgeColumn
                  judgeScript={data.judgeScript}
                  scoringRules={config.constitution?.scoring_rules ?? ''}
                  allTestResults={data.allTestResults}
                  judgeModelName={judgeModelName}
                />
              </TabsContent>
              <TabsContent value="blue" className="mt-0">
                <BlueTeamColumn
                  blueStreamText={data.blueStreamText}
                  isRunning={running}
                  fixedCodeVersions={data.fixedCodeVersions}
                  roundInfos={data.roundInfos}
                  allTestResults={data.allTestResults}
                  latestFixedCode={data.latestFixedCode}
                  redScore={data.redScore}
                  blueScore={data.blueScore}
                  defenseData={data.defenseData}
                  blueModelName={blueModelName}
                />
              </TabsContent>
            </div>
          </Tabs>
        </div>
      </div>

      {/* 底部面板：所有屏幕尺寸通用 */}
      <div className="flex-shrink-0 border-t border-border/50">
        <button
          onClick={() => setBottomOpen(!bottomOpen)}
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
                  setBottomTab(tab.key)
                  if (!bottomOpen) setBottomOpen(true)
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
                      <div className="text-xs text-muted-foreground text-center py-4">等待日志...</div>
                    ) : (
                      sandboxLogs.map((log, i) => {
                        const stdout = typeof log.data?.stdout === 'string' ? log.data.stdout : ''
                        const stderr = typeof log.data?.stderr === 'string' ? log.data.stderr : ''
                        const exitCode = log.data?.exit_code !== undefined ? Number(log.data.exit_code) : undefined
                        const elapsed = typeof log.data?.elapsed === 'string' ? log.data.elapsed : (log.data?.elapsed_time != null ? String(log.data.elapsed_time) : '')
                        const formatTime = (ts: number) => {
                          const d = new Date(ts * 1000)
                          return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                        }

                        const ROLE_COLORS: Record<string, string> = { red: '#ff4444', blue: '#4488ff', judge: '#ffaa00', arena: '#00f0ff' }
                        const ROLE_LABELS: Record<string, string> = { red: '红队', blue: '蓝队', judge: '判官', arena: '系统' }

                        return (
                          <div
                            key={i}
                            className={`text-xs px-2 py-1 rounded font-mono ${
                              log.type === 'error' ? 'text-red-400 bg-red-900/10' : 'text-muted-foreground bg-card/30'
                            }`}
                          >
                            <div className="flex items-center gap-2">
                              <span className="text-muted-foreground/70">{formatTime(log.timestamp)}</span>
                              <span style={{ color: ROLE_COLORS[log.role] || '#888' }}>
                                [{ROLE_LABELS[log.role] || log.role}]
                              </span>
                              {exitCode !== undefined && (
                                <span className={exitCode === 0 ? 'text-green-400' : 'text-red-400'}>
                                  exit={exitCode}
                                </span>
                              )}
                              {elapsed && <span className="text-muted-foreground">{elapsed}</span>}
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
                            {!stdout && !stderr && <span>{log.content}</span>}
                          </div>
                        )
                      })
                    )}
                  </div>
                )}
                {bottomTab === 'script' && (
                  <div className="relative">
                    {data.judgeScript ? (
                      <>
                        <pre className="bg-muted text-foreground text-xs p-2 overflow-auto max-h-56 font-mono leading-relaxed rounded">
                          {data.judgeScript}
                        </pre>
                        <button
                          onClick={async () => { try { await navigator.clipboard.writeText(data.judgeScript) } catch { return } }}
                          className="absolute top-2 right-2 px-2 py-1 text-xs rounded bg-muted hover:bg-muted/80 text-foreground transition-colors"
                        >
                          复制
                        </button>
                      </>
                    ) : (
                      <div className="text-xs text-muted-foreground py-8 text-center">等待判官脚本生成...</div>
                    )}
                  </div>
                )}
                {bottomTab === 'diff' && (
                  <DiffPanel versions={data.fixedCodeVersions} originalCode={data.originalCode} />
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  )
}
