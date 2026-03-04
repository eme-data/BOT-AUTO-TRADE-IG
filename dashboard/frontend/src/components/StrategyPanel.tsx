import { useState } from 'react'

interface Strategy {
  name: string
  enabled: boolean
  config: Record<string, unknown>
}

interface Props {
  strategies: Strategy[]
  onToggle: (name: string, enabled: boolean) => void
}

export default function StrategyPanel({ strategies, onToggle }: Props) {
  if (strategies.length === 0) {
    return (
      <div className="bg-bg-card rounded-lg border border-gray-700 p-8 text-center text-gray-400">
        No strategies configured
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {strategies.map((strategy) => (
        <div
          key={strategy.name}
          className="bg-bg-card rounded-lg border border-gray-700 p-4"
        >
          <div className="flex items-center justify-between">
            <div>
              <h4 className="font-medium text-white">{strategy.name}</h4>
              <p className="text-xs text-gray-400 mt-1">
                {strategy.config.epics
                  ? `Epics: ${(strategy.config.epics as string[]).join(', ') || 'None configured'}`
                  : 'No epics configured'}
              </p>
            </div>
            <button
              onClick={() => onToggle(strategy.name, !strategy.enabled)}
              className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                strategy.enabled
                  ? 'bg-profit/20 text-profit hover:bg-profit/30'
                  : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
              }`}
            >
              {strategy.enabled ? 'Enabled' : 'Disabled'}
            </button>
          </div>
          {strategy.enabled && (
            <div className="mt-3 pt-3 border-t border-gray-700">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                {Object.entries(strategy.config)
                  .filter(([key]) => key !== 'epics')
                  .map(([key, value]) => (
                    <div key={key}>
                      <span className="text-gray-400">{key}: </span>
                      <span className="text-white">{String(value)}</span>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
