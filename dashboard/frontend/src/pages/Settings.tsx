import { useState, useEffect } from 'react'
import { useApiFetch } from '../context/AuthContext'
import StrategyPanel from '../components/StrategyPanel'

interface Strategy {
  name: string
  enabled: boolean
  config: Record<string, unknown>
}

interface WatchedMarket {
  epic: string
  instrument_name: string
  enabled: boolean
}

export default function Settings() {
  const apiFetch = useApiFetch()
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [markets, setMarkets] = useState<WatchedMarket[]>([])
  const [editingStrategy, setEditingStrategy] = useState<string | null>(null)
  const [editConfig, setEditConfig] = useState<string>('')
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    fetchStrategies()
    fetchMarkets()
  }, [])

  const fetchStrategies = async () => {
    try {
      const res = await apiFetch('/api/strategies')
      if (res.ok) setStrategies(await res.json())
    } catch { /* */ }
  }

  const fetchMarkets = async () => {
    try {
      const res = await apiFetch('/api/markets/watched')
      if (res.ok) setMarkets(await res.json())
    } catch { /* */ }
  }

  const toggleStrategy = async (name: string, enabled: boolean) => {
    try {
      const res = await apiFetch(`/api/strategies/${name}`, {
        method: 'PUT',
        body: JSON.stringify({ enabled }),
      })
      if (res.ok) {
        setStrategies((prev) =>
          prev.map((s) => (s.name === name ? { ...s, enabled } : s))
        )
      }
    } catch { /* */ }
  }

  const startEditConfig = (strategy: Strategy) => {
    setEditingStrategy(strategy.name)
    setEditConfig(JSON.stringify(strategy.config, null, 2))
  }

  const saveConfig = async () => {
    if (!editingStrategy) return
    setMessage(null)
    try {
      const config = JSON.parse(editConfig)
      const res = await apiFetch(`/api/strategies/${editingStrategy}`, {
        method: 'PUT',
        body: JSON.stringify({ config }),
      })
      if (res.ok) {
        setMessage({ type: 'success', text: `Strategy ${editingStrategy} updated` })
        setEditingStrategy(null)
        fetchStrategies()
      }
    } catch (e: any) {
      setMessage({ type: 'error', text: `Invalid JSON: ${e.message}` })
    }
  }

  // Available epics from watched markets
  const availableEpics = markets.filter((m) => m.enabled).map((m) => m.epic)

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Strategies Configuration</h2>

      {message && (
        <div
          className={`rounded px-4 py-2 text-sm ${
            message.type === 'success' ? 'bg-profit/20 text-profit' : 'bg-loss/20 text-loss'
          }`}
        >
          {message.text}
        </div>
      )}

      {availableEpics.length === 0 && (
        <div className="bg-yellow-500/10 text-yellow-400 text-sm rounded px-4 py-2">
          No markets in watchlist. Go to Markets page to add instruments before configuring strategies.
        </div>
      )}

      <StrategyPanel strategies={strategies} onToggle={toggleStrategy} />

      {/* Strategy config editor */}
      <div className="space-y-3">
        {strategies.map((s) => (
          <div key={s.name} className="bg-bg-card rounded-lg border border-gray-700 p-4">
            <div className="flex items-center justify-between mb-3">
              <h4 className="font-medium">{s.name}</h4>
              <button
                onClick={() =>
                  editingStrategy === s.name ? setEditingStrategy(null) : startEditConfig(s)
                }
                className="text-xs text-blue-400 hover:text-blue-300"
              >
                {editingStrategy === s.name ? 'Cancel' : 'Edit Config'}
              </button>
            </div>

            {editingStrategy === s.name && (
              <div className="space-y-3">
                {availableEpics.length > 0 && (
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">
                      Available epics (click to add to config):
                    </label>
                    <div className="flex flex-wrap gap-1">
                      {availableEpics.map((epic) => (
                        <button
                          key={epic}
                          onClick={() => {
                            try {
                              const config = JSON.parse(editConfig)
                              if (!config.epics) config.epics = []
                              if (!config.epics.includes(epic)) {
                                config.epics.push(epic)
                                setEditConfig(JSON.stringify(config, null, 2))
                              }
                            } catch { /* */ }
                          }}
                          className="px-2 py-0.5 bg-gray-700 text-gray-300 rounded text-xs hover:bg-gray-600"
                        >
                          {epic}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <textarea
                  value={editConfig}
                  onChange={(e) => setEditConfig(e.target.value)}
                  className="w-full h-48 bg-bg-primary border border-gray-600 rounded px-3 py-2 text-white font-mono text-sm focus:border-blue-500 focus:outline-none"
                  spellCheck={false}
                />
                <button
                  onClick={saveConfig}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded text-sm"
                >
                  Save Config
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
