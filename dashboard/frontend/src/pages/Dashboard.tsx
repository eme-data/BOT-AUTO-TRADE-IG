import { useState, useEffect, useCallback } from 'react'
import { useApiFetch } from '../context/AuthContext'
import MetricsCards from '../components/MetricsCards'
import PositionsTable from '../components/PositionsTable'
import PnLChart from '../components/PnLChart'
import { useWebSocket } from '../hooks/useWebSocket'

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

interface Position {
  deal_id: string
  epic: string
  direction: string
  size: number
  open_level: number
  stop_level: number | null
  limit_level: number | null
  profit: number
}

interface PnLPoint {
  date: string
  daily_pnl: number
  cumulative_pnl: number
  trades: number
}

export default function Dashboard() {
  const apiFetch = useApiFetch()
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [account, setAccount] = useState<AccountInfo | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [pnlHistory, setPnlHistory] = useState<PnLPoint[]>([])

  const handleMessage = useCallback((data: { type: string; [key: string]: unknown }) => {
    if (data.type === 'tick') {
      // Could update live prices here
    } else if (data.type === 'position_update') {
      fetchPositions()
    }
  }, [])

  const { connected } = useWebSocket(handleMessage)

  const fetchMetrics = async () => {
    try {
      const res = await apiFetch('/api/metrics')
      if (res.ok) setMetrics(await res.json())
    } catch {
      // silent
    }
  }

  const fetchPositions = async () => {
    try {
      const res = await apiFetch('/api/positions')
      if (res.ok) setPositions(await res.json())
    } catch {
      // silent
    }
  }

  const fetchAccount = async () => {
    try {
      const res = await apiFetch('/api/metrics/account')
      if (res.ok) setAccount(await res.json())
    } catch {
      // silent
    }
  }

  const fetchPnlHistory = async () => {
    try {
      const res = await apiFetch('/api/metrics/pnl-history?days=30')
      if (res.ok) setPnlHistory(await res.json())
    } catch {
      // silent
    }
  }

  useEffect(() => {
    fetchMetrics()
    fetchAccount()
    fetchPositions()
    fetchPnlHistory()
    const interval = setInterval(() => {
      fetchMetrics()
      fetchPositions()
    }, 10000)
    // Refresh account balance every 60s (IG rate limits)
    const accountInterval = setInterval(fetchAccount, 60000)
    return () => { clearInterval(interval); clearInterval(accountInterval) }
  }, [])

  // Transform P&L history for the chart
  const pnlData = pnlHistory.map((p) => ({
    time: p.date,
    value: p.cumulative_pnl,
  }))

  return (
    <div className="space-y-6">
      {/* Connection status */}
      <div className="flex items-center gap-2">
        <div
          className={`w-2 h-2 rounded-full ${connected ? 'bg-profit' : 'bg-loss'}`}
        />
        <span className="text-xs text-gray-400">
          {connected ? 'Connected' : 'Disconnected'}
        </span>
      </div>

      {/* Metrics */}
      <MetricsCards metrics={metrics} account={account} />

      {/* P&L Chart */}
      <PnLChart data={pnlData} />

      {/* Daily P&L breakdown */}
      {pnlHistory.length > 0 && (
        <div className="bg-bg-card rounded-lg border border-gray-700 p-4">
          <h3 className="text-sm font-medium mb-3">Daily P&L (Last 30 days)</h3>
          <div className="flex items-end gap-1 h-24">
            {pnlHistory.map((day, i) => {
              const maxAbs = Math.max(...pnlHistory.map((d) => Math.abs(d.daily_pnl)), 1)
              const height = (Math.abs(day.daily_pnl) / maxAbs) * 100
              const isPositive = day.daily_pnl >= 0
              return (
                <div key={i} className="flex-1 flex flex-col items-center justify-end h-full">
                  <div
                    className={`w-full min-w-[3px] rounded-t ${isPositive ? 'bg-profit' : 'bg-loss'}`}
                    style={{ height: `${Math.max(2, height)}%` }}
                    title={`${day.date}: ${day.daily_pnl >= 0 ? '+' : ''}${day.daily_pnl} (${day.trades} trades)`}
                  />
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Open Positions */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Open Positions</h2>
        <PositionsTable positions={positions} />
      </div>
    </div>
  )
}
