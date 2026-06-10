import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

export default function RoundCard({
  roundNum,
  attackSuccess,
  defensePassed,
  defaultExpanded,
  children,
}: {
  roundNum: number
  attackSuccess: boolean
  defensePassed: boolean
  defaultExpanded?: boolean
  children: React.ReactNode
}): JSX.Element {
  const [expanded, setExpanded] = useState(defaultExpanded ?? false)

  return (
    <div className="rounded-lg border border-border/50 bg-background/80 overflow-hidden mb-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-card/50 transition-colors text-left"
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-muted-foreground">回合 {roundNum}</span>
          <span className="text-xs">
            {attackSuccess ? (
              <span title="攻击成功" className="text-red-400">
                {'⚔️'}{' '}
              </span>
            ) : (
              <span title="攻击被防御" className="text-blue-400">
                {'🛡️'}{' '}
              </span>
            )}
          </span>
          <span className="text-[10px] text-muted-foreground">
            {defensePassed ? (
              <span className="text-green-400">防御通过</span>
            ) : (
              <span className="text-red-400">防御失败</span>
            )}
          </span>
        </div>
        <span className="text-muted-foreground text-xs">{expanded ? '▲' : '▼'}</span>
      </button>
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-3 border-t border-border/50">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
