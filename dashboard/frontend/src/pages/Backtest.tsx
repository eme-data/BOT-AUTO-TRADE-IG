import { useState } from 'react'
import { useApiFetch } from '../context/AuthContext'

interface BacktestSummary {
  strategy: string
  epic: string
  period: string
  initial_balance: number
  final_balance: number
  total_return_pct: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  profit_factor: number
  avg_win: number
  avg_loss: number
  max_drawdown: number
  max_drawdown_pct: number
  sharpe_ratio: number
}

interface BacktestTrade {
  entry_time: string
  exit_time: string
  direction: string
  size: number
  entry_price: number
  exit_price: number
  profit: number
  reason: string
}

interface EquityPoint {
  time: string
  equity: number
  balance: number
  drawdown: number
}

export default function Backtest() {
  const apiFetch = useApiFetch()
  const [strategy, setStrategy] = useState('macd_trend')
  const [epic, setEpic] = useState('')
  const [resolution, setResolution] = useState('HOUR')
  const [historyBars, setHistoryBars] = useState(500)
  const [initialBalance, setInitialBalance] = useState(10000)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [summary, setSummary] = useState<BacktestSummary | null>(null)
  const [trades, setTrades] = useState<BacktestTrade[]>([])
  const [equityCurve, setEquityCurve] = useState<EquityPoint[]>([])

  const runBacktest = async () => {
    if (!epic.trim()) {
      setError('Please enter an epic (e.g. IX.D.DAX.DAILY.IP)')
      return
    }
    setLoading(true)
    setError('')
    setSummary(null)
    try {
      const res = await apiFetch('/api/backtest', {
        method: 'POST',
        body: JSON.stringify({
          strategy,
          epic: epic.trim(),
          resolution,
          history_bars: historyBars,
          initial_balance: initialBalance,
        }),
      })
      if (!res.ok) {
        const err = await res.json()
        setError(err.detail || 'Backtest failed')
        return
      }
      const data = await res.json()
      setSummary(data.summary)
      setTrades(data.trades || [])
      setEquityCurve(data.equity_curve || [])
    } catch {
      setError('Network error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-white">Backtesting</h2>

      {/* Configuration */}
      <div className="card p-4">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Strategy</label>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              className="input"
            >
              <option value="macd_trend">MACD Trend</option>
              <option value="rsi_mean_reversion">RSI Mean Reversion</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Epic</label>
            <input
              type="text"
              value={epic}
              onChange={(e) => setEpic(e.target.value)}
              placeholder="IX.D.DAX.DAILY.IP"
              className="input"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Resolution</label>
            <select
              value={resolution}
              onChange={(e) => setResolution(e.target.value)}
              className="input"
            >
              <option value="MINUTE_5">5 min</option>
              <option value="MINUTE_15">15 min</option>
              <option value="HOUR">1 hour</option>
              <option value="HOUR_4">4 hours</option>
              <option value="DAY">Daily</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Bars</label>
            <input
              type="number"
              value={historyBars}
              onChange={(e) => setHistoryBars(Number(e.target.value))}
              className="input"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Balance</label>
            <input
              type="number"
              value={initialBalance}
              onChange={(e) => setInitialBalance(Number(e.target.value))}
              className="input"
            />
          </div>
        </div>
        <div className="mt-4">
          <button
            onClick={runBacktest}
            disabled={loading}
            className="btn-primary"
          >
            {loading ? 'Running...' : 'Run Backtest'}
          </button>
        </div>
        {error && <p className="mt-2 text-sm text-loss">{error}</p>}
      </div>

      {/* Results */}
      {summary && (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <SummaryCard
              label="Total Return"
              value={`${summary.total_return_pct}%`}
              positive={summary.total_return_pct >= 0}
            />
            <SummaryCard label="Win Rate" value={`${summary.win_rate}%`} positive={summary.win_rate >= 50} />
            <SummaryCard label="Profit Factor" value={`${summary.profit_factor}`} positive={summary.profit_factor >= 1} />
            <SummaryCard label="Max Drawdown" value={`${summary.max_drawdown_pct}%`} positive={false} />
            <SummaryCard label="Total Trades" value={`${summary.total_trades}`} />
            <SummaryCard label="Sharpe Ratio" value={`${summary.sharpe_ratio}`} positive={summary.sharpe_ratio > 0} />
            <SummaryCard label="Avg Win" value={`${summary.avg_win}`} positive />
            <SummaryCard label="Avg Loss" value={`${summary.avg_loss}`} positive={false} />
          </div>

          {/* Equity Curve (simple text-based) */}
          {equityCurve.length > 0 && (
            <div className="card p-4">
              <h3 className="text-sm font-medium mb-3">Equity Curve</h3>
              <div className="flex items-end gap-px h-32">
                {equityCurve
                  .filter((_, i) => i % Math.max(1, Math.floor(equityCurve.length / 100)) === 0)
                  .map((point, i) => {
                    const min = Math.min(...equityCurve.map((p) => p.equity))
                    const max = Math.max(...equityCurve.map((p) => p.equity))
                    const range = max - min || 1
                    const height = ((point.equity - min) / range) * 100
                    const isProfit = point.equity >= initialBalance
                    return (
                      <div
                        key={i}
                        className={`flex-1 min-w-[2px] rounded-t ${isProfit ? 'bg-profit' : 'bg-loss'}`}
                        style={{ height: `${Math.max(2, height)}%` }}
                        title={`${point.time}: ${point.equity}`}
                      />
                    )
                  })}
              </div>
              <div className="flex justify-between text-xs text-gray-500 mt-1">
                <span>{equityCurve[0]?.time?.slice(0, 10)}</span>
                <span>{equityCurve[equityCurve.length - 1]?.time?.slice(0, 10)}</span>
              </div>
            </div>
          )}

          {/* Trades Table */}
          {trades.length > 0 && (
            <div className="card overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-gray-500 text-xs uppercase">
                    <th className="text-left px-4 py-3">Entry</th>
                    <th className="text-left px-4 py-3">Exit</th>
                    <th className="text-left px-4 py-3">Dir</th>
                    <th className="text-right px-4 py-3">Entry Price</th>
                    <th className="text-right px-4 py-3">Exit Price</th>
                    <th className="text-right px-4 py-3">P&L</th>
                    <th className="text-left px-4 py-3">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((t, i) => (
                    <tr key={i} className="border-b border-border/50 hover:bg-bg-hover/50 transition-colors">
                      <td className="px-4 py-2 text-xs text-gray-500">{t.entry_time?.slice(0, 16)}</td>
                      <td className="px-4 py-2 text-xs text-gray-500">{t.exit_time?.slice(0, 16)}</td>
                      <td className="px-4 py-2">
                        <span className={
                          t.direction === 'BUY' ? 'badge-profit' : 'badge-loss'
                        }>
                          {t.direction}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-right">{t.entry_price}</td>
                      <td className="px-4 py-2 text-right">{t.exit_price}</td>
                      <td className={`px-4 py-2 text-right font-medium ${t.profit >= 0 ? 'text-profit' : 'text-loss'}`}>
                        {t.profit >= 0 ? '+' : ''}{t.profit}
                      </td>
                      <td className="px-4 py-2 text-xs text-gray-500">{t.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function SummaryCard({ label, value, positive }: { label: string; value: string; positive?: boolean }) {
  const color = positive === undefined ? 'text-white' : positive ? 'text-profit' : 'text-loss'
  return (
    <div className="card p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-lg font-bold ${color}`}>{value}</div>
    </div>
  )
}
