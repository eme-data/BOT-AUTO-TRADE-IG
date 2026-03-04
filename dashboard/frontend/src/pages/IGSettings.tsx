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

  useEffect(() => {
    loadSettings()
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
      <h2 className="text-lg font-semibold">IG Markets Account</h2>

      {message && (
        <div
          className={`rounded px-4 py-2 text-sm ${
            message.type === 'success' ? 'bg-profit/20 text-profit' : 'bg-loss/20 text-loss'
          }`}
        >
          {message.text}
        </div>
      )}

      <div className="bg-bg-card rounded-lg border border-gray-700 p-6 space-y-4">
        {configured && (
          <div className="bg-blue-600/10 text-blue-400 text-sm rounded px-4 py-2">
            Credentials are configured. Leave fields empty to keep current values.
          </div>
        )}

        <div>
          <label className="block text-sm text-gray-400 mb-1">API Key</label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={configured ? '***configured***' : 'Enter your IG API key'}
            className="w-full bg-bg-primary border border-gray-600 rounded px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">Username</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder={configured ? '***configured***' : 'Enter your IG username'}
            className="w-full bg-bg-primary border border-gray-600 rounded px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={configured ? '***configured***' : 'Enter your IG password'}
            className="w-full bg-bg-primary border border-gray-600 rounded px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Account Type</label>
            <select
              value={accType}
              onChange={(e) => setAccType(e.target.value)}
              className="w-full bg-bg-primary border border-gray-600 rounded px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
            >
              <option value="DEMO">DEMO</option>
              <option value="LIVE">LIVE</option>
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Account Number</label>
            <input
              type="text"
              value={accNumber}
              onChange={(e) => setAccNumber(e.target.value)}
              placeholder="e.g., ABC123"
              className="w-full bg-bg-primary border border-gray-600 rounded px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
            />
          </div>
        </div>

        <div className="flex gap-3 pt-2">
          <button
            onClick={handleTest}
            disabled={testing}
            className="bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded text-sm transition-colors disabled:opacity-50"
          >
            {testing ? 'Testing...' : 'Test Connection'}
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded text-sm transition-colors disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>

      {/* Discovered accounts */}
      {accounts.length > 0 && (
        <div className="bg-bg-card rounded-lg border border-gray-700 p-6">
          <h3 className="text-sm font-medium text-gray-400 mb-3">Discovered Accounts</h3>
          <div className="space-y-2">
            {accounts.map((acc) => (
              <div
                key={acc.accountId}
                className={`flex items-center justify-between p-3 rounded border ${
                  acc.accountId === accNumber
                    ? 'border-blue-500 bg-blue-600/10'
                    : 'border-gray-700'
                }`}
              >
                <div>
                  <span className="font-medium">{acc.accountName || acc.accountId}</span>
                  <span className="text-xs text-gray-400 ml-2">({acc.accountType})</span>
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
    </div>
  )
}
