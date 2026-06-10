import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

interface DefenseDataPoint {
  round: number
  rate: number
}

export default function DefenseChart({ data }: { data: DefenseDataPoint[] }): JSX.Element {
  if (data.length === 0) {
    return (
      <div className="rounded-lg border border-border p-4 bg-card/50">
        <div className="text-sm font-medium text-muted-foreground mb-2">{'📈'} 防御率实时曲线</div>
        <div className="text-muted-foreground text-xs text-center py-6">等待数据...</div>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-border p-3 bg-card/50">
      <div className="text-sm font-medium text-muted-foreground mb-2">{'📈'} 防御率实时曲线</div>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--muted)" />
          <XAxis
            dataKey="round"
            stroke="var(--muted-foreground)"
            tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
            tickLine={false}
            label={{ value: '回合', position: 'insideBottom', offset: -4, fill: 'var(--muted-foreground)', fontSize: 10 }}
          />
          <YAxis
            stroke="var(--muted-foreground)"
            tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
            tickLine={false}
            domain={[0, 100]}
            tickFormatter={(v: number) => `${v}%`}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'var(--card)',
              border: '1px solid var(--border)',
              borderRadius: '6px',
              fontSize: '12px',
              color: 'var(--foreground)',
            }}
            formatter={(value: number) => [`${value}%`, '防御率']}
            labelFormatter={(label: number) => `回合 ${label}`}
          />
          <Line
            type="monotone"
            dataKey="rate"
            stroke="#00f0ff"
            strokeWidth={2}
            dot={{ r: 3, fill: '#00f0ff' }}
            activeDot={{ r: 5 }}
            animationDuration={500}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
