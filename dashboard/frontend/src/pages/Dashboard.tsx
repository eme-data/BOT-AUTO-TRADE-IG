import { useState, useEffect, useCallback } from 'react'
import { NavLink } from 'react-router-dom'
import { useApiFetch } from '../context/AuthContext'
import MetricsCards from '../components/MetricsCards'
import PositionsTable from '../components/PositionsTable'
import PnLChart from '../components/PnLChart'
import { useWebSocket } from '../hooks/useWebSocket'

interface AutoPilotStatus {
  enabled: boolean
  shadow_mode?: boolean
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

interface AIDecision {
  id: number
  epic: string
  mode: string
  verdict: string
  confidence: number
  reasoning: string
  signal_direction: string
  latency_ms: number
  created_at: string
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
  const [aiDecisions, setAiDecisions] = useState<AIDecision[]>([])

  const handleMessage = useCallback((data: { type: string; [key: string]: unknown }) => {
    if (data.type === 'position_update') fetchPositions()
  }, [])

  const { connected } = useWebSocket(handleMessage)

  const fetchMetrics = async () => {
    try { const r = await apiFetch('/api/metrics'); if (r.ok) setMetrics(await r.json()) } catch {}
  }
  const fetchPositions = async () => {
    try { const r = await apiFetch('/api/positions'); if (r.ok) setPositions(await r.json()) } catch {}
  }
  const fetchAccount = async () => {
    try { const r = await apiFetch('/api/metrics/account'); if (r.ok) setAccount(await r.json()) } catch {}
  }
  const fetchPnlHistory = async () => {
    try { const r = await apiFetch('/api/metrics/pnl-history?days=30'); if (r.ok) setPnlHistory(await r.json()) } catch {}
  }
  const fetchAutopilot = async () => {
    try { const r = await apiFetch('/api/autopilot/status'); if (r.ok) setAutopilot(await r.json()) } catch {}
  }
  const fetchActivity = async () => {
    try { const r = await apiFetch('/api/autopilot/activity'); if (r.ok) setActivity(await r.json()) } catch {}
  }
  const fetchAiDecisions = async () => {
    try { const r = await apiFetch('/api/ai/logs?limit=10'); if (r.ok) setAiDecisions(await r.json()) } catch {}
  }

  useEffect(() => {
    fetchMetrics(); fetchAccount(); fetchPositions(); fetchPnlHistory(); fetchAutopilot(); fetchActivity(); fetchAiDecisions()
    const interval = setInterval(() => { fetchMetrics(); fetchPositions(); fetchAutopilot(); fetchActivity(); fetchAiDecisions() }, 10000)
    const accountInterval = setInterval(fetchAccount, 60000)
    return () => { clearInterval(interval); clearInterval(accountInterval) }
  }, [])

  const pnlData = pnlHistory.map((p) => ({ time: p.date, value: p.cumulative_pnl }))

