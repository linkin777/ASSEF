import AgentStreamOutput from '../shared/AgentStreamOutput'
import DefenseChart from '../shared/DefenseChart'
import RoundCard from '../shared/RoundCard'

interface CodeVersion {
  round: number
  code: string
  timestamp: number
}

interface RoundInfo {
  round: number
  attackSuccess: boolean
  defensePassed: boolean
  attackScript: string
  testResults: { passed: boolean; name: string }[]
  fixedCode: string
  scoreRed: number
  scoreBlue: number
  blueIterations: number
  blueMode: 'fix' | 'enhance' | ''
  costScore: number
}

interface TestResultItem {
  round: number
  passed: boolean
}

interface DefenseDataPoint {
  round: number
  rate: number
}

interface BlueTeamColumnProps {
  blueStreamText: string
  isRunning: boolean
  fixedCodeVersions: CodeVersion[]
  roundInfos: RoundInfo[]
  allTestResults: TestResultItem[]
  latestFixedCode: string
  redScore: number
  blueScore: number
  defenseData: DefenseDataPoint[]
  blueModelName: string
}

function formatTime(ts: number): string {
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function BlueTeamColumn({
  blueStreamText,
  isRunning,
  fixedCodeVersions,
  roundInfos,
  allTestResults,
  latestFixedCode,
  redScore,
  blueScore,
  defenseData,
  blueModelName,
}: BlueTeamColumnProps): JSX.Element {
  return (
    <div className="flex-1 min-w-[280px] flex flex-col min-h-0 rounded-lg border border-blue-500/30 bg-background/80 overflow-hidden">
      <div className="flex-shrink-0 px-3 py-2 border-b border-blue-500/20 flex items-center gap-2">
        <span className="w-2.5 h-2.5 rounded-full bg-[#4488ff]" />
        <span className="text-sm font-medium text-[#4488ff]">{'蓝队'} {'防御者'}</span>
        <span className="text-[10px] text-muted-foreground ml-auto">{blueModelName}</span>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        <div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">{'收到的攻击报告'}</div>
          <div className="bg-muted rounded p-2 max-h-32 overflow-y-auto">
            {blueStreamText ? (
              <AgentStreamOutput fullText={blueStreamText} isActive={isRunning} />
            ) : (
              <div className="text-[10px] text-muted-foreground/70">{'等待攻击报告...'}</div>
            )}
          </div>
        </div>

        {fixedCodeVersions.length > 0 && (
          <div>
            <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">{'自我迭代修复'}</div>
            <div className="space-y-1.5">
              {fixedCodeVersions.map((v, i) => {
                const ri = roundInfos.find((r) => r.round === v.round)
                const modeLabel = ri?.blueMode === 'fix' ? '修复' : ri?.blueMode === 'enhance' ? '增强' : ''
                const roundTests = allTestResults.filter((t) => t.round === v.round)
                const allPassed = roundTests.length > 0 && roundTests.every((t) => t.passed)
                return (
                  <div key={i} className="bg-card/40 rounded p-2 border border-blue-500/10">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] text-muted-foreground">
                        {'回合'} {v.round}
                        {ri && (
                          <span className="text-[#4488ff] ml-1">
                            ({ri.blueIterations} {'次迭代'})
                          </span>
                        )}
                        {modeLabel && (
                          <span className={`ml-1 px-1 py-0.5 rounded text-[9px] ${
                            ri?.blueMode === 'enhance' ? 'bg-purple-900/40 text-purple-300' : 'bg-blue-900/40 text-blue-300'
                          }`}>
                            {modeLabel}
                          </span>
                        )}
                      </span>
                      <span className="text-[10px] text-muted-foreground">{formatTime(v.timestamp)}</span>
                    </div>
                    <pre className="text-[10px] text-foreground font-mono bg-muted rounded p-1.5 max-h-20 overflow-hidden">
                      {v.code.slice(0, 150)}{v.code.length > 150 ? '...' : ''}
                    </pre>
                    {roundTests.length > 0 && (
                      <div className="mt-1 text-[10px]">
                        <span className={allPassed ? 'text-green-400' : 'text-red-400'}>
                          {allPassed ? '✅ 通过' : '❌ 失败'}
                        </span>
                        <span className="text-muted-foreground ml-1">
                          ({roundTests.filter((t) => t.passed).length}/{roundTests.length})
                        </span>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {latestFixedCode && (
          <div>
            <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">{'最终修复代码'}</div>
            <pre className="text-[10px] text-green-300 font-mono bg-muted rounded p-2 max-h-40 overflow-y-auto leading-relaxed">
              {latestFixedCode}
            </pre>
          </div>
        )}

        <div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">{'3-D 评估结果'}</div>
          <div className="flex gap-3 bg-card/30 rounded p-2">
            <div className="flex flex-col items-center flex-1">
              <div
                className={`w-3 h-3 rounded-full mb-1 ${
                  redScore > blueScore ? 'bg-red-500' : 'bg-muted/80'
                }`}
              />
              <span className="text-[9px] text-muted-foreground">{'红灯'}</span>
            </div>
            <div className="flex flex-col items-center flex-1">
              <div
                className={`w-3 h-3 rounded-full mb-1 ${
                  redScore === blueScore && redScore > 0 ? 'bg-yellow-500' : 'bg-muted/80'
                }`}
              />
              <span className="text-[9px] text-muted-foreground">{'黄灯'}</span>
            </div>
            <div className="flex flex-col items-center flex-1">
              <div
                className={`w-3 h-3 rounded-full mb-1 ${
                  blueScore > redScore ? 'bg-green-500' : 'bg-muted/80'
                }`}
              />
              <span className="text-[9px] text-muted-foreground">{'绿灯'}</span>
            </div>
            <div className="flex flex-col items-center flex-1">
              <span className="text-xs font-mono font-bold text-foreground">
                {roundInfos.reduce((sum, ri) => sum + ri.costScore, 0) || '-'}
              </span>
              <span className="text-[9px] text-muted-foreground">{'成本分'}</span>
            </div>
          </div>
        </div>

        <DefenseChart data={defenseData} />

        <div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">{'回合记录'}</div>
          {roundInfos.length === 0 ? (
            <div className="text-[10px] text-muted-foreground/70">{'等待回合数据...'}</div>
          ) : (
            roundInfos.map((ri) => (
              <RoundCard
                key={ri.round}
                roundNum={ri.round}
                attackSuccess={ri.attackSuccess}
                defensePassed={ri.defensePassed}
              >
                <div className="space-y-2 pt-1">
                  <div className="flex gap-4 text-[10px] flex-wrap">
                    <span className="text-red-400">{'红队'} {ri.scoreRed}</span>
                    <span className="text-blue-400">{'蓝队'} {ri.scoreBlue}</span>
                    {ri.blueIterations > 0 && (
                      <span className="text-[#4488ff]/70">{'蓝队迭代'}: {ri.blueIterations}{'次'}</span>
                    )}
                    {ri.blueMode && (
                      <span className={ri.blueMode === 'enhance' ? 'text-purple-400' : 'text-blue-400'}>
                        {'模式'}: {ri.blueMode === 'fix' ? '修复' : '增强'}
                      </span>
                    )}
                    {ri.costScore > 0 && (
                      <span className="text-yellow-400">{'成本分'}: {ri.costScore}</span>
                    )}
                  </div>
                  {ri.attackScript && (
                    <div>
                      <div className="text-[10px] text-[#ff4444]/70 mb-1">{'攻击脚本'}</div>
                      <pre className="text-[10px] text-muted-foreground font-mono bg-muted rounded p-1.5 max-h-24 overflow-hidden">
                        {ri.attackScript.slice(0, 120)}
                      </pre>
                    </div>
                  )}
                  {ri.testResults.length > 0 && (
                    <div className="text-[10px] text-muted-foreground">
                      {'测试:'}{' '}
                      {ri.testResults.map((t, ti) => (
                        <span key={ti} className="mr-1">
                          {t.passed ? '✅' : '❌'} {t.name}
                        </span>
                      ))}
                    </div>
                  )}
                  {ri.fixedCode && (
                    <pre className="text-[10px] text-green-300/70 font-mono bg-muted rounded p-1.5 max-h-24 overflow-hidden">
                      {ri.fixedCode.slice(0, 120)}
                    </pre>
                  )}
                </div>
              </RoundCard>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
