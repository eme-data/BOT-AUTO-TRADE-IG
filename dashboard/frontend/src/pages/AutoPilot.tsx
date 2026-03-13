import { useState, useEffect, useCallback } from 'react'
import { useApiFetch } from '../context/AuthContext'

interface Score {
  epic: string
  instrument_name: string
  total_score: number
  trend_score: number
  momentum_score: number
  volatility_score: number
  regime: string
  direction_bias: string
  timeframe_alignment: number
  selected_strategy: string | null
  is_active: boolean
  scored_at: string
}

interface Status {
  enabled: boolean
  shadow_mode: boolean
  status: string
  last_scan: string | null
  active_markets: number
  scores: Score[]
}

interface Config {
  enabled: boolean
  scan_interval_minutes: number
  max_active_markets: number
  min_score_threshold: number
  universe_mode: string
  search_terms: string
  api_budget_per_cycle: number
  shadow_mode: boolean
}

function ScoreBar({ value, color }: { value: number; color: string }) {
  const width = Math.round(value * 100)
  return (
    <div className="w-full bg-border rounded-full h-2">
      <div className={`h-2 rounded-full ${color}`} style={{ width: `${width}%` }} />
    </div>
  )
}

function scoreColor(score: number): string {
  if (score >= 0.7) return 'text-profit'
  if (score >= 0.5) return 'text-yellow-400'
  return 'text-gray-500'
}

function barColor(score: number): string {
  if (score >= 0.7) return 'bg-profit'
  if (score >= 0.5) return 'bg-yellow-400'
  return 'bg-gray-500'
}

function regimeBadge(regime: string) {
  const colors: Record<string, string> = {
    trending: 'badge-accent',
    ranging: 'bg-purple-600/20 text-purple-400',
    volatile: 'badge-warning',
    neutral: 'badge-neutral',
  }
  const cls = colors[regime] || colors.neutral
  const isUtility = cls.startsWith('badge-')
  return (
    <span className={isUtility ? cls : `text-xs px-2 py-0.5 rounded-full ${cls}`}>
      {regime}
    </span>
  )
}

function directionBadge(dir: string) {
  if (dir === 'bullish') return <span className="badge-profit">Bullish</span>
  if (dir === 'bearish') return <span className="badge-loss">Bearish</span>
  return <span className="badge-neutral">Neutral</span>
}

