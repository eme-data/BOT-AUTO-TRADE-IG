import { useState, useEffect } from 'react'
import { useApiFetch } from '../context/AuthContext'

export default function Notifications() {
  const apiFetch = useApiFetch()
  const [botToken, setBotToken] = useState('')
  const [chatId, setChatId] = useState('')
  const [configured, setConfigured] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    loadSettings()
  }, [])

  const loadSettings = async () => {
    try {
      const res = await apiFetch('/api/settings/notifications')
      if (res.ok) {
        const data = await res.json()
        for (const s of data) {
          if (s.key === 'telegram_bot_token') setConfigured(s.value !== '')
          if (s.key === 'telegram_chat_id') setChatId(s.value || '')
        }
      }
    } catch { /* */ }
  }

  const handleSave = async () => {
    if (!chatId.trim()) {
      setMessage({ type: 'error', text: 'Chat ID is required' })
      return
    }
    setSaving(true)
    setMessage(null)
    try {
      const settingsToSave: Record<string, string> = {
        telegram_chat_id: chatId,
      }
      if (botToken) settingsToSave.telegram_bot_token = botToken

      const res = await apiFetch('/api/settings', {
        method: 'PUT',
        body: JSON.stringify({ settings: settingsToSave }),
      })
      if (res.ok) {
        setMessage({ type: 'success', text: 'Telegram settings saved. Restart bot to apply.' })
        setConfigured(true)
        setBotToken('')
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
    try {
      const token = botToken || '__stored__'
      const res = await apiFetch('/api/notifications/test', {
        method: 'POST',
        body: JSON.stringify({ bot_token: token, chat_id: chatId }),
      })
      const data = await res.json()
      if (data.success) {
        setMessage({ type: 'success', text: 'Test message sent successfully!' })
      } else {
        setMessage({ type: 'error', text: data.message || 'Test failed' })
      }
    } catch (e: any) {
      setMessage({ type: 'error', text: e.message })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <h2 className="text-lg font-semibold">Notifications (Telegram)</h2>

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
        <p className="text-sm text-gray-400">
          Get notified on Telegram when trades are opened/closed and when the bot starts/stops.
        </p>

        {configured && (
          <div className="bg-blue-600/10 text-blue-400 text-sm rounded px-4 py-2">
            Bot token is configured. Leave empty to keep current value.
          </div>
        )}

        <div>
          <label className="block text-sm text-gray-400 mb-1">Bot Token</label>
          <input
            type="password"
            value={botToken}
            onChange={(e) => setBotToken(e.target.value)}
            placeholder={configured ? '***configured***' : 'e.g., 123456:ABC-DEF...'}
            className="w-full bg-bg-primary border border-gray-600 rounded px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
          />
          <p className="text-xs text-gray-600 mt-1">Create a bot via @BotFather on Telegram</p>
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">Chat ID</label>
          <input
            type="text"
            value={chatId}
            onChange={(e) => setChatId(e.target.value)}
            placeholder="e.g., -1001234567890"
            className="w-full bg-bg-primary border border-gray-600 rounded px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
          />
          <p className="text-xs text-gray-600 mt-1">Your personal chat ID or a group chat ID</p>
        </div>

        <div className="flex gap-3 pt-2">
          <button
            onClick={handleTest}
            disabled={testing || (!botToken && !configured) || !chatId}
            className="bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded text-sm transition-colors disabled:opacity-50"
          >
            {testing ? 'Sending...' : 'Send Test Message'}
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
    </div>
  )
}
