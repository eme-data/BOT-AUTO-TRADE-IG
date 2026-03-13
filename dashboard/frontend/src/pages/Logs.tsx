import { useState, useEffect, useCallback, useRef } from 'react'
import { useWebSocket } from '../hooks/useWebSocket'

interface LogEntry {
  time: string
  level: string
  message: string
  [key: string]: unknown
}

const LEVEL_COLORS: Record<string, string> = {
  INFO: 'text-blue-400',
  WARNING: 'text-yellow-400',
  ERROR: 'text-loss',
  DEBUG: 'text-gray-500',
}

export default function Logs() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [autoScroll, setAutoScroll] = useState(true)
  const [filter, setFilter] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)

  const handleMessage = useCallback((data: { type: string; [key: string]: unknown }) => {
    // Log messages come from bot:logs channel
    if (data.level && data.message) {
      setLogs((prev) => {
        const updated = [...prev, data as unknown as LogEntry]
        // Keep last 1000 entries
        return updated.length > 1000 ? updated.slice(-1000) : updated
      })
    }
  }, [])

  const { connected } = useWebSocket(handleMessage)

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  const filteredLogs = filter
    ? logs.filter(
        (l) =>
          l.message.toLowerCase().includes(filter.toLowerCase()) ||
          l.level.toLowerCase().includes(filter.toLowerCase())
      )
    : logs

  const formatTime = (iso: string) => {
    try {
      return new Date(iso).toLocaleTimeString()
    } catch {
      return iso
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-semibold text-white">Live Logs</h2>
          <div className={`w-2 h-2 rounded-full ${connected ? 'bg-profit' : 'bg-loss'}`} />
          <span className="text-xs text-gray-500">{logs.length} entries</span>
        </div>
        <div className="flex items-center gap-3">
          <input
            type="text"
            placeholder="Filter logs..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="input w-48"
          />
          <label className="flex items-center gap-1.5 text-xs text-gray-500">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="rounded"
            />
            Auto-scroll
          </label>
          <button
            onClick={() => setLogs([])}
            className="text-xs text-gray-500 hover:text-white px-2 py-1 rounded border border-border"
          >
            Clear
          </button>
        </div>
      </div>

      <div
        ref={containerRef}
        className="card p-4 h-[calc(100vh-220px)] overflow-y-auto font-mono text-xs"
      >
        {filteredLogs.length === 0 ? (
          <div className="text-gray-500 text-center py-12">
            {connected ? 'Waiting for log entries...' : 'Not connected to bot'}
          </div>
        ) : (
          filteredLogs.map((entry, i) => (
            <div key={i} className="flex gap-3 py-0.5 hover:bg-bg-hover/50 px-1 rounded">
              <span className="text-gray-600 whitespace-nowrap">{formatTime(entry.time)}</span>
              <span className={`font-medium w-16 ${LEVEL_COLORS[entry.level] || 'text-gray-400'}`}>
                {entry.level}
              </span>
              <span className="text-gray-300 break-all">{entry.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
