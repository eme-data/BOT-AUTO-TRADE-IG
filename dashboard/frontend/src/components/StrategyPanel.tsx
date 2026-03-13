
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
      <div className="card p-8 text-center text-gray-500">
        No strategies configured
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {strategies.map((strategy) => (
        <div key={strategy.name} className="card p-4">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="font-medium text-white">{strategy.name}</h4>
              <p className="text-xs text-gray-500 mt-1">
                {strategy.config.epics
                  ? `Epics: ${(strategy.config.epics as string[]).join(', ') || 'None configured'}`
                  : 'No epics configured'}
              </p>
            </div>
            <button
              onClick={() => onToggle(strategy.name, !strategy.enabled)}
              className={strategy.enabled ? 'badge-profit cursor-pointer' : 'badge-neutral cursor-pointer'}
            >
              {strategy.enabled ? 'Enabled' : 'Disabled'}
            </button>
          </div>
          {strategy.enabled && (
            <div className="mt-3 pt-3 border-t border-border">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                {Object.entries(strategy.config)
                  .filter(([key]) => key !== 'epics')
                  .map(([key, value]) => (
                    <div key={key}>
                      <span className="text-gray-500">{key}: </span>
                      <span className="text-gray-300">{String(value)}</span>
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
