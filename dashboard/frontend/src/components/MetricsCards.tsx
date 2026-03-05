interface Metrics {
  daily_pnl: number
  total_pnl: number
  open_positions: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  account_balance: number
}

interface AccountInfo {
  balance: number
  deposit: number
  profit_loss: number
  available: number
  currency: string
}

interface Props {
  metrics: Metrics | null
  account?: AccountInfo | null
}

function MetricCard({ label, value, subtitle, color }: { label: string; value: string; subtitle?: string; color?: string }) {
  return (
    <div className="bg-bg-card rounded-lg p-4 border border-gray-700">
      <p className="text-xs text-gray-400 uppercase tracking-wider">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${color || 'text-white'}`}>{value}</p>
      {subtitle && <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>}
    </div>
  )
}

export default function MetricsCards({ metrics, account }: Props) {
  if (!metrics) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="bg-bg-card rounded-lg p-4 border border-gray-700 animate-pulse h-20" />
        ))}
      </div>
    )
  }

  const dailyColor = metrics.daily_pnl >= 0 ? 'text-profit' : 'text-loss'
  const totalColor = metrics.total_pnl >= 0 ? 'text-profit' : 'text-loss'
  const currency = account?.currency || 'EUR'
  const balance = account?.balance ?? metrics.account_balance
  const available = account?.available

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
      <MetricCard
        label="Account Balance"
        value={`${balance.toLocaleString('fr-FR', { minimumFractionDigits: 2 })} ${currency}`}
        subtitle={available != null ? `Available: ${available.toLocaleString('fr-FR', { minimumFractionDigits: 2 })} ${currency}` : undefined}
        color="text-blue-400"
      />
      <MetricCard label="Daily P&L" value={`${metrics.daily_pnl >= 0 ? '+' : ''}${metrics.daily_pnl.toFixed(2)} ${currency}`} color={dailyColor} />
      <MetricCard label="Total P&L" value={`${metrics.total_pnl >= 0 ? '+' : ''}${metrics.total_pnl.toFixed(2)} ${currency}`} color={totalColor} />
      <MetricCard label="Open Positions" value={String(metrics.open_positions)} />
      <MetricCard label="Win Rate" value={`${metrics.win_rate.toFixed(1)}%`} color={metrics.win_rate >= 50 ? 'text-profit' : 'text-loss'} />
    </div>
  )
}
