import AgentStreamOutput from '../shared/AgentStreamOutput'

interface AttackScriptRound {
  round: number
  script: string
}

interface RoundInfo {
  round: number
  attackSuccess: boolean
}

interface RedTeamColumnProps {
  targetCodeSummary: string
  attackSuccessCriteria: string
  attackScriptRounds: AttackScriptRound[]
  redStreamText: string
  isRunning: boolean
  roundInfos: RoundInfo[]
  redModelName: string
}

export default function RedTeamColumn({
  targetCodeSummary,
  attackSuccessCriteria,
  attackScriptRounds,
  redStreamText,
  isRunning,
  roundInfos,
  redModelName,
}: RedTeamColumnProps): JSX.Element {
  return (
    <div className="flex-1 min-w-[280px] flex flex-col min-h-0 rounded-lg border border-red-500/30 bg-background/80 overflow-hidden">
      <div className="flex-shrink-0 px-3 py-2 border-b border-red-500/20 flex items-center gap-2">
        <span className="w-2.5 h-2.5 rounded-full bg-[#ff4444]" />
        <span className="text-sm font-medium text-[#ff4444]">{'红队'} {'攻击者'}</span>
        <span className="text-[10px] text-muted-foreground ml-auto">{redModelName}</span>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {targetCodeSummary && (
          <div>
            <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">{'靶机代码摘要'}</div>
            <pre className="text-[10px] text-muted-foreground font-mono bg-muted rounded p-2 max-h-24 overflow-hidden line-clamp-6">
              {targetCodeSummary}
            </pre>
          </div>
        )}

        {attackSuccessCriteria && (
          <div>
            <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">{'攻击判定标准'}</div>
            <div className="text-[10px] text-muted-foreground bg-card/30 rounded p-2 max-h-24 overflow-y-auto">
              {attackSuccessCriteria}
            </div>
          </div>
        )}

        {attackScriptRounds.length > 0 && (
          <div>
            <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">{'攻击脚本历史'}</div>
            <div className="space-y-2">
              {attackScriptRounds.map((asr, roundIdx) => (
                <div key={roundIdx}>
                  <div className="text-[10px] text-[#ff4444] font-medium bg-red-900/20 px-2 py-0.5 rounded mb-1">
                    {'第'}{asr.round}{'回合'}
                  </div>
                  <div className="bg-card/40 rounded p-2 border border-red-500/10">
                    <pre className="text-[10px] text-foreground font-mono whitespace-pre-wrap break-all max-h-48 overflow-y-auto leading-relaxed bg-muted rounded p-1.5">
                      {asr.script}
                    </pre>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">{'LLM 原始输出'}</div>
          <div className="bg-muted rounded p-2 max-h-48 overflow-y-auto">
            {redStreamText ? (
              <AgentStreamOutput fullText={redStreamText} isActive={isRunning} />
            ) : (
              <div className="text-[10px] text-muted-foreground/70">{'等待输出...'}</div>
            )}
          </div>
        </div>

        {roundInfos.length > 0 && (
          <div>
            <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">{'多回合策略链'}</div>
            <div className="space-y-1">
              {roundInfos.map((ri) => (
                <div key={ri.round} className="text-[10px] text-muted-foreground bg-card/30 rounded px-2 py-1">
                  {'基于第'}{ri.round}{'回合反馈调整策略'}
                  {ri.attackSuccess && <span className="text-red-400 ml-2">{'⚔️ 突破'}</span>}
                  {!ri.attackSuccess && <span className="text-blue-400 ml-2">{'🛡️ 被防御'}</span>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
