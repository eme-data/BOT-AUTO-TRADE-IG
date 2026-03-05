import { useState, useEffect, useCallback } from 'react'
import { NavLink } from 'react-router-dom'
import { useApiFetch } from '../context/AuthContext'
import MetricsCards from '../components/MetricsCards'
import PositionsTable from '../components/PositionsTable'
import PnLChart from '../components/PnLChart'
import { useWebSocket } from '../hooks/useWebSocket'

interface AutoPilotStatus {
  enabled: boolean
  status: string
  last_scan: string | null
  active_markets: number
  scores: { epic: string; instrument_name: string; total_score: number; is_active: boolean; selected_strategy: string | null }[]
}

interface ActivityEntry {
  time: string
  level: string
  message: string
}

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
  const [autopilot, setAutopilot] = useState<AutoPilotStatus | null>(null)
  const [activity, setActivity] = useState<ActivityEntry[]>([])

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

  const fetchAutopilot = async () => {
    try {
      const res = await apiFetch('/api/autopilot/status')
      if (res.ok) setAutopilot(await res.json())
    } catch {
      // silent
    }
  }

  const fetchActivity = async () => {
    try {
      const res = await apiFetch('/api/autopilot/activity')
      if (res.ok) setActivity(await res.json())
    } catch {
      // silent
    }
  }

  useEffect(() => {
    fetchMetrics()
    fetchAccount()
    fetchPositions()
    fetchPnlHistory()
    fetchAutopilot()
    fetchActivity()
    const interval = setInterval(() => {
      fetchMetrics()
      fetchPositions()
      fetchAutopilot()
      fetchActivity()
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
      {/* Connection status + Auto-Pilot status */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div
            className={`w-2 h-2 rounded-full ${connected ? 'bg-profit' : 'bg-loss'}`}
          />
          <span className="text-xs text-gray-400">
            {connected ? 'Connected' : 'Disconnected'}
          </span>
        </div>

        {autopilot && (
          <NavLink to="/autopilot" className="flex items-center gap-3 bg-bg-card border border-gray-700 rounded-lg px-4 py-2 hover:border-gray-500 transition-colors">
            <div className="flex items-center gap-2">
              <div className={`w-2.5 h-2.5 rounded-full ${
                autopilot.status === 'scanning' ? 'bg-yellow-400 animate-pulse'
                  : autopilot.enabled ? 'bg-profit' : 'bg-gray-500'
              }`} />
              <span className="text-sm font-medium text-white">Auto-Pilot</span>
              <span className={`text-xs px-1.5 py-0.5 rounded ${
                autopilot.enabled ? 'bg-profit/20 text-profit' : 'bg-gray-600/30 text-gray-400'
              }`}>
                {autopilot.enabled ? 'ON' : 'OFF'}
              </span>
            </div>
            {autopilot.enabled && (
              <div className="flex items-center gap-3 text-xs text-gray-400 border-l border-gray-700 pl-3">
                <span>{autopilot.active_markets} active</span>
                <span>{autopilot.scores.length} scored</span>
                {autopilot.last_scan && (
                  <span>Last: {new Date(autopilot.last_scan).toLocaleTimeString()}</span>
                )}
              </div>
            )}
          </NavLink>
        )}
      </div>

      {/* Active Auto-Pilot markets summary */}
      {autopilot?.enabled && autopilot.scores.some(s => s.is_active) && (
        <div className="bg-bg-card rounded-lg border border-gray-700 p-3">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Auto-Pilot Active Markets</h3>
            <NavLink to="/autopilot" className="text-xs text-blue-400 hover:text-blue-300">View all</NavLink>
          </div>
          <div className="flex gap-3">
            {autopilot.scores.filter(s => s.is_active).map(s => (
              <div key={s.epic} className="flex items-center gap-2 bg-bg-primary rounded px-3 py-1.5">
                <span className="text-sm font-medium text-white">{s.instrument_name || s.epic}</span>
                <span className={`text-xs font-bold ${
                  s.total_score >= 0.7 ? 'text-profit' : s.total_score >= 0.5 ? 'text-yellow-400' : 'text-gray-500'
                }`}>
                  {(s.total_score * 100).toFixed(0)}
                </span>
                {s.selected_strategy && (
                  <span className="text-xs text-gray-500">{s.selected_strategy}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

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

      {/* Auto-Pilot Logs */}
      {autopilot?.enabled && (
        <div className="bg-bg-card rounded-lg border border-gray-700 p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Auto-Pilot Logs</h3>
            <NavLink to="/autopilot" className="text-xs text-blue-400 hover:text-blue-300">Configure</NavLink>
          </div>
          {activity.length > 0 ? (
            <div className="space-y-1 max-h-64 overflow-y-auto text-xs font-mono">
              {activity.map((entry, i) => {
                const levelColor = entry.level === 'ERROR' ? 'text-loss'
                  : entry.level === 'WARN' ? 'text-yellow-400'
                  : 'text-gray-400'
                const time = new Date(entry.time).toLocaleTimeString()
                return (
                  <div key={i} className="flex gap-2 py-0.5">
                    <span className="text-gray-600 shrink-0">{time}</span>
                    <span className={`shrink-0 w-10 ${levelColor}`}>{entry.level}</span>
                    <span className="text-gray-300">{entry.message}</span>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-xs text-gray-500">No activity yet. Waiting for next scan cycle...</p>
          )}
        </div>
      )}
    </div>
  )
}
