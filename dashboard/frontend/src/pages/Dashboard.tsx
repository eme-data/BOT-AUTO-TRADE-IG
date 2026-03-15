import { useState, useEffect, useCallback } from 'react'
import { NavLink } from 'react-router-dom'
import { useApiFetch } from '../context/AuthContext'
import MetricsCards from '../components/MetricsCards'
import PositionsTable from '../components/PositionsTable'
import PnLChart from '../components/PnLChart'
import { useWebSocket } from '../hooks/useWebSocket'

interface MarketScore {
  epic: string
  instrument_name: string
  total_score: number
  trend_score: number
  momentum_score: number
  volatility_score: number
  timeframe_alignment: number
  regime: string
  direction_bias: string
  selected_strategy: string | null
  sentiment_long: number | null
  sentiment_short: number | null
  is_active: boolean
  scored_at: string
}

interface AutoPilotStatus {
  enabled: boolean
  shadow_mode?: boolean
  status: string
  last_scan: string | null
  active_markets: number
  scores: MarketScore[]
  vix_level: number | null
  vix_regime: string
  vix_multiplier: number
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

interface CalendarEvent {
  name: string
  time: string
  impact: string
  currency: string
}

interface CalendarStatus {
  enabled: boolean
  paused: boolean
  paused_until: string | null
  next_event: { name: string; time: string; impact: string } | null
  total_events: number
  upcoming_events: CalendarEvent[]
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

function ScoreBar({ value, color }: { value: number; color: string }) {
  const pct = Math.round(value * 100)
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-2 bg-bg-primary rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400 w-8">{pct}%</span>
    </div>
  )
}

function scoreBarColor(value: number) {
  if (value >= 0.7) return 'bg-profit'
  if (value >= 0.5) return 'bg-yellow-400'
  return 'bg-orange-500'
}

function regimeBadge(regime: string) {
  switch (regime) {
    case 'trending': return 'badge-accent'
    case 'ranging': return 'badge-warning'
    case 'volatile': return 'badge-loss'
    default: return 'badge-neutral'
  }
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
  const [calendar, setCalendar] = useState<CalendarStatus | null>(null)

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
  const fetchCalendar = async () => {
    try { const r = await apiFetch('/api/calendar/status'); if (r.ok) setCalendar(await r.json()) } catch {}
  }

  const handleScanNow = async () => {
    try { await apiFetch('/api/autopilot/scan-now', { method: 'POST' }) } catch {}
  }

  useEffect(() => {
    fetchMetrics(); fetchAccount(); fetchPositions(); fetchPnlHistory(); fetchAutopilot(); fetchActivity(); fetchAiDecisions(); fetchCalendar()
    const interval = setInterval(() => { fetchMetrics(); fetchPositions(); fetchAutopilot(); fetchActivity(); fetchAiDecisions(); fetchCalendar() }, 10000)
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

        {/* VIX Indicator */}
        {autopilot?.vix_level != null && (
          <div className={`card px-4 py-2.5 flex items-center gap-3 ${
            autopilot.vix_regime === 'extreme' ? 'border-loss/40' :
            autopilot.vix_regime === 'elevated' ? 'border-orange-500/40' :
            autopilot.vix_regime === 'normal' ? 'border-yellow-400/40' :
            'border-profit/40'
          }`}>
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${
                autopilot.vix_regime === 'extreme' ? 'bg-loss animate-pulse' :
                autopilot.vix_regime === 'elevated' ? 'bg-orange-500' :
                autopilot.vix_regime === 'normal' ? 'bg-yellow-400' :
                'bg-profit'
              }`} />
              <span className="text-xs text-gray-500">VIX</span>
              <span className={`text-sm font-bold ${
                autopilot.vix_regime === 'extreme' ? 'text-loss' :
                autopilot.vix_regime === 'elevated' ? 'text-orange-500' :
                autopilot.vix_regime === 'normal' ? 'text-yellow-400' :
                'text-profit'
              }`}>
                {autopilot.vix_level.toFixed(1)}
              </span>
            </div>
            <div className="text-[10px] text-gray-500 border-l border-border pl-3">
              <div>{autopilot.vix_regime}</div>
              <div>sizing x{autopilot.vix_multiplier}</div>
            </div>
          </div>
        )}
      </div>

      {/* Market Ticker Strip */}
      {autopilot?.enabled && autopilot.scores.length > 0 && (
        <div className="card p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941" /></svg>
              <h3 className="text-sm font-medium text-white">Marches suivis</h3>
            </div>
            <span className="text-xs text-gray-500">{autopilot.scores.length} paires scannees</span>
          </div>
          <div className="flex gap-3 overflow-x-auto pb-1">
            {autopilot.scores.map(s => (
              <div key={s.epic} className={`flex-shrink-0 bg-bg-primary rounded-lg px-4 py-3 border ${s.is_active ? 'border-accent/40' : 'border-border'} min-w-[140px]`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-white truncate">{s.instrument_name || s.epic}</span>
                  {s.is_active && <span className="w-1.5 h-1.5 rounded-full bg-profit shrink-0" />}
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`text-lg font-bold ${
                    s.total_score >= 0.6 ? 'text-profit' : s.total_score >= 0.45 ? 'text-yellow-400' : 'text-gray-500'
                  }`}>
                    {(s.total_score * 100).toFixed(0)}%
                  </span>
                  <span className={`text-[10px] ${regimeBadge(s.regime)}`}>{s.regime}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* KPI Cards */}
      <MetricsCards metrics={metrics} account={account} />

      {/* Autopilot Analysis Table */}
      {autopilot?.enabled && autopilot.scores.length > 0 && (
        <div className="card p-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-yellow-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" /></svg>
              <h3 className="text-sm font-medium text-white">Autopilot - Analyse des tendances</h3>
              <span className="text-xs text-gray-500">{autopilot.scores.length} paires scannees · {autopilot.active_markets} actives</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">{autopilot.enabled ? 'ON' : 'OFF'}</span>
                <div className={`w-9 h-5 rounded-full ${autopilot.enabled ? 'bg-profit' : 'bg-gray-600'} flex items-center`}>
                  <div className={`w-4 h-4 bg-white rounded-full transition-transform mx-0.5 ${autopilot.enabled ? 'translate-x-4' : ''}`} />
                </div>
              </div>
              <button onClick={handleScanNow} className="bg-bg-hover hover:bg-bg-hover/80 text-white px-3 py-1.5 rounded-lg text-xs font-medium transition-colors">
                Relancer le scan
              </button>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 text-xs border-b border-border">
                  <th className="text-left py-2 px-3 font-medium">Paire</th>
                  <th className="text-left py-2 px-3 font-medium">Score</th>
                  <th className="text-left py-2 px-3 font-medium">Tendance</th>
                  <th className="text-left py-2 px-3 font-medium">Momentum</th>
                  <th className="text-left py-2 px-3 font-medium">Volatilite</th>
                  <th className="text-left py-2 px-3 font-medium">Alignement</th>
                  <th className="text-left py-2 px-3 font-medium">Sentiment</th>
                  <th className="text-left py-2 px-3 font-medium">Regime</th>
                  <th className="text-left py-2 px-3 font-medium">Direction</th>
                  <th className="text-left py-2 px-3 font-medium">Strategie</th>
                  <th className="text-left py-2 px-3 font-medium">Statut</th>
                </tr>
              </thead>
              <tbody>
                {autopilot.scores.map(s => (
                  <tr key={s.epic} className={`border-b border-border/30 hover:bg-bg-hover/30 transition-colors ${s.is_active ? 'bg-accent/5' : ''}`}>
                    <td className="py-2.5 px-3">
                      <span className="text-white font-medium">{s.instrument_name || s.epic}</span>
                    </td>
                    <td className="py-2.5 px-3">
                      <span className={`font-bold ${
                        s.total_score >= 0.6 ? 'text-profit' : s.total_score >= 0.45 ? 'text-yellow-400' : 'text-gray-500'
                      }`}>
                        {(s.total_score * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td className="py-2.5 px-3"><ScoreBar value={s.trend_score} color={scoreBarColor(s.trend_score)} /></td>
                    <td className="py-2.5 px-3"><ScoreBar value={s.momentum_score} color={scoreBarColor(s.momentum_score)} /></td>
                    <td className="py-2.5 px-3"><ScoreBar value={s.volatility_score} color={scoreBarColor(s.volatility_score)} /></td>
                    <td className="py-2.5 px-3"><ScoreBar value={s.timeframe_alignment} color={scoreBarColor(s.timeframe_alignment)} /></td>
                    <td className="py-2.5 px-3">
                      {s.sentiment_long != null && s.sentiment_long > 0 ? (
                        <div className="flex items-center gap-1.5">
                          <div className="w-16 h-2 bg-bg-primary rounded-full overflow-hidden flex">
                            <div className="h-full bg-profit rounded-l-full" style={{ width: `${s.sentiment_long}%` }} />
                            <div className="h-full bg-loss rounded-r-full" style={{ width: `${s.sentiment_short}%` }} />
                          </div>
                          <span className="text-[10px] text-gray-500">{s.sentiment_long?.toFixed(0)}L</span>
                        </div>
                      ) : (
                        <span className="text-gray-600 text-xs">---</span>
                      )}
                    </td>
                    <td className="py-2.5 px-3"><span className={regimeBadge(s.regime)}>{s.regime}</span></td>
                    <td className="py-2.5 px-3">
                      {s.direction_bias && s.direction_bias !== 'neutral' ? (
                        <span className={s.direction_bias === 'bullish' ? 'text-profit text-xs font-medium' : 'text-loss text-xs font-medium'}>
                          {s.direction_bias === 'bullish' ? 'Haussier' : 'Baissier'}
                        </span>
                      ) : (
                        <span className="text-gray-600 text-xs">---</span>
                      )}
                    </td>
                    <td className="py-2.5 px-3">
                      {s.selected_strategy ? (
                        <span className="text-xs text-gray-300 font-mono">{s.selected_strategy}</span>
                      ) : (
                        <span className="text-gray-600 text-xs">---</span>
                      )}
                    </td>
                    <td className="py-2.5 px-3">
                      {s.is_active ? (
                        <span className="badge-profit">Active</span>
                      ) : (
                        <span className="text-gray-600 text-xs">---</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

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

      {/* Economic Calendar */}
      {calendar && calendar.total_events > 0 && (
        <div className="card p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-yellow-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" /></svg>
              <h3 className="text-sm font-medium text-white">Calendrier economique</h3>
            </div>
            <div className="flex items-center gap-2">
              {calendar.paused ? (
                <span className="badge-warning">Pause active</span>
              ) : (
                <span className="badge-profit">Trading actif</span>
              )}
            </div>
          </div>
          {calendar.upcoming_events.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {calendar.upcoming_events.slice(0, 6).map((ev, i) => {
                const evDate = new Date(ev.time)
                const now = new Date()
                const diffMs = evDate.getTime() - now.getTime()
                const diffH = Math.floor(diffMs / 3600000)
                const diffM = Math.floor((diffMs % 3600000) / 60000)
                const isImminent = diffMs > 0 && diffMs < 3600000
                return (
                  <div key={i} className={`bg-bg-primary rounded-lg px-3 py-2 border ${isImminent ? 'border-yellow-400/40' : 'border-border'}`}>
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-white truncate">{ev.name}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                        ev.impact === 'high' ? 'bg-loss/15 text-loss' :
                        ev.impact === 'medium' ? 'bg-yellow-400/15 text-yellow-400' :
                        'bg-gray-500/15 text-gray-400'
                      }`}>{ev.currency}</span>
                    </div>
                    <div className="flex items-center gap-2 mt-1 text-[10px] text-gray-500">
                      <span>{evDate.toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' })}</span>
                      <span>{evDate.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</span>
                      {diffMs > 0 && (
                        <span className={isImminent ? 'text-yellow-400 font-medium' : ''}>
                          {diffH > 0 ? `${diffH}h${diffM}m` : `${diffM}min`}
                        </span>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-xs text-gray-500">Aucun evenement a venir</p>
          )}
        </div>
      )}

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
