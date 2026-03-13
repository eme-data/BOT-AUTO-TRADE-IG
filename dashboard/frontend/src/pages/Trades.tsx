import { useState, useEffect } from 'react'
import { useAuth, useApiFetch } from '../context/AuthContext'

interface Trade {
  id: number
  deal_id: string
  epic: string
  direction: string
  size: number
  open_price: number | null
  close_price: number | null
  profit: number | null
  strategy_name: string | null
  status: string
  opened_at: string
  closed_at: string | null
  notes: string | null
}

export default function Trades() {
  const { token } = useAuth()
  const apiFetch = useApiFetch()
  const [trades, setTrades] = useState<Trade[]>([])
  const [filter, setFilter] = useState<'ALL' | 'OPEN' | 'CLOSED'>('ALL')
  const [loading, setLoading] = useState(true)
  const [editingNotes, setEditingNotes] = useState<number | null>(null)
  const [notesText, setNotesText] = useState('')

  const handleExportCSV = () => {
    const params = filter !== 'ALL' ? `?status=${filter}` : ''
    const url = `/api/trades/export/csv${params}`
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => res.blob())
      .then((blob) => {
        const a = document.createElement('a')
        a.href = URL.createObjectURL(blob)
        a.download = 'trades.csv'
        a.click()
        URL.revokeObjectURL(a.href)
      })
      .catch(() => {})
  }

  const fetchTrades = async () => {
    try {
      const params = filter !== 'ALL' ? `?status=${filter}` : ''
      const res = await apiFetch(`/api/trades${params}`)
      if (res.ok) setTrades(await res.json())
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }

  const saveNotes = async (tradeId: number) => {
    try {
      await apiFetch(`/api/trades/${tradeId}/notes`, {
        method: 'PATCH',
        body: JSON.stringify({ notes: notesText }),
      })
      setTrades((prev) =>
        prev.map((t) => (t.id === tradeId ? { ...t, notes: notesText } : t))
      )
      setEditingNotes(null)
    } catch {
      // silent
    }
  }

  useEffect(() => {
    fetchTrades()
  }, [filter])

  const statusBadgeClass = (status: string) => {
    switch (status) {
      case 'SHADOW':
        return 'badge-warning'
      case 'OPEN':
        return 'badge-accent'
      case 'CLOSED':
        return 'badge-neutral'
      default:
        return 'badge-neutral'
    }
  }

  const statusLabel = (status: string) => {
    switch (status) {
      case 'SHADOW':
        return 'Shadow'
      case 'OPEN':
        return 'Open'
      case 'CLOSED':
        return 'Closed'
      default:
        return status
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">Trade History</h2>
        <div className="flex items-center gap-3">
          <div className="flex gap-2">
            {(['ALL', 'OPEN', 'CLOSED'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3 py-1.5 rounded text-xs font-medium ${
                  filter === f
                    ? 'btn-primary'
                    : 'card text-gray-400 hover:text-white'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
          <button
            onClick={handleExportCSV}
            className="card px-3 py-1.5 text-xs font-medium text-gray-400 hover:text-white"
          >
            Export CSV
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center text-gray-400 py-8">Loading...</div>
      ) : trades.length === 0 ? (
        <div className="card p-8 text-center text-gray-400">
          No trades found
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="section-title text-left px-4 py-3">Date</th>
                <th className="section-title text-left px-4 py-3">Epic</th>
                <th className="section-title text-left px-4 py-3">Direction</th>
                <th className="section-title text-right px-4 py-3">Size</th>
                <th className="section-title text-right px-4 py-3">Open</th>
                <th className="section-title text-right px-4 py-3">Close</th>
                <th className="section-title text-left px-4 py-3">Strategy</th>
                <th className="section-title text-left px-4 py-3">Status</th>
                <th className="section-title text-right px-4 py-3">P&L</th>
                <th className="section-title text-left px-4 py-3">Notes</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => (
                <tr key={trade.id} className="border-b border-border/50 hover:bg-bg-hover/50">
                  <td className="px-4 py-3 text-gray-400 text-xs">
                    {new Date(trade.opened_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 font-medium">{trade.epic}</td>
                  <td className="px-4 py-3">
                    <span
                      className={
                        trade.direction === 'BUY'
                          ? 'badge-profit'
                          : 'badge-loss'
                      }
                    >
                      {trade.direction}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">{trade.size}</td>
                  <td className="px-4 py-3 text-right">{trade.open_price?.toFixed(2) || '-'}</td>
                  <td className="px-4 py-3 text-right">{trade.close_price?.toFixed(2) || '-'}</td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{trade.strategy_name || '-'}</td>
                  <td className="px-4 py-3">
                    <span className={statusBadgeClass(trade.status)}>
                      {statusLabel(trade.status)}
                    </span>
                  </td>
                  <td
                    className={`px-4 py-3 text-right font-medium ${
                      (trade.profit || 0) >= 0 ? 'text-profit' : 'text-loss'
                    }`}
                  >
                    {trade.profit != null
                      ? `${trade.profit >= 0 ? '+' : ''}${trade.profit.toFixed(2)}`
                      : '-'}
                  </td>
                  <td className="px-4 py-3">
                    {editingNotes === trade.id ? (
                      <div className="flex gap-1">
                        <input
                          type="text"
                          value={notesText}
                          onChange={(e) => setNotesText(e.target.value)}
                          onKeyDown={(e) => e.key === 'Enter' && saveNotes(trade.id)}
                          className="input text-xs w-32"
                          autoFocus
                        />
                        <button
                          onClick={() => saveNotes(trade.id)}
                          className="text-xs text-blue-400 hover:text-blue-300"
                        >
                          Save
                        </button>
                        <button
                          onClick={() => setEditingNotes(null)}
                          className="text-xs text-gray-500 hover:text-gray-400"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => {
                          setEditingNotes(trade.id)
                          setNotesText(trade.notes || '')
                        }}
                        className="text-xs text-gray-500 hover:text-gray-300 max-w-[150px] truncate block"
                        title={trade.notes || 'Click to add notes'}
                      >
                        {trade.notes || '+ Add note'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