  return (
    <div className="space-y-6">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">Dashboard</h1>
          <div className="flex items-center gap-2 mt-1">
            <div className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-profit' : 'bg-loss'}`} />
            <span className="text-xs text-gray-500">{connected ? 'Live' : 'Disconnected'}</span>
          </div>
        </div>

        {autopilot && (
          <NavLink to="/autopilot" className="card px-4 py-2.5 hover:border-border-light transition-colors flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${
                autopilot.status === 'scanning' ? 'bg-yellow-400 animate-pulse'
                  : autopilot.enabled ? 'bg-profit' : 'bg-gray-500'
              }`} />
              <span className="text-sm font-medium text-white">Auto-Pilot</span>
              {autopilot.shadow_mode && autopilot.enabled && (
                <span className="badge-warning">Shadow</span>
              )}
              {!autopilot.shadow_mode && autopilot.enabled && (
                <span className="badge-profit">Live</span>
              )}
              {!autopilot.enabled && (
                <span className="badge-neutral">OFF</span>
              )}
            </div>
            {autopilot.enabled && (
              <div className="flex items-center gap-3 text-xs text-gray-500 border-l border-border pl-3">
                <span>{autopilot.active_markets} active</span>
                <span>{autopilot.scores.length} scored</span>
              </div>
            )}
          </NavLink>
        )}
      </div>

      {/* Active autopilot markets */}
      {autopilot?.enabled && autopilot.scores.some(s => s.is_active) && (
        <div className="card p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="section-title">Active Markets</h3>
            <NavLink to="/autopilot" className="text-xs text-accent hover:text-blue-300 transition-colors">View all</NavLink>
          </div>
          <div className="flex gap-3 flex-wrap">
            {autopilot.scores.filter(s => s.is_active).map(s => (
              <div key={s.epic} className="flex items-center gap-2.5 bg-bg-primary rounded-lg px-3 py-2 border border-border">
                <span className="text-sm font-medium text-white">{s.instrument_name || s.epic}</span>
                <span className={`text-xs font-bold ${
                  s.total_score >= 0.7 ? 'text-profit' : s.total_score >= 0.5 ? 'text-yellow-400' : 'text-gray-500'
                }`}>
                  {(s.total_score * 100).toFixed(0)}%
                </span>
                {s.selected_strategy && (
                  <span className="badge-neutral">{s.selected_strategy}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* KPI Cards */}
      <MetricsCards metrics={metrics} account={account} />

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PnLChart data={pnlData} />

        {/* Daily P&L bars */}
        {pnlHistory.length > 0 && (
          <div className="card p-4">
            <h3 className="section-title mb-4">Daily P&L (30 days)</h3>
            <div className="flex items-end gap-[3px] h-48">
              {pnlHistory.map((day, i) => {
                const maxAbs = Math.max(...pnlHistory.map((d) => Math.abs(d.daily_pnl)), 1)
                const height = (Math.abs(day.daily_pnl) / maxAbs) * 100
                const isPositive = day.daily_pnl >= 0
                return (
                  <div key={i} className="flex-1 flex flex-col items-center justify-end h-full group relative">
                    <div
                      className={`w-full min-w-[3px] rounded-sm transition-all group-hover:opacity-80 ${isPositive ? 'bg-profit' : 'bg-loss'}`}
                      style={{ height: `${Math.max(3, height)}%` }}
                    />
                    <div className="absolute bottom-full mb-2 hidden group-hover:block bg-bg-secondary border border-border rounded px-2 py-1 text-[10px] whitespace-nowrap z-10 shadow-lg">
                      <div className="text-gray-400">{day.date}</div>
                      <div className={isPositive ? 'text-profit' : 'text-loss'}>
                        {isPositive ? '+' : ''}{day.daily_pnl.toFixed(2)} ({day.trades} trades)
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {/* Open Positions */}
      <div>
        <h2 className="text-base font-semibold mb-3">Open Positions</h2>
        <PositionsTable positions={positions} />
      </div>

      {/* Auto-Pilot Logs + AI Decisions side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Auto-Pilot Logs */}
        {autopilot?.enabled && (
          <div className="card p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="section-title">Auto-Pilot Activity</h3>
              <NavLink to="/autopilot" className="text-xs text-accent hover:text-blue-300 transition-colors">Configure</NavLink>
            </div>
            {activity.length > 0 ? (
              <div className="space-y-0.5 max-h-72 overflow-y-auto font-mono text-xs">
                {activity.map((entry, i) => {
                  const levelColor = entry.level === 'ERROR' ? 'text-loss'
                    : entry.level === 'WARN' ? 'text-yellow-400'
                    : 'text-gray-500'
                  const time = new Date(entry.time).toLocaleTimeString()
                  return (
                    <div key={i} className="flex gap-2 py-0.5 hover:bg-bg-hover/50 rounded px-1 -mx-1">
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

        {/* AI Decisions */}
        {aiDecisions.length > 0 && (
          <div className="card p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="section-title">AI Decisions</h3>
              <NavLink to="/ai" className="text-xs text-accent hover:text-blue-300 transition-colors">View all</NavLink>
            </div>
            <div className="space-y-2 max-h-72 overflow-y-auto">
              {aiDecisions.map((d) => {
                const verdictColor = d.verdict === 'APPROVE' ? 'badge-profit'
                  : d.verdict === 'REJECT' ? 'badge-loss'
                  : d.verdict === 'ADJUST' ? 'badge-warning'
                  : 'badge-neutral'
                const dirColor = d.signal_direction === 'BUY' ? 'text-profit' : d.signal_direction === 'SELL' ? 'text-loss' : 'text-gray-500'
                return (
                  <div key={d.id} className="flex items-start gap-3 py-2 px-2 rounded-lg hover:bg-bg-hover/50 -mx-2">
                    <div className="shrink-0 pt-0.5">
                      <span className={verdictColor}>{d.verdict}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono text-white">{d.epic.split('.').slice(-3, -2).join('') || d.epic}</span>
                        {d.signal_direction && <span className={`text-xs font-medium ${dirColor}`}>{d.signal_direction}</span>}
                        <span className="text-[10px] text-gray-600">{d.latency_ms}ms</span>
                      </div>
                      <p className="text-xs text-gray-400 mt-0.5 truncate">{d.reasoning}</p>
                    </div>
                    <div className="text-[10px] text-gray-600 shrink-0 whitespace-nowrap">
                      {d.created_at ? new Date(d.created_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : ''}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
