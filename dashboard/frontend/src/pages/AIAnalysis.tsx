import { useState, useEffect, useCallback } from 'react'
import { useApiFetch } from '../context/AuthContext'

interface AILog {
  id: number
  epic: string
  mode: string
  verdict: string
  confidence: number
  reasoning: string
  market_summary: string
  risk_warnings: string[]
  suggested_adjustments: Record<string, unknown>
  signal_direction: string
  signal_strategy: string
  model_used: string
  latency_ms: number
  created_at: string
}

interface AIStats {
  total: number
  approvals: number
  rejections: number
  adjustments: number
  avg_latency_ms: number
  avg_confidence: number
}

interface AIStatus {
  enabled: boolean
  configured: boolean
  model: string
  modes: {
    pre_trade: boolean
    market_review: boolean
    sentiment: boolean
    post_trade: boolean
  }
}

function verdictBadge(verdict: string) {
  switch (verdict) {
    case 'APPROVE': return 'badge-profit'
    case 'REJECT': return 'badge-loss'
    case 'ADJUST': return 'badge-warning'
    default: return 'badge-neutral'
  }
}

function modeBadge(mode: string) {
  switch (mode) {
    case 'pre_trade': return 'badge-accent'
    case 'post_trade': return 'badge-neutral'
    case 'market_review': return 'badge-warning'
    default: return 'badge-neutral'
  }
}

function modeLabel(mode: string) {
  switch (mode) {
    case 'pre_trade': return 'Pre-Trade'
    case 'post_trade': return 'Post-Trade'
    case 'market_review': return 'Market Review'
    case 'sentiment': return 'Sentiment'
    default: return mode
  }
}

