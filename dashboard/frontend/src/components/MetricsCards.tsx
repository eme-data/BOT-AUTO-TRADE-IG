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

function MetricCard({ label, value, subtitle, color }: {
  label: string; value: string; subtitle?: string; color?: string
}) {
  return (
    <div className="card p-4 hover:border-border-light transition-colors">
      <p className="section-title text-[11px]">{label}</p>
      <p className={`text-xl font-semibold mt-1.5 tracking-tight ${color || 'text-white'}`}>{value}</p>
      {subtitle && <p className="text-[11px] text-gray-500 mt-1">{subtitle}</p>}
    </div>
  )
}

export default function MetricsCards({ metrics, account }: Props) {
  if (!metrics) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="card p-4 animate-pulse">
            <div className="h-3 bg-gray-700 rounded w-20 mb-3" />
            <div className="h-6 bg-gray-700 rounded w-28" />
          </div>
        ))}
      </div>
    )
  }

  const dailyColor = metrics.daily_pnl >= 0 ? 'text-profit' : 'text-loss'
  const totalColor = metrics.total_pnl >= 0 ? 'text-profit' : 'text-loss'
  const currency = account?.currency || 'EUR'
  const balance = account?.balance ?? metrics.account_balance
  const available = account?.available
  const fmt = (n: number) => n.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const sign = (n: number) => n >= 0 ? '+' : ''

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      <MetricCard
        label="Balance"
        value={`${fmt(balance)} ${currency}`}
        subtitle={available != null ? `Available: ${fmt(available)} ${currency}` : undefined}
        color="text-accent"
      />
      <MetricCard
        label="Daily P&L"
        value={`${sign(metrics.daily_pnl)}${fmt(metrics.daily_pnl)} ${currency}`}
        color={dailyColor}
      />
      <MetricCard
        label="Total P&L"
        value={`${sign(metrics.total_pnl)}${fmt(metrics.total_pnl)} ${currency}`}
        color={totalColor}
      />
      <MetricCard
        label="Positions"
        value={String(metrics.open_positions)}
        subtitle={`${metrics.total_trades} total trades`}
      />
      <MetricCard
        label="Win Rate"
        value={`${metrics.win_rate.toFixed(1)}%`}
        subtitle={`${metrics.winning_trades}W / ${metrics.losing_trades}L`}
        color={metrics.win_rate >= 50 ? 'text-profit' : metrics.win_rate > 0 ? 'text-loss' : 'text-gray-400'}
      />
    </div>
  )
}
