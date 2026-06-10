import { motion } from 'framer-motion'
import AnimatedNumber from './shared/AnimatedNumber'

interface ArenaHeaderProps {
  taskEnded: boolean
  connecting: boolean
  running: boolean
  statusMessage: string
  currentRound: number
  maxRounds: number
  paused: boolean
  redScore: number
  blueScore: number
  error: string
  onPauseResume: () => void
  onStop: () => void
  onReturn: () => void
  isTerminal: boolean
}

export default function ArenaHeader({
  taskEnded,
  connecting,
  running,
  statusMessage,
  currentRound,
  maxRounds,
  paused,
  redScore,
  blueScore,
  error,
  onPauseResume,
  onStop,
  onReturn,
  isTerminal,
}: ArenaHeaderProps): JSX.Element {
  return (
    <div className="flex-shrink-0 border-b border-border/50 bg-muted/60 px-4 py-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <span className="text-sm font-medium text-foreground">
            {'⚔️'} ASSEF {'竞技场'}
          </span>
          {taskEnded && (
            <span className="text-[10px] bg-muted text-muted-foreground px-2 py-0.5 rounded">
              {'已结束'}
            </span>
          )}
          <div className="flex items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full ${
                connecting ? 'bg-yellow-400 animate-pulse' : running ? 'bg-green-400 animate-pulse' : 'bg-gray-500'
              }`}
            />
            <span className="text-xs text-muted-foreground">
              {statusMessage || (connecting ? '启动中...' : running ? '运行中...' : '')}
            </span>
          </div>
          <span className="text-xs text-muted-foreground">
            {'回合'} {currentRound}/{maxRounds}
          </span>
          {paused && <span className="text-xs text-yellow-400 font-medium">{'已暂停'}</span>}
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-3 mr-4">
            <div className="text-center">
              <div className="text-[10px] text-muted-foreground uppercase">{'红队'}</div>
              <div className="text-lg font-bold font-mono">
                <AnimatedNumber value={redScore} color="#ff4444" />
              </div>
            </div>
            <div className="text-center">
              <div className="text-[10px] text-muted-foreground uppercase">{'蓝队'}</div>
              <div className="text-lg font-bold font-mono">
                <AnimatedNumber value={blueScore} color="#4488ff" />
              </div>
            </div>
          </div>

          {running && (
            <>
              <button
                onClick={onPauseResume}
                className="px-3 py-1 bg-yellow-600/80 hover:bg-yellow-500 rounded text-xs font-medium text-white transition-colors"
              >
                {paused ? '▶ 恢复' : '⏸ 暂停'}
              </button>
              <button
                onClick={onStop}
                className="px-3 py-1 bg-red-700/80 hover:bg-red-600 rounded text-xs font-medium text-white transition-colors"
              >
                {'⏹'} {'停止'}
              </button>
            </>
          )}

          {isTerminal && taskEnded && (
            <button
              onClick={onReturn}
              className="px-3 py-1 bg-muted hover:bg-muted/80 rounded text-xs font-medium text-foreground transition-colors"
            >
              {'←'} {'返回'}
            </button>
          )}
        </div>
      </div>

      {error && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mt-2 text-xs text-red-400 bg-red-900/20 border border-red-800 rounded px-3 py-2"
        >
          {error}
        </motion.p>
      )}
    </div>
  )
}