export default function AIAnalysis() {
  const apiFetch = useApiFetch()
  const [status, setStatus] = useState<AIStatus | null>(null)
  const [logs, setLogs] = useState<AILog[]>([])
  const [stats, setStats] = useState<AIStats | null>(null)
  const [selectedLog, setSelectedLog] = useState<AILog | null>(null)
  const [modeFilter, setModeFilter] = useState<string>('all')
  const [analyzeEpic, setAnalyzeEpic] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeResult, setAnalyzeResult] = useState<Record<string, unknown> | null>(null)

  const fetchStatus = useCallback(async () => {
    try {
      const res = await apiFetch('/api/ai/status')
      if (res.ok) setStatus(await res.json())
    } catch { /* ignore */ }
  }, [apiFetch])

  const fetchLogs = useCallback(async () => {
    try {
      const res = await apiFetch('/api/ai/logs?limit=100')
      if (res.ok) setLogs(await res.json())
    } catch { /* ignore */ }
  }, [apiFetch])

  const fetchStats = useCallback(async () => {
    try {
      const res = await apiFetch('/api/ai/stats')
      if (res.ok) setStats(await res.json())
    } catch { /* ignore */ }
  }, [apiFetch])

  useEffect(() => {
    fetchStatus()
    fetchLogs()
    fetchStats()
    const interval = setInterval(() => { fetchLogs(); fetchStats() }, 30000)
    return () => clearInterval(interval)
  }, [fetchStatus, fetchLogs, fetchStats])

  const handleAnalyze = async () => {
    if (!analyzeEpic.trim()) return
    setAnalyzing(true)
    setAnalyzeResult(null)
    try {
      const res = await apiFetch('/api/ai/analyze', {
        method: 'POST',
        body: JSON.stringify({ epic: analyzeEpic.trim(), mode: 'market_review' }),
      })
      if (res.ok) {
        const data = await res.json()
        setAnalyzeResult(data)
        fetchLogs()
        fetchStats()
      }
    } catch { /* ignore */ }
    setAnalyzing(false)
  }

  const filteredLogs = modeFilter === 'all'
    ? logs
    : logs.filter(l => l.mode === modeFilter)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">AI Analysis</h1>
          <p className="text-sm text-gray-500 mt-1">Analyse Claude des signaux de trading</p>
        </div>
        {status && (
          <div className="flex items-center gap-3">
            <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium ${status.enabled && status.configured ? 'bg-profit/15 text-profit' : 'bg-loss/15 text-loss'}`}>
              <span className={`w-2 h-2 rounded-full ${status.enabled && status.configured ? 'bg-profit animate-pulse' : 'bg-loss'}`} />
              {status.enabled && status.configured ? 'AI Active' : 'AI Inactive'}
            </span>
            <span className="text-xs text-gray-500">{status.model}</span>
          </div>
        )}
      </div>

      {/* Stats cards */}
      {stats && stats.total > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="card p-4">
            <div className="text-xs text-gray-500">Total Analyses</div>
            <div className="text-2xl font-bold text-white mt-1">{stats.total}</div>
          </div>
          <div className="card p-4">
            <div className="text-xs text-gray-500">Approves</div>
            <div className="text-2xl font-bold text-profit mt-1">{stats.approvals}</div>
            <div className="text-xs text-gray-500">{stats.total > 0 ? ((stats.approvals / stats.total) * 100).toFixed(0) : 0}%</div>
          </div>
          <div className="card p-4">
            <div className="text-xs text-gray-500">Rejections</div>
            <div className="text-2xl font-bold text-loss mt-1">{stats.rejections}</div>
            <div className="text-xs text-gray-500">{stats.total > 0 ? ((stats.rejections / stats.total) * 100).toFixed(0) : 0}%</div>
          </div>
          <div className="card p-4">
            <div className="text-xs text-gray-500">Adjustments</div>
            <div className="text-2xl font-bold text-yellow-400 mt-1">{stats.adjustments}</div>
          </div>
          <div className="card p-4">
            <div className="text-xs text-gray-500">Avg Latency</div>
            <div className="text-2xl font-bold text-white mt-1">{stats.avg_latency_ms}ms</div>
            <div className="text-xs text-gray-500">Confidence: {(stats.avg_confidence * 100).toFixed(0)}%</div>
          </div>
        </div>
      )}

      {/* Manual analysis */}
      <div className="card p-5">
        <h2 className="section-title mb-3">Analyse manuelle</h2>
        <div className="flex gap-3">
          <input
            className="input max-w-xs"
            placeholder="Epic (ex: CS.D.EURUSD.CFD.IP)"
            value={analyzeEpic}
            onChange={e => setAnalyzeEpic(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAnalyze()}
          />
          <button
            className="btn-primary disabled:opacity-50"
            onClick={handleAnalyze}
            disabled={analyzing || !analyzeEpic.trim()}
          >
            {analyzing ? 'Analyse en cours...' : 'Analyser'}
          </button>
        </div>
        {analyzeResult && (
          <div className="mt-4 p-4 bg-bg-primary rounded-lg border border-border">
            {'error' in analyzeResult ? (
              <p className="text-loss text-sm">{String(analyzeResult.error)}</p>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <span className={verdictBadge(String(analyzeResult.verdict))}>{String(analyzeResult.verdict)}</span>
                  <span className="text-sm text-gray-400">Confidence: {((analyzeResult.confidence as number) * 100).toFixed(0)}%</span>
                  <span className="text-xs text-gray-500">{String(analyzeResult.latency_ms)}ms</span>
                </div>
                <p className="text-sm text-gray-300">{String(analyzeResult.reasoning)}</p>
                {typeof analyzeResult.market_summary === 'string' && analyzeResult.market_summary && (
                  <p className="text-xs text-gray-500 italic">{analyzeResult.market_summary}</p>
                )}
                {(analyzeResult.risk_warnings as string[])?.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {(analyzeResult.risk_warnings as string[]).map((w, i) => (
                      <span key={i} className="badge-warning text-[10px]">{w}</span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Filter + Logs table */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="section-title">Historique des analyses</h2>
          <div className="flex gap-2">
            {['all', 'pre_trade', 'market_review', 'post_trade'].map(m => (
              <button
                key={m}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${modeFilter === m ? 'bg-accent text-white' : 'bg-bg-primary text-gray-400 hover:text-white'}`}
                onClick={() => setModeFilter(m)}
              >
                {m === 'all' ? 'Tout' : modeLabel(m)}
              </button>
            ))}
          </div>
        </div>

        {filteredLogs.length === 0 ? (
          <p className="text-center text-gray-500 py-8 text-sm">Aucune analyse IA pour le moment</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 text-xs border-b border-border">
                  <th className="text-left py-2 px-3 font-medium">Date</th>
                  <th className="text-left py-2 px-3 font-medium">Mode</th>
                  <th className="text-left py-2 px-3 font-medium">Marche</th>
                  <th className="text-left py-2 px-3 font-medium">Direction</th>
                  <th className="text-left py-2 px-3 font-medium">Verdict</th>
                  <th className="text-left py-2 px-3 font-medium">Confidence</th>
                  <th className="text-left py-2 px-3 font-medium">Latence</th>
                  <th className="text-left py-2 px-3 font-medium">Raisonnement</th>
                </tr>
              </thead>
              <tbody>
                {filteredLogs.map(log => (
                  <tr
                    key={log.id}
                    className="border-b border-border/50 hover:bg-bg-hover/50 cursor-pointer transition-colors"
                    onClick={() => setSelectedLog(selectedLog?.id === log.id ? null : log)}
                  >
                    <td className="py-2 px-3 text-gray-400 whitespace-nowrap">
                      {log.created_at ? new Date(log.created_at).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-'}
                    </td>
                    <td className="py-2 px-3"><span className={modeBadge(log.mode)}>{modeLabel(log.mode)}</span></td>
                    <td className="py-2 px-3 text-white font-mono text-xs">{log.epic}</td>
                    <td className="py-2 px-3">
                      {log.signal_direction && (
                        <span className={log.signal_direction === 'BUY' ? 'text-profit' : 'text-loss'}>{log.signal_direction}</span>
                      )}
                    </td>
                    <td className="py-2 px-3"><span className={verdictBadge(log.verdict)}>{log.verdict}</span></td>
                    <td className="py-2 px-3 text-gray-300">{(log.confidence * 100).toFixed(0)}%</td>
                    <td className="py-2 px-3 text-gray-500">{log.latency_ms}ms</td>
                    <td className="py-2 px-3 text-gray-400 max-w-xs truncate">{log.reasoning}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Detail panel */}
      {selectedLog && (
        <div className="card p-5 animate-fade-in">
          <div className="flex items-center justify-between mb-4">
            <h2 className="section-title">Detail de l'analyse #{selectedLog.id}</h2>
            <button className="text-gray-500 hover:text-white text-sm" onClick={() => setSelectedLog(null)}>Fermer</button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-3">
              <div>
                <span className="text-xs text-gray-500">Marche</span>
                <p className="text-white font-mono">{selectedLog.epic}</p>
              </div>
              <div>
                <span className="text-xs text-gray-500">Strategie</span>
                <p className="text-white">{selectedLog.signal_strategy || 'N/A'}</p>
              </div>
              <div>
                <span className="text-xs text-gray-500">Direction</span>
                <p className={selectedLog.signal_direction === 'BUY' ? 'text-profit font-medium' : 'text-loss font-medium'}>
                  {selectedLog.signal_direction || 'N/A'}
                </p>
              </div>
              <div>
                <span className="text-xs text-gray-500">Modele</span>
                <p className="text-gray-400 text-sm">{selectedLog.model_used}</p>
              </div>
            </div>
            <div className="space-y-3">
              <div>
                <span className="text-xs text-gray-500">Raisonnement</span>
                <p className="text-gray-300 text-sm">{selectedLog.reasoning}</p>
              </div>
              {selectedLog.market_summary && (
                <div>
                  <span className="text-xs text-gray-500">Resume marche</span>
                  <p className="text-gray-400 text-sm italic">{selectedLog.market_summary}</p>
                </div>
              )}
              {selectedLog.risk_warnings && selectedLog.risk_warnings.length > 0 && (
                <div>
                  <span className="text-xs text-gray-500">Alertes</span>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {selectedLog.risk_warnings.map((w, i) => (
                      <span key={i} className="badge-warning">{w}</span>
                    ))}
                  </div>
                </div>
              )}
              {selectedLog.suggested_adjustments && Object.keys(selectedLog.suggested_adjustments).length > 0 && (
                <div>
                  <span className="text-xs text-gray-500">Ajustements suggeres</span>
                  <pre className="text-xs text-gray-400 mt-1 bg-bg-primary p-2 rounded">
                    {JSON.stringify(selectedLog.suggested_adjustments, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* AI modes status */}
      {status && (
        <div className="card p-5">
          <h2 className="section-title mb-3">Modes actifs</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(status.modes).map(([mode, enabled]) => (
              <div key={mode} className={`p-3 rounded-lg border ${enabled ? 'border-profit/30 bg-profit/5' : 'border-border bg-bg-primary'}`}>
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${enabled ? 'bg-profit' : 'bg-gray-600'}`} />
                  <span className="text-sm text-white">{modeLabel(mode)}</span>
                </div>
                <p className="text-xs text-gray-500 mt-1">{enabled ? 'Active' : 'Desactive'}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
