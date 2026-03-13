import { useState, useEffect } from 'react'
import { useApiFetch } from '../context/AuthContext'

interface BotStatus {
  status: string
}

export default function RiskSettings() {
  const apiFetch = useApiFetch()
  const [maxDailyLoss, setMaxDailyLoss] = useState('500')
  const [maxPositionSize, setMaxPositionSize] = useState('10')
  const [maxOpenPositions, setMaxOpenPositions] = useState('5')
  const [maxPerEpic, setMaxPerEpic] = useState('1')
  const [maxRiskPct, setMaxRiskPct] = useState('2.0')
  const [defaultStop, setDefaultStop] = useState('20')
  const [defaultLimit, setDefaultLimit] = useState('40')
  const [botStatus, setBotStatus] = useState<BotStatus>({ status: 'unknown' })
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    loadSettings()
    loadBotStatus()
  }, [])

  const loadSettings = async () => {
    try {
      const res = await apiFetch('/api/settings/risk')
      if (res.ok) {
        const data = await res.json()
        for (const s of data) {
          switch (s.key) {
            case 'bot_max_daily_loss': setMaxDailyLoss(s.value); break
            case 'bot_max_position_size': setMaxPositionSize(s.value); break
            case 'bot_max_open_positions': setMaxOpenPositions(s.value); break
            case 'bot_max_positions_per_epic': setMaxPerEpic(s.value); break
            case 'bot_max_risk_per_trade_pct': setMaxRiskPct(s.value); break
            case 'bot_default_stop_distance': setDefaultStop(s.value); break
            case 'bot_default_limit_distance': setDefaultLimit(s.value); break
          }
        }
      }
    } catch { /* */ }
  }

  const loadBotStatus = async () => {
    try {
      const res = await apiFetch('/api/bot/status')
      if (res.ok) setBotStatus(await res.json())
    } catch { /* */ }
  }

  const validate = (): string | null => {
    const checks: [string, string, number?, number?][] = [
      ['Max Daily Loss', maxDailyLoss, 0],
      ['Max Position Size', maxPositionSize, 0],
      ['Max Open Positions', maxOpenPositions, 1, 50],
      ['Max per Epic', maxPerEpic, 1, 20],
      ['Risk per Trade %', maxRiskPct, 0.1, 100],
      ['Default Stop Distance', defaultStop, 1],
      ['Default Limit Distance', defaultLimit, 1],
    ]
    for (const [label, val, min, max] of checks) {
      const n = Number(val)
      if (isNaN(n)) return `${label} must be a number`
      if (min !== undefined && n < min) return `${label} must be >= ${min}`
      if (max !== undefined && n > max) return `${label} must be <= ${max}`
    }
    return null
  }

  const handleSave = async () => {
    const err = validate()
    if (err) {
      setMessage({ type: 'error', text: err })
      return
    }
    setSaving(true)
    setMessage(null)
    try {
      const res = await apiFetch('/api/settings', {
        method: 'PUT',
        body: JSON.stringify({
          settings: {
            bot_max_daily_loss: maxDailyLoss,
            bot_max_position_size: maxPositionSize,
            bot_max_open_positions: maxOpenPositions,
            bot_max_positions_per_epic: maxPerEpic,
            bot_max_risk_per_trade_pct: maxRiskPct,
            bot_default_stop_distance: defaultStop,
            bot_default_limit_distance: defaultLimit,
          },
        }),
      })
      if (res.ok) {
        setMessage({ type: 'success', text: 'Risk settings saved. Restart bot to apply.' })
      }
    } catch (e: any) {
      setMessage({ type: 'error', text: e.message })
    } finally {
      setSaving(false)
    }
  }

  const sendBotCommand = async (command: string) => {
    setMessage(null)
    try {
      const res = await apiFetch(`/api/bot/${command}`, { method: 'POST' })
      const data = await res.json()
      if (res.ok) {
        setMessage({ type: 'success', text: data.message })
        setTimeout(loadBotStatus, 2000)
      } else {
        setMessage({ type: 'error', text: data.detail || data.message })
      }
    } catch (e: any) {
      setMessage({ type: 'error', text: e.message })
    }
  }

  const statusColor: Record<string, string> = {
    running: 'bg-profit/20 text-profit',
    starting: 'bg-yellow-500/20 text-yellow-400',
    stopped: 'bg-bg-hover text-gray-400',
    error: 'bg-loss/20 text-loss',
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <h2 className="text-xl font-semibold text-white">Risk Management & Bot Control</h2>

      {message && (
        <div
          className={`rounded-lg px-4 py-2 text-sm ${
            message.type === 'success' ? 'bg-profit/20 text-profit' : 'bg-loss/20 text-loss'
          }`}
        >
          {message.text}
        </div>
      )}

      {/* Bot Control */}
      <div className="card p-6">
        <h3 className="section-title mb-4">Bot Control</h3>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-500">Status:</span>
            <span className={`px-3 py-1 rounded-lg text-sm font-medium ${statusColor[botStatus.status] || statusColor.stopped}`}>
              {botStatus.status.toUpperCase()}
            </span>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => sendBotCommand('start')}
              disabled={botStatus.status === 'running'}
              className="btn-success disabled:opacity-30"
            >
              Start
            </button>
            <button
              onClick={() => sendBotCommand('stop')}
              disabled={botStatus.status === 'stopped'}
              className="btn-danger disabled:opacity-30"
            >
              Stop
            </button>
            <button
              onClick={() => sendBotCommand('restart')}
              className="bg-yellow-500/20 text-yellow-400 hover:bg-yellow-500/30 px-4 py-2 rounded-lg text-sm font-medium"
            >
              Restart
            </button>
          </div>
        </div>
      </div>

      {/* Risk Parameters */}
      <div className="card p-6 space-y-4">
        <h3 className="section-title mb-2">Risk Parameters</h3>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Max Daily Loss" value={maxDailyLoss} onChange={setMaxDailyLoss} suffix="EUR" />
          <Field label="Max Position Size" value={maxPositionSize} onChange={setMaxPositionSize} suffix="lots" />
          <Field label="Max Open Positions" value={maxOpenPositions} onChange={setMaxOpenPositions} />
          <Field label="Max per Epic" value={maxPerEpic} onChange={setMaxPerEpic} />
          <Field label="Risk per Trade" value={maxRiskPct} onChange={setMaxRiskPct} suffix="%" />
          <div /> {/* spacer */}
          <Field label="Default Stop Distance" value={defaultStop} onChange={setDefaultStop} suffix="pts" />
          <Field label="Default Limit Distance" value={defaultLimit} onChange={setDefaultLimit} suffix="pts" />
        </div>

        <button
          onClick={handleSave}
          disabled={saving}
          className="btn-primary mt-2"
        >
          {saving ? 'Saving...' : 'Save Risk Settings'}
        </button>
      </div>
    </div>
  )
}

function Field({
  label,
  value,
  onChange,
  suffix,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  suffix?: string
}) {
  const isInvalid = isNaN(Number(value)) || value.trim() === ''
  return (
    <div>
      <label className="block text-sm text-gray-500 mb-1">{label}</label>
      <div className="flex items-center gap-2">
        <input
          type="number"
          step="any"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={`input ${
            isInvalid ? '!border-loss focus:!border-loss' : ''
          }`}
        />
        {suffix && <span className="text-xs text-gray-500 whitespace-nowrap">{suffix}</span>}
      </div>
    </div>
  )
}
