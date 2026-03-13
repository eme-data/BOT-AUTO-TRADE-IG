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
      <div className="card p-8 text-center text-gray-500">
        No open positions
      </div>
    )
  }

  return (
    <div className="card overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-gray-500 text-xs uppercase">
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
            <tr key={pos.deal_id} className="border-b border-border/50 hover:bg-bg-hover/50 transition-colors">
              <td className="px-4 py-3 font-medium text-white">{pos.epic}</td>
              <td className="px-4 py-3">
                <span className={pos.direction === 'BUY' ? 'badge-profit' : 'badge-loss'}>
                  {pos.direction}
                </span>
              </td>
              <td className="px-4 py-3 text-right text-gray-300">{pos.size}</td>
              <td className="px-4 py-3 text-right text-gray-300">{pos.open_level.toFixed(2)}</td>
              <td className="px-4 py-3 text-right text-gray-500">
                {pos.stop_level?.toFixed(2) || '-'}
              </td>
              <td className="px-4 py-3 text-right text-gray-500">
                {pos.limit_level?.toFixed(2) || '-'}
              </td>
              <td className={`px-4 py-3 text-right font-semibold ${pos.profit >= 0 ? 'text-profit' : 'text-loss'}`}>
                {pos.profit >= 0 ? '+' : ''}{pos.profit.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
