interface Metrics {
  daily_pnl: number
  total_pnl: number
  open_positions: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
}

interface Props {
  metrics: Metrics | null
}

function MetricCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-bg-card rounded-lg p-4 border border-gray-700">
      <p className="text-xs text-gray-400 uppercase tracking-wider">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${color || 'text-white'}`}>{value}</p>
    </div>
  )
}

export default function MetricsCards({ metrics }: Props) {
  if (!metrics) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-bg-card rounded-lg p-4 border border-gray-700 animate-pulse h-20" />
        ))}
      </div>
    )
  }

  const dailyColor = metrics.daily_pnl >= 0 ? 'text-profit' : 'text-loss'
  const totalColor = metrics.total_pnl >= 0 ? 'text-profit' : 'text-loss'

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <MetricCard label="Daily P&L" value={`${metrics.daily_pnl >= 0 ? '+' : ''}${metrics.daily_pnl.toFixed(2)}`} color={dailyColor} />
      <MetricCard label="Total P&L" value={`${metrics.total_pnl >= 0 ? '+' : ''}${metrics.total_pnl.toFixed(2)}`} color={totalColor} />
      <MetricCard label="Open Positions" value={String(metrics.open_positions)} />
      <MetricCard label="Win Rate" value={`${metrics.win_rate.toFixed(1)}%`} color={metrics.win_rate >= 50 ? 'text-profit' : 'text-loss'} />
    </div>
  )
}
