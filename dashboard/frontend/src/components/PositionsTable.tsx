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

interface Props {
  positions: Position[]
}

export default function PositionsTable({ positions }: Props) {
  if (positions.length === 0) {
    return (
      <div className="bg-bg-card rounded-lg border border-gray-700 p-8 text-center text-gray-400">
        No open positions
      </div>
    )
  }

  return (
    <div className="bg-bg-card rounded-lg border border-gray-700 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-700 text-gray-400 text-xs uppercase">
            <th className="text-left px-4 py-3">Epic</th>
            <th className="text-left px-4 py-3">Direction</th>
            <th className="text-right px-4 py-3">Size</th>
            <th className="text-right px-4 py-3">Open</th>
            <th className="text-right px-4 py-3">Stop</th>
            <th className="text-right px-4 py-3">Limit</th>
            <th className="text-right px-4 py-3">P&L</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((pos) => (
            <tr key={pos.deal_id} className="border-b border-gray-800 hover:bg-gray-800/50">
              <td className="px-4 py-3 font-medium">{pos.epic}</td>
              <td className="px-4 py-3">
                <span
                  className={`px-2 py-0.5 rounded text-xs font-medium ${
                    pos.direction === 'BUY'
                      ? 'bg-profit/20 text-profit'
                      : 'bg-loss/20 text-loss'
                  }`}
                >
                  {pos.direction}
                </span>
              </td>
              <td className="px-4 py-3 text-right">{pos.size}</td>
              <td className="px-4 py-3 text-right">{pos.open_level.toFixed(2)}</td>
              <td className="px-4 py-3 text-right text-gray-400">
                {pos.stop_level?.toFixed(2) || '-'}
              </td>
              <td className="px-4 py-3 text-right text-gray-400">
                {pos.limit_level?.toFixed(2) || '-'}
              </td>
              <td
                className={`px-4 py-3 text-right font-medium ${
                  pos.profit >= 0 ? 'text-profit' : 'text-loss'
                }`}
              >
                {pos.profit >= 0 ? '+' : ''}{pos.profit.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
