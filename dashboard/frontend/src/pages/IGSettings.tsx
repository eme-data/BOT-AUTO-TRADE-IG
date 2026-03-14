import { useState, useEffect } from 'react'
import { useApiFetch } from '../context/AuthContext'

interface Account {
  accountId: string
  accountName: string
  accountType: string
  currency: string
  balance: number
  preferred: boolean
}

export default function IGSettings() {
  const apiFetch = useApiFetch()
  const [apiKey, setApiKey] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [accType, setAccType] = useState('DEMO')
  const [accNumber, setAccNumber] = useState('')
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [configured, setConfigured] = useState(false)

  // AI Settings
  const [aiEnabled, setAiEnabled] = useState(false)
  const [aiApiKey, setAiApiKey] = useState('')
  const [aiModel, setAiModel] = useState('claude-sonnet-4-6')
  const [aiPreTrade, setAiPreTrade] = useState(true)
  const [aiMarketReview, setAiMarketReview] = useState(true)
  const [aiPostTrade, setAiPostTrade] = useState(true)
  const [aiConfigured, setAiConfigured] = useState(false)
  const [savingAi, setSavingAi] = useState(false)

  useEffect(() => {
    loadSettings()
    loadAiSettings()
  }, [])

  const loadSettings = async () => {
    try {
      const res = await apiFetch('/api/settings/ig')
      if (res.ok) {
        const data = await res.json()
        for (const s of data) {
          if (s.key === 'ig_api_key') setConfigured(s.value !== '')
          if (s.key === 'ig_acc_type') setAccType(s.value || 'DEMO')
          if (s.key === 'ig_acc_number') setAccNumber(s.value || '')
        }
      }
    } catch { /* */ }
  }

  const loadAiSettings = async () => {
    try {
      const res = await apiFetch('/api/settings/ai')
      if (res.ok) {
        const data = await res.json()
        for (const s of data) {
          if (s.key === 'ai_enabled') setAiEnabled(s.value === 'true')
          if (s.key === 'ai_api_key') setAiConfigured(s.value !== '' && s.value !== '***configured***' ? true : s.encrypted && s.value !== '')
          if (s.key === 'ai_model') setAiModel(s.value || 'claude-sonnet-4-6')
          if (s.key === 'ai_pre_trade_enabled') setAiPreTrade(s.value === 'true')
          if (s.key === 'ai_market_review_enabled') setAiMarketReview(s.value === 'true')
          if (s.key === 'ai_post_trade_enabled') setAiPostTrade(s.value === 'true')
        }
      }
    } catch { /* */ }
  }

  const handleSaveAi = async () => {
    setSavingAi(true)
    setMessage(null)
    try {
      const settingsToSave: Record<string, string> = {
        ai_enabled: aiEnabled ? 'true' : 'false',
        ai_model: aiModel,
        ai_pre_trade_enabled: aiPreTrade ? 'true' : 'false',
        ai_market_review_enabled: aiMarketReview ? 'true' : 'false',
        ai_post_trade_enabled: aiPostTrade ? 'true' : 'false',
      }
      if (aiApiKey) settingsToSave.ai_api_key = aiApiKey

      const res = await apiFetch('/api/settings', {
        method: 'PUT',
        body: JSON.stringify({ settings: settingsToSave }),
      })
      if (res.ok) {
        setMessage({ type: 'success', text: 'AI settings saved. Restart the bot to apply.' })
        if (aiApiKey) { setAiConfigured(true); setAiApiKey('') }
      } else {
        const err = await res.json()
        setMessage({ type: 'error', text: err.detail || 'Save failed' })
      }
    } catch (e: any) {
      setMessage({ type: 'error', text: e.message })
    } finally {
      setSavingAi(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setMessage(null)
    try {
      const settingsToSave: Record<string, string> = {
        ig_acc_type: accType,
        ig_acc_number: accNumber,
      }
      // Only update credentials if user entered new values
      if (apiKey) settingsToSave.ig_api_key = apiKey
      if (username) settingsToSave.ig_username = username
      if (password) settingsToSave.ig_password = password

      const res = await apiFetch('/api/settings', {
        method: 'PUT',
        body: JSON.stringify({ settings: settingsToSave }),
      })
      if (res.ok) {
        setMessage({ type: 'success', text: 'Settings saved successfully' })
        setConfigured(true)
        // Clear sensitive fields
        setApiKey('')
        setUsername('')
        setPassword('')
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

  const handleTest = async () => {
    setTesting(true)
    setMessage(null)
    setAccounts([])
    try {
      const res = await apiFetch('/api/settings/ig/test', {
        method: 'POST',
        body: JSON.stringify({
          api_key: apiKey,
          username: username,
          password: password,
          acc_type: accType,
        }),
      })
      const data = await res.json()
      if (data.success) {
        setMessage({ type: 'success', text: data.message })
        setAccounts(data.accounts || [])
      } else {
        setMessage({ type: 'error', text: data.message })
      }
    } catch (e: any) {
      setMessage({ type: 'error', text: e.message })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <h2 className="text-xl font-semibold text-white">IG Markets Account</h2>

      {message && (
        <div
          className={`rounded-lg px-4 py-2 text-sm ${
            message.type === 'success' ? 'bg-profit/20 text-profit' : 'bg-loss/20 text-loss'
          }`}
        >
          {message.text}
        </div>
      )}

      <div className="card p-6 space-y-4">
        {configured && (
          <div className="bg-blue-600/10 text-blue-400 text-sm rounded-lg px-4 py-2">
            Credentials are configured. Leave fields empty to keep current values.
          </div>
        )}

        <div>
          <label className="block text-sm text-gray-500 mb-1">API Key</label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={configured ? '***configured***' : 'Enter your IG API key'}
            className="input"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-500 mb-1">Username</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder={configured ? '***configured***' : 'Enter your IG username'}
            className="input"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-500 mb-1">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={configured ? '***configured***' : 'Enter your IG password'}
            className="input"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-500 mb-1">Account Type</label>
            <select
              value={accType}
              onChange={(e) => setAccType(e.target.value)}
              className="input"
            >
              <option value="DEMO">DEMO</option>
              <option value="LIVE">LIVE</option>
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-500 mb-1">Account Number</label>
            <input
              type="text"
              value={accNumber}
              onChange={(e) => setAccNumber(e.target.value)}
              placeholder="e.g., ABC123"
              className="input"
            />
          </div>
        </div>

        <div className="flex gap-3 pt-2">
          <button
            onClick={handleTest}
            disabled={testing}
            className="bg-bg-hover hover:bg-bg-hover/80 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          >
            {testing ? 'Testing...' : 'Test Connection'}
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="btn-primary"
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>

      {/* Discovered accounts */}
      {accounts.length > 0 && (
        <div className="card p-6">
          <h3 className="section-title mb-3">Discovered Accounts</h3>
          <div className="space-y-2">
            {accounts.map((acc) => (
              <div
                key={acc.accountId}
                className={`flex items-center justify-between p-3 rounded-lg border ${
                  acc.accountId === accNumber
                    ? 'border-accent bg-accent/10'
                    : 'border-border'
                }`}
              >
                <div>
                  <span className="font-medium">{acc.accountName || acc.accountId}</span>
                  <span className="text-xs text-gray-500 ml-2">({acc.accountType})</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm">
                    {acc.currency} {acc.balance.toFixed(2)}
                  </span>
                  <button
                    onClick={() => setAccNumber(acc.accountId)}
                    className="text-xs text-blue-400 hover:text-blue-300"
                  >
                    {acc.accountId === accNumber ? 'Selected' : 'Select'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* AI Analysis Settings */}
      <h2 className="text-xl font-semibold text-white pt-4">AI Analysis (Claude)</h2>

      <div className="card p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-sm font-medium text-white">Enable AI Analysis</span>
            <p className="text-xs text-gray-500 mt-0.5">Claude analysera chaque signal avant execution</p>
          </div>
          <button
            onClick={() => setAiEnabled(!aiEnabled)}
            className={`relative w-11 h-6 rounded-full transition-colors ${aiEnabled ? 'bg-profit' : 'bg-gray-600'}`}
          >
            <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${aiEnabled ? 'translate-x-5' : ''}`} />
          </button>
        </div>

        <div>
          <label className="block text-sm text-gray-500 mb-1">Anthropic API Key</label>
          <input
            type="password"
            value={aiApiKey}
            onChange={(e) => setAiApiKey(e.target.value)}
            placeholder={aiConfigured ? '***configured***' : 'sk-ant-...'}
            className="input"
          />
          <p className="text-[10px] text-gray-600 mt-1">Obtenir une cle sur console.anthropic.com</p>
        </div>

        <div>
          <label className="block text-sm text-gray-500 mb-1">Model</label>
          <select value={aiModel} onChange={(e) => setAiModel(e.target.value)} className="input">
            <option value="claude-sonnet-4-6">Claude Sonnet 4.6 (rapide)</option>
            <option value="claude-opus-4-6">Claude Opus 4.6 (precis)</option>
            <option value="claude-haiku-4-5-20251001">Claude Haiku 4.5 (economique)</option>
          </select>
        </div>

        <div className="space-y-3 pt-2">
          <h4 className="section-title">Modes d'analyse</h4>
          <label className="flex items-center justify-between cursor-pointer">
            <div>
              <span className="text-sm text-white">Pre-Trade</span>
              <p className="text-[10px] text-gray-500">Valide chaque signal avant ouverture de position</p>
            </div>
            <button
              onClick={() => setAiPreTrade(!aiPreTrade)}
              className={`relative w-11 h-6 rounded-full transition-colors ${aiPreTrade ? 'bg-accent' : 'bg-gray-600'}`}
            >
              <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${aiPreTrade ? 'translate-x-5' : ''}`} />
            </button>
          </label>
          <label className="flex items-center justify-between cursor-pointer">
            <div>
              <span className="text-sm text-white">Market Review</span>
              <p className="text-[10px] text-gray-500">Analyse de marche a la demande depuis le dashboard</p>
            </div>
            <button
              onClick={() => setAiMarketReview(!aiMarketReview)}
              className={`relative w-11 h-6 rounded-full transition-colors ${aiMarketReview ? 'bg-accent' : 'bg-gray-600'}`}
            >
              <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${aiMarketReview ? 'translate-x-5' : ''}`} />
            </button>
          </label>
          <label className="flex items-center justify-between cursor-pointer">
            <div>
              <span className="text-sm text-white">Post-Trade</span>
              <p className="text-[10px] text-gray-500">Scoring et retour d'experience apres cloture</p>
            </div>
            <button
              onClick={() => setAiPostTrade(!aiPostTrade)}
              className={`relative w-11 h-6 rounded-full transition-colors ${aiPostTrade ? 'bg-accent' : 'bg-gray-600'}`}
            >
              <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${aiPostTrade ? 'translate-x-5' : ''}`} />
            </button>
          </label>
        </div>

        <button
          onClick={handleSaveAi}
          disabled={savingAi}
          className="btn-primary mt-2"
        >
          {savingAi ? 'Saving...' : 'Save AI Settings'}
        </button>
      </div>
    </div>
  )
}
