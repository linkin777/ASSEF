import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { TargetConfig, LLMBackendConfig } from '../../types'
import { useArenaStore } from '../../store/arenaSlice'
import { Button } from '../ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { cn } from '../../lib/utils'

interface ArenaPreLaunchProps {
  targets: TargetConfig[]
  backends: LLMBackendConfig[]
  onStart: () => void
  loading?: boolean
}

const STEPS = [
  { key: 1, label: '靶机选择' },
  { key: 2, label: '角色分配' },
  { key: 3, label: '确认启动' },
]

function stepCircleClass(current: number, s: { key: number }): string {
  if (current === s.key) {
    return 'bg-accent-cyan text-background shadow-glow-cyan'
  }
  if (current > s.key) {
    return 'bg-accent-cyan/30 text-accent-cyan cursor-pointer hover:bg-accent-cyan/50'
  }
  return 'bg-card text-muted-foreground'
}

export default function ArenaPreLaunch({ targets, backends, onStart, loading }: ArenaPreLaunchProps) {
  const [step, setStep] = useState(1)
  
  const targetName = useArenaStore((s) => s.targetName)
  const setTargetName = useArenaStore((s) => s.setTargetName)
  const redBackendIdx = useArenaStore((s) => s.redBackendIdx)
  const setRedBackendIdx = useArenaStore((s) => s.setRedBackendIdx)
  const blueBackendIdx = useArenaStore((s) => s.blueBackendIdx)
  const setBlueBackendIdx = useArenaStore((s) => s.setBlueBackendIdx)
  const judgeBackendIdx = useArenaStore((s) => s.judgeBackendIdx)
  const setJudgeBackendIdx = useArenaStore((s) => s.setJudgeBackendIdx)
  const maxRounds = useArenaStore((s) => s.maxRounds)
  const setMaxRounds = useArenaStore((s) => s.setMaxRounds)
  const error = useArenaStore((s) => s.error)

  const selectedTarget = targets.find((t) => t.name === targetName) ?? null

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="flex-1 flex flex-col items-center justify-center gap-6 px-4"
    >
      <div className="rounded-xl border border-border bg-card p-6 w-full max-w-3xl">
        {/* 标题 */}
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-accent-cyan tracking-wider">
            {'⚔️'} ASSEF 竞技场
          </h1>
          <p className="text-xs text-muted-foreground mt-1">AI 安全对抗演习平台</p>
        </div>

        {/* 步骤指示器 */}
        <div className="flex items-center justify-center gap-4 mb-6">
          {STEPS.map((s, i) => (
            <div key={s.key} className="flex items-center gap-2">
              <button
                onClick={() => {
                  if (s.key < step) setStep(s.key)
                }}
                className={cn(
                  'w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors',
                  stepCircleClass(step, s)
                )}
              >
                {step > s.key ? '✓' : s.key}
              </button>
              <span className={cn('text-xs', step >= s.key ? 'text-foreground' : 'text-muted-foreground/70')}>
                {s.label}
              </span>
              {i < STEPS.length - 1 && (
                <div
                  className={cn(
                    'w-12 h-0.5 ml-2',
                    step > s.key ? 'bg-accent-cyan/50' : 'bg-muted'
                  )}
                />
              )}
            </div>
          ))}
        </div>

        <AnimatePresence mode="wait">
          {/* Step 1: 靶机选择 */}
          {step === 1 && (
            <motion.div
              key="step1"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
              className="space-y-4"
            >
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground uppercase tracking-wide">选择靶机</label>
                <Select value={targetName} onValueChange={setTargetName}>
                  <SelectTrigger className="bg-card border border-border text-foreground">
                    <SelectValue placeholder="选择靶机..." />
                  </SelectTrigger>
                  <SelectContent className="bg-card border border-border">
                    {targets.map((t) => (
                      <SelectItem key={t.name} value={t.name} className="text-foreground">
                        {t.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {selectedTarget && (
                <div className="bg-card/50 rounded-lg p-3 border border-border">
                  <div className="text-xs text-muted-foreground mb-1">{selectedTarget.description}</div>
                  <div className="flex gap-4 text-xs text-muted-foreground">
                    <span>沙箱: {selectedTarget.sandbox_type}</span>
                    <span>攻击面: {selectedTarget.attack_surface}</span>
                  </div>
                  {selectedTarget.code && (
                    <pre className="mt-2 text-xs text-muted-foreground font-mono bg-muted/50 rounded p-2 max-h-32 overflow-hidden">
                      {selectedTarget.code.slice(0, 500)}
                      {selectedTarget.code.length > 500 ? '\n...' : ''}
                    </pre>
                  )}
                </div>
              )}

              <div className="flex justify-end">
                <Button
                  onClick={() => setStep(2)}
                  disabled={!targetName}
                  className="bg-accent-cyan hover:bg-accent-cyan/80 text-background"
                >
                  下一步
                </Button>
              </div>
            </motion.div>
          )}

          {/* Step 2: 角色分配 */}
          {step === 2 && (
            <motion.div
              key="step2"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
              className="space-y-4"
            >
              <div className="flex flex-wrap items-end gap-4">
                {/* 红队选择 */}
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-muted-foreground uppercase tracking-wide">
                    <span className="text-team-red">{'●'}</span> 红队 LLM
                  </label>
                  <Select
                    value={String(redBackendIdx)}
                    onValueChange={(v) => setRedBackendIdx(Number(v))}
                  >
                    <SelectTrigger className="bg-card border border-border text-foreground w-44">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-card border border-border">
                      {backends.map((b, i) => (
                        <SelectItem key={i} value={String(i)} className="text-foreground">
                          {b.backend} / {b.model}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* 蓝队选择 */}
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-muted-foreground uppercase tracking-wide">
                    <span className="text-team-blue">{'●'}</span> 蓝队 LLM
                  </label>
                  <Select
                    value={String(blueBackendIdx)}
                    onValueChange={(v) => setBlueBackendIdx(Number(v))}
                  >
                    <SelectTrigger className="bg-card border border-border text-foreground w-44">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-card border border-border">
                      {backends.map((b, i) => (
                        <SelectItem key={i} value={String(i)} className="text-foreground">
                          {b.backend} / {b.model}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* 判官选择 */}
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-muted-foreground uppercase tracking-wide">
                    <span className="text-team-yellow">{'●'}</span> 判官 LLM
                  </label>
                  <Select
                    value={String(judgeBackendIdx)}
                    onValueChange={(v) => setJudgeBackendIdx(Number(v))}
                  >
                    <SelectTrigger className="bg-card border border-border text-foreground w-44">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-card border border-border">
                      {backends.map((b, i) => (
                        <SelectItem key={i} value={String(i)} className="text-foreground">
                          {b.backend} / {b.model}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* 最大回合数 */}
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-muted-foreground uppercase tracking-wide">最大回合数</label>
                  <input
                    type="number"
                    min={1}
                    max={50}
                    value={maxRounds}
                    onChange={(e) => setMaxRounds(Math.max(1, Number(e.target.value)))}
                    className="bg-card border border-border rounded px-3 py-1.5 text-sm text-foreground w-20 focus:border-ring focus:outline-none"
                  />
                </div>
              </div>

              <div className="flex justify-between">
                <Button variant="ghost" onClick={() => setStep(1)} className="text-muted-foreground">
                  上一步
                </Button>
                <Button
                  onClick={() => setStep(3)}
                  disabled={backends.length === 0}
                  className="bg-accent-cyan hover:bg-accent-cyan/80 text-background"
                >
                  下一步
                </Button>
              </div>
            </motion.div>
          )}

          {/* Step 3: 确认启动 */}
          {step === 3 && (
            <motion.div
              key="step3"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
              className="space-y-4"
            >
              <div className="bg-card/50 rounded-lg p-4 border border-border space-y-3">
                <h3 className="text-sm font-medium text-foreground">配置摘要</h3>
                
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <span className="text-muted-foreground">靶机:</span>
                    <span className="text-foreground ml-2">{selectedTarget?.name ?? '-'}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">回合数:</span>
                    <span className="text-foreground ml-2">{maxRounds}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">红队:</span>
                    <span className="text-team-red ml-2">
                      {backends[redBackendIdx]?.backend}/{backends[redBackendIdx]?.model}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">蓝队:</span>
                    <span className="text-team-blue ml-2">
                      {backends[blueBackendIdx]?.backend}/{backends[blueBackendIdx]?.model}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">判官:</span>
                    <span className="text-team-yellow ml-2">
                      {backends[judgeBackendIdx]?.backend}/{backends[judgeBackendIdx]?.model}
                    </span>
                  </div>
                </div>

                {selectedTarget?.code && (
                  <div>
                    <div className="text-xs text-muted-foreground mb-1">靶机代码预览:</div>
                    <pre className="text-xs text-muted-foreground font-mono bg-muted/50 rounded p-2 max-h-24 overflow-hidden">
                      {selectedTarget.code.slice(0, 300)}
                      {selectedTarget.code.length > 300 ? '\n...' : ''}
                    </pre>
                  </div>
                )}
              </div>

              {error && (
                <motion.p
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="text-xs text-semantic-error bg-red-900/20 border border-red-800 rounded px-3 py-2"
                >
                  {error}
                </motion.p>
              )}

              <div className="flex justify-between">
                <Button variant="ghost" onClick={() => setStep(2)} className="text-muted-foreground">
                  上一步
                </Button>
                <Button
                  onClick={onStart}
                  disabled={!selectedTarget || backends.length === 0 || loading}
                  className="bg-accent-cyan hover:bg-accent-cyan/80 text-background px-8"
                >
                  {loading ? '启动中...' : '▶ 启动对抗'}
                </Button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {step !== 3 && (
        <p className="text-muted-foreground/70 text-sm">点击启动开始对抗</p>
      )}
    </motion.div>
  )
}
