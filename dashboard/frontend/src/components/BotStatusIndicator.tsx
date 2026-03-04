import { useState, useEffect, useCallback } from 'react'
import { useApiFetch } from '../context/AuthContext'
import { useWebSocket } from '../hooks/useWebSocket'

const STATUS_COLORS: Record<string, string> = {
  running: 'bg-profit',
  starting: 'bg-yellow-400',
  stopped: 'bg-gray-500',
  error: 'bg-loss',
  unknown: 'bg-gray-600',
}

const STATUS_LABELS: Record<string, string> = {
  running: 'Running',
  starting: 'Starting...',
  stopped: 'Stopped',
  error: 'Error',
  unknown: '...',
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

  return (
    <div className="flex items-center gap-1.5">
      <div className={`w-2 h-2 rounded-full ${STATUS_COLORS[status] || STATUS_COLORS.unknown}`} />
      <span className="text-xs text-gray-400">{STATUS_LABELS[status] || status}</span>
    </div>
  )
}
