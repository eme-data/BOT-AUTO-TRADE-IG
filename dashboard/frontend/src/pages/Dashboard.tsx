import { useState, useEffect, useCallback } from 'react'
import { useApiFetch } from '../context/AuthContext'
import MetricsCards from '../components/MetricsCards'
import PositionsTable from '../components/PositionsTable'
import PnLChart from '../components/PnLChart'
import { useWebSocket } from '../hooks/useWebSocket'

interface Metrics {
  daily_pnl: number
  total_pnl: number
  open_positions: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
}

interface Position {
  deal_id: string
  epic: string
  direction: string
  size: number
  open_level: number
  stop_level: number | null
  limit_level: number | null
  profit: number
}

export default function Dashboard() {
  const apiFetch = useApiFetch()
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [pnlData, setPnlData] = useState<{ time: string; value: number }[]>([])

  const handleMessage = useCallback((data: { type: string; [key: string]: unknown }) => {
    if (data.type === 'tick') {
      // Could update live prices here
    } else if (data.type === 'position_update') {
      // Refresh positions on update
      fetchPositions()
    }
  }, [])

  const { connected } = useWebSocket(handleMessage)

  const fetchMetrics = async () => {
    try {
      const res = await apiFetch('/api/metrics')
      if (res.ok) setMetrics(await res.json())
    } catch {
      // silent
    }
  }

  const fetchPositions = async () => {
    try {
      const res = await apiFetch('/api/positions')
      if (res.ok) setPositions(await res.json())
    } catch {
      // silent
    }
  }

  useEffect(() => {
    fetchMetrics()
    fetchPositions()
    const interval = setInterval(() => {
      fetchMetrics()
      fetchPositions()
    }, 10000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="space-y-6">
      {/* Connection status */}
      <div className="flex items-center gap-2">
        <div
          className={`w-2 h-2 rounded-full ${connected ? 'bg-profit' : 'bg-loss'}`}
        />
        <span className="text-xs text-gray-400">
          {connected ? 'Connected' : 'Disconnected'}
        </span>
      </div>

      {/* Metrics */}
      <MetricsCards metrics={metrics} />

      {/* P&L Chart */}
      <PnLChart data={pnlData} />

      {/* Open Positions */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Open Positions</h2>
        <PositionsTable positions={positions} />
      </div>
    </div>
  )
}