export default function AutoPilot() {
  const apiFetch = useApiFetch()
  const [status, setStatus] = useState<Status | null>(null)
  const [, setConfig] = useState<Config | null>(null)
  const [editConfig, setEditConfig] = useState<Partial<Config>>({})
  const [saving, setSaving] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const fetchStatus = useCallback(async () => {
    try {
      const res = await apiFetch('/api/autopilot/status')
      if (res.ok) setStatus(await res.json())
    } catch { /* */ }
  }, [apiFetch])

  const fetchConfig = useCallback(async () => {
    try {
      const res = await apiFetch('/api/autopilot/config')
      if (res.ok) {
        const data = await res.json()
        setConfig(data)
        setEditConfig(data)
      }
    } catch { /* */ }
  }, [apiFetch])

  useEffect(() => {
    fetchStatus()
    fetchConfig()
    const interval = setInterval(fetchStatus, 10000)
    return () => clearInterval(interval)
  }, [fetchStatus, fetchConfig])

  const handleToggle = async () => {
    const newEnabled = !status?.enabled
    try {
      const res = await apiFetch(`/api/autopilot/toggle?enabled=${newEnabled}`, { method: 'POST' })
      if (res.ok) {
        setMessage({ type: 'success', text: newEnabled ? 'Auto-Pilot enabled — scanning markets automatically...' : 'Auto-Pilot disabled' })
        setTimeout(fetchStatus, newEnabled ? 5000 : 1000)
      }
    } catch (e: any) {
      setMessage({ type: 'error', text: e.message })
    }
  }

  const handleScanNow = async () => {
    setScanning(true)
    try {
      await apiFetch('/api/autopilot/scan-now', { method: 'POST' })
      setMessage({ type: 'success', text: 'Scan triggered, results will appear shortly...' })
      setTimeout(fetchStatus, 5000)
    } catch (e: any) {
      setMessage({ type: 'error', text: e.message })
    } finally {
      setScanning(false)
    }
  }

  const handleSaveConfig = async () => {
    setSaving(true)
    setMessage(null)
    try {
      const res = await apiFetch('/api/autopilot/config', {
        method: 'PUT',
        body: JSON.stringify(editConfig),
      })
      if (res.ok) {
        setMessage({ type: 'success', text: 'Configuration saved' })
        fetchConfig()
      } else {
        const err = await res.json()
        setMessage({ type: 'error', text: err.detail || 'Save failed' })
      }
    } catch (e: any) {
      setMessage({ type: 'error', text: e.message })
    } finally {
      setSaving(false)
    }
  }

  const statusDot = status?.status === 'scanning' ? 'bg-yellow-400 animate-pulse'
    : status?.enabled ? 'bg-profit' : 'bg-gray-500'

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">Auto-Pilot</h1>
          <p className="text-sm text-gray-400 mt-1">
            Autonomous market scanning, analysis, and trading
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className={`w-2.5 h-2.5 rounded-full ${statusDot}`} />
            <span className="text-sm text-gray-400 capitalize">
              {status?.status || 'disabled'}
            </span>
          </div>
          <button
            onClick={handleToggle}
            className={status?.enabled ? 'btn-danger' : 'btn-success'}
          >
            {status?.enabled ? 'Disable' : 'Enable'} Auto-Pilot
          </button>
        </div>
      </div>

      {/* Shadow mode banner */}
      {status?.enabled && status?.shadow_mode && (
        <div className="card px-4 py-2 text-sm bg-yellow-600/20 text-yellow-400 border-yellow-600/30 flex items-center justify-between">
          <span>Shadow Mode active — signals are logged but not executed on the broker</span>
          <button
            onClick={async () => {
              await apiFetch('/api/autopilot/config', {
                method: 'PUT',
                body: JSON.stringify({ shadow_mode: false }),
              })
              fetchConfig()
              fetchStatus()
              setMessage({ type: 'success', text: 'Shadow mode disabled — trades will now be executed live!' })
            }}
            className="ml-4 bg-yellow-600 hover:bg-yellow-700 text-white px-3 py-1 rounded-lg text-xs font-medium"
          >
            Go Live
          </button>
        </div>
      )}

      {status?.enabled && !status?.shadow_mode && (
        <div className="card px-4 py-2 text-sm bg-profit/20 text-profit border-profit/30">
          Live Trading active — orders are sent to the broker
        </div>
      )}

      {message && (
        <div className={`rounded-xl px-4 py-2 text-sm ${
          message.type === 'success' ? 'bg-profit/20 text-profit' : 'bg-loss/20 text-loss'
        }`}>
          {message.text}
        </div>
      )}

      {/* Status bar */}
      {status?.enabled && (
        <div className="card p-4 flex items-center justify-between">
          <div className="flex gap-6 text-sm">
            <div>
              <span className="text-gray-400">Active markets: </span>
              <span className="text-white font-medium">{status.active_markets}</span>
            </div>
            <div>
              <span className="text-gray-400">Last scan: </span>
              <span className="text-white">
                {status.last_scan ? new Date(status.last_scan).toLocaleTimeString() : 'Never'}
              </span>
            </div>
            <div>
              <span className="text-gray-400">Markets scored: </span>
              <span className="text-white">{status.scores.length}</span>
            </div>
          </div>
          <button
            onClick={handleScanNow}
            disabled={scanning}
            className="btn-primary disabled:opacity-50"
          >
            {scanning ? 'Scanning...' : 'Scan Now'}
          </button>
        </div>
      )}

      {/* Configuration */}
      <div className="card p-6 space-y-4">
        <h2 className="section-title">Configuration</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Scan Interval (min)</label>
            <input
              type="number"
              value={editConfig.scan_interval_minutes ?? 30}
              onChange={(e) => setEditConfig({ ...editConfig, scan_interval_minutes: Number(e.target.value) })}
              className="input w-full"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Max Active Markets</label>
            <input
              type="number"
              value={editConfig.max_active_markets ?? 3}
              onChange={(e) => setEditConfig({ ...editConfig, max_active_markets: Number(e.target.value) })}
              className="input w-full"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Min Score Threshold</label>
            <input
              type="number"
              step="0.05"
              value={editConfig.min_score_threshold ?? 0.5}
              onChange={(e) => setEditConfig({ ...editConfig, min_score_threshold: Number(e.target.value) })}
              className="input w-full"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Universe Mode</label>
            <select
              value={editConfig.universe_mode ?? 'discovery'}
              onChange={(e) => setEditConfig({ ...editConfig, universe_mode: e.target.value })}
              className="input w-full"
            >
              <option value="discovery">Discovery (Recommended)</option>
              <option value="watchlist">Watchlist</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Trading Mode</label>
            <select
              value={editConfig.shadow_mode ? 'shadow' : 'live'}
              onChange={(e) => setEditConfig({ ...editConfig, shadow_mode: e.target.value === 'shadow' })}
              className={`w-full border rounded-lg px-3 py-2 text-sm ${
                editConfig.shadow_mode
                  ? 'bg-yellow-900/30 border-yellow-600/50 text-yellow-400'
                  : 'bg-profit/10 border-profit/30 text-profit'
              }`}
            >
              <option value="shadow">Shadow (Paper)</option>
              <option value="live">Live Trading</option>
            </select>
          </div>
          <div className="col-span-2">
            <label className="block text-xs text-gray-400 mb-1">Search Terms (discovery mode)</label>
            <input
              type="text"
              value={editConfig.search_terms ?? ''}
              onChange={(e) => setEditConfig({ ...editConfig, search_terms: e.target.value })}
              placeholder="EUR/USD, US 500, Gold..."
              className="input w-full"
            />
          </div>
        </div>
        <button
          onClick={handleSaveConfig}
          disabled={saving}
          className="btn-primary disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Save Configuration'}
        </button>
      </div>

      {/* Market Scores Table */}
      {status?.scores && status.scores.length > 0 && (
        <div className="card p-6">
          <h2 className="section-title mb-4">
            Market Rankings
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 text-xs uppercase border-b border-border">
                  <th className="text-left py-2 pr-4">Market</th>
                  <th className="text-right py-2 px-2">Score</th>
                  <th className="text-center py-2 px-2 w-24">Trend</th>
                  <th className="text-center py-2 px-2 w-24">Momentum</th>
                  <th className="text-center py-2 px-2 w-24">Volatility</th>
                  <th className="text-center py-2 px-2">Regime</th>
                  <th className="text-center py-2 px-2">Direction</th>
                  <th className="text-center py-2 px-2">Strategy</th>
                  <th className="text-center py-2 px-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {status.scores.map((s) => (
                  <tr key={s.epic} className={`border-b border-border/50 hover:bg-bg-hover/50 transition-colors ${s.is_active ? 'bg-blue-600/5' : ''}`}>
                    <td className="py-3 pr-4">
                      <div className="font-medium text-white">{s.instrument_name || s.epic}</div>
                      <div className="text-xs text-gray-500">{s.epic}</div>
                    </td>
                    <td className={`text-right px-2 font-bold ${scoreColor(s.total_score)}`}>
                      {(s.total_score * 100).toFixed(0)}
                    </td>
                    <td className="px-2"><ScoreBar value={s.trend_score} color={barColor(s.trend_score)} /></td>
                    <td className="px-2"><ScoreBar value={s.momentum_score} color={barColor(s.momentum_score)} /></td>
                    <td className="px-2"><ScoreBar value={s.volatility_score} color={barColor(s.volatility_score)} /></td>
                    <td className="text-center px-2">{regimeBadge(s.regime)}</td>
                    <td className="text-center px-2">{directionBadge(s.direction_bias)}</td>
                    <td className="text-center px-2 text-xs text-gray-300">
                      {s.selected_strategy || '-'}
                    </td>
                    <td className="text-center px-2">
                      {s.is_active ? (
                        <span className="badge-profit">Active</span>
                      ) : (
                        <span className="text-xs text-gray-500">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Empty state */}
      {(!status?.scores || status.scores.length === 0) && status?.enabled && (
        <div className="card p-8 text-center text-gray-400">
          <p>No market scores yet. A scan was triggered automatically and results will appear shortly.</p>
          <p className="text-xs mt-2">
            Discovery mode searches for markets automatically using the configured search terms.
          </p>
        </div>
      )}
    </div>
  )
}
