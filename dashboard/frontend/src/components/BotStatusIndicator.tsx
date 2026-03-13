import { useState, useEffect, useCallback } from 'react'
import { useApiFetch } from '../context/AuthContext'
import { useWebSocket } from '../hooks/useWebSocket'

const STATUS_CONFIG: Record<string, { color: string; bg: string; dot: string; label: string }> = {
  running: { color: 'text-profit', bg: 'bg-profit/15', dot: 'bg-profit animate-pulse', label: 'Running' },
  starting: { color: 'text-yellow-400', bg: 'bg-yellow-400/15', dot: 'bg-yellow-400 animate-pulse', label: 'Starting...' },
  stopped: { color: 'text-gray-400', bg: 'bg-gray-600/20', dot: 'bg-gray-500', label: 'Stopped' },
  error: { color: 'text-loss', bg: 'bg-loss/15', dot: 'bg-loss', label: 'Error' },
  unknown: { color: 'text-gray-500', bg: 'bg-gray-600/20', dot: 'bg-gray-600', label: '...' },
}

export default function BotStatusIndicator() {
  const apiFetch = useApiFetch()
  const [status, setStatus] = useState('unknown')

  const handleMessage = useCallback((data: { type: string; [key: string]: unknown }) => {
    if (data.status && typeof data.status === 'string') {
      setStatus(data.status)
    }
  }, [])

  useWebSocket(handleMessage)

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await apiFetch('/api/bot/status')
        if (res.ok) {
          const data = await res.json()
          setStatus(data.status)
        }
      } catch {
        // silent
      }
    }
    fetchStatus()
    const interval = setInterval(fetchStatus, 30000)
    return () => clearInterval(interval)
  }, [apiFetch])

  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.unknown

  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg ${cfg.bg}`}>
      <div className={`w-2 h-2 rounded-full ${cfg.dot}`} />
      <span className={`text-xs font-medium ${cfg.color}`}>{cfg.label}</span>
    </div>
  )
}
