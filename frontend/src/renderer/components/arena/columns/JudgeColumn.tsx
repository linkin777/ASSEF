import TestResultCard from '../shared/TestResultCard'

interface TestResultItem {
  id: number
  round: number
  name: string
  input: string
  expectedOutput: string
  actualOutput: string
  passed: boolean
  reason: string
}

interface JudgeColumnProps {
  judgeScript: string
  scoringRules: string
  allTestResults: TestResultItem[]
  judgeModelName: string
}

export default function JudgeColumn({
  judgeScript,
  scoringRules,
  allTestResults,
  judgeModelName,
}: JudgeColumnProps): JSX.Element {
  return (
    <div className="flex-1 min-w-[280px] flex flex-col min-h-0 rounded-lg border border-yellow-500/30 bg-background/80 overflow-hidden">
      <div className="flex-shrink-0 px-3 py-2 border-b border-yellow-500/20 flex items-center gap-2">
        <span className="w-2.5 h-2.5 rounded-full bg-[#ffaa00]" />
        <span className="text-sm font-medium text-[#ffaa00]">{'判官'}</span>
        <span className="text-[10px] text-muted-foreground ml-auto">{judgeModelName}</span>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {judgeScript && (
          <div>
            <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">{'判词脚本摘要'}</div>
            <pre className="text-[10px] text-muted-foreground font-mono bg-card/30 rounded p-2 max-h-20 overflow-hidden text-ellipsis">
              {judgeScript.slice(0, 200)}{judgeScript.length > 200 ? '...' : ''}
            </pre>
          </div>
        )}

        {scoringRules && (
          <div>
            <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">{'规则摘要'}</div>
            <div className="text-[10px] text-muted-foreground bg-card/30 rounded p-2 max-h-20 overflow-y-auto">
              {scoringRules}
            </div>
          </div>
        )}

        {allTestResults.length > 0 && (
          <div>
            <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">
              {'测试结果'} ({allTestResults.filter((t) => t.passed).length}/{allTestResults.length} {'通过'})
            </div>
            <div className="space-y-1.5">
              {allTestResults.map((test) => (
                <TestResultCard key={test.id} test={test} />
              ))}
            </div>
          </div>
        )}

        <div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">{'总结'}</div>
          <div className="text-[10px] text-muted-foreground bg-card/30 rounded p-2">
            <div>
              {'攻击成功:'} {allTestResults.filter((t) => !t.passed).length}{' '}
              {'失败:'} {allTestResults.filter((t) => t.passed).length}
            </div>
            {allTestResults.filter((t) => !t.passed).length > 0 && (
              <div className="mt-1 text-red-400/70">
                {'失败原因:'}{' '}
                {allTestResults
                  .filter((t) => !t.passed)
                  .map((t) => t.reason)
                  .filter(Boolean)
                  .slice(0, 3)
                  .join('; ')}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
