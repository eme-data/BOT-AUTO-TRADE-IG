import { useState, useEffect } from 'react'
import { useApiFetch } from '../context/AuthContext'

interface SearchResult {
  epic: string
  instrument_name: string
  instrument_type: string
  expiry: string
  bid: number
  offer: number
  market_status: string
  is_watched: boolean
}

interface WatchedMarket {
  id: number
  epic: string
  instrument_name: string
  instrument_type: string
  expiry: string
  currency: string
  enabled: boolean
}

export default function Markets() {
  const apiFetch = useApiFetch()
  const [searchTerm, setSearchTerm] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [watched, setWatched] = useState<WatchedMarket[]>([])
  const [searching, setSearching] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    loadWatched()
  }, [])

  const loadWatched = async () => {
    try {
      const res = await apiFetch('/api/markets/watched')
      if (res.ok) setWatched(await res.json())
    } catch { /* */ }
  }

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault()
    if (searchTerm.length < 2) return
    setSearching(true)
    setMessage(null)
    try {
      const res = await apiFetch(`/api/markets/search?term=${encodeURIComponent(searchTerm)}`)
      if (res.ok) {
        setSearchResults(await res.json())
      } else {
        const err = await res.json()
        setMessage({ type: 'error', text: err.detail || 'Search failed' })
      }
    } catch (e: any) {
      setMessage({ type: 'error', text: e.message })
    } finally {
      setSearching(false)
    }
  }

  const addMarket = async (market: SearchResult) => {
    try {
      const res = await apiFetch('/api/markets/watched', {
        method: 'POST',
        body: JSON.stringify({
          epic: market.epic,
          instrument_name: market.instrument_name,
          instrument_type: market.instrument_type,
          expiry: market.expiry,
        }),
      })
      if (res.ok) {
        setMessage({ type: 'success', text: `${market.instrument_name} added to watchlist` })
        await loadWatched()
        setSearchResults((prev) =>
          prev.map((r) => (r.epic === market.epic ? { ...r, is_watched: true } : r))
        )
      } else {
        const err = await res.json()
        setMessage({ type: 'error', text: err.detail })
      }
    } catch (e: any) {
      setMessage({ type: 'error', text: e.message })
    }
  }

  const removeMarket = async (id: number) => {
    try {
      await apiFetch(`/api/markets/watched/${id}`, { method: 'DELETE' })
      setWatched((prev) => prev.filter((m) => m.id !== id))
      setMessage({ type: 'success', text: 'Market removed' })
    } catch { /* */ }
  }

  const toggleMarket = async (id: number, enabled: boolean) => {
    try {
      await apiFetch(`/api/markets/watched/${id}?enabled=${enabled}`, { method: 'PUT' })
      setWatched((prev) => prev.map((m) => (m.id === id ? { ...m, enabled } : m)))
    } catch { /* */ }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Markets</h2>

      {message && (
        <div
          className={`rounded px-4 py-2 text-sm ${
            message.type === 'success' ? 'bg-profit/20 text-profit' : 'bg-loss/20 text-loss'
          }`}
        >
          {message.text}
        </div>
      )}

      {/* Search */}
      <div className="bg-bg-card rounded-lg border border-gray-700 p-6">
        <h3 className="text-sm font-medium text-gray-400 mb-3">Search IG Markets</h3>
        <form onSubmit={handleSearch} className="flex gap-3">
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by keyword (e.g., EURUSD, FTSE, Apple...)"
            className="flex-1 bg-bg-primary border border-gray-600 rounded px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
            minLength={2}
          />
          <button
            type="submit"
            disabled={searching || searchTerm.length < 2}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded text-sm transition-colors disabled:opacity-50"
          >
            {searching ? 'Searching...' : 'Search'}
          </button>
        </form>

        {searchResults.length > 0 && (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 text-gray-400 text-xs uppercase">
                  <th className="text-left px-3 py-2">Instrument</th>
                  <th className="text-left px-3 py-2">Type</th>
                  <th className="text-right px-3 py-2">Bid</th>
                  <th className="text-right px-3 py-2">Offer</th>
                  <th className="text-center px-3 py-2">Status</th>
                  <th className="text-right px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {searchResults.map((r) => (
                  <tr key={r.epic} className="border-b border-gray-800 hover:bg-gray-800/50">
                    <td className="px-3 py-2">
                      <div className="font-medium">{r.instrument_name}</div>
                      <div className="text-xs text-gray-500">{r.epic}</div>
                    </td>
                    <td className="px-3 py-2 text-gray-400">{r.instrument_type}</td>
                    <td className="px-3 py-2 text-right">{r.bid.toFixed(2)}</td>
                    <td className="px-3 py-2 text-right">{r.offer.toFixed(2)}</td>
                    <td className="px-3 py-2 text-center">
                      <span
                        className={`px-2 py-0.5 rounded text-xs ${
                          r.market_status === 'TRADEABLE'
                            ? 'bg-profit/20 text-profit'
                            : 'bg-gray-700 text-gray-400'
                        }`}
                      >
                        {r.market_status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      {r.is_watched ? (
                        <span className="text-xs text-gray-500">Added</span>
                      ) : (
                        <button
                          onClick={() => addMarket(r)}
                          className="text-xs text-blue-400 hover:text-blue-300"
                        >
                          + Add
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

      {/* Watchlist */}
      <div className="bg-bg-card rounded-lg border border-gray-700 p-6">
        <h3 className="text-sm font-medium text-gray-400 mb-3">
          Watchlist ({watched.length} market{watched.length !== 1 ? 's' : ''})
        </h3>
        {watched.length === 0 ? (
          <p className="text-gray-500 text-sm">No markets in watchlist. Search and add markets above.</p>
        ) : (
          <div className="space-y-2">
            {watched.map((m) => (
              <div
                key={m.id}
                className={`flex items-center justify-between p-3 rounded border ${
                  m.enabled ? 'border-gray-700' : 'border-gray-800 opacity-50'
                }`}
              >
                <div>
                  <span className="font-medium">{m.instrument_name || m.epic}</span>
                  <span className="text-xs text-gray-500 ml-2">{m.epic}</span>
                  <span className="text-xs text-gray-600 ml-2">{m.instrument_type}</span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => toggleMarket(m.id, !m.enabled)}
                    className={`px-2 py-1 rounded text-xs ${
                      m.enabled
                        ? 'bg-profit/20 text-profit hover:bg-profit/30'
                        : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
                    }`}
                  >
                    {m.enabled ? 'Enabled' : 'Disabled'}
                  </button>
                  <button
                    onClick={() => removeMarket(m.id)}
                    className="text-xs text-loss hover:text-red-400"
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
