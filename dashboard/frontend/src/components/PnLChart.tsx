import { useEffect, useRef } from 'react'
import { createChart, IChartApi, ISeriesApi, LineData, Time } from 'lightweight-charts'

interface Props {
  data: { time: string; value: number }[]
}

export default function PnLChart({ data }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: '#1a2332' },
        textColor: '#6b7280',
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      width: containerRef.current.clientWidth,
      height: 300,
      rightPriceScale: {
        borderColor: '#1e293b',
      },
      timeScale: {
        borderColor: '#1e293b',
      },
    })

    const series = chart.addLineSeries({
      color: '#3b82f6',
      lineWidth: 2,
    })

    chartRef.current = chart
    seriesRef.current = series

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [])

  useEffect(() => {
    if (seriesRef.current && data.length > 0) {
      const chartData: LineData[] = data.map((d) => ({
        time: d.time as Time,
        value: d.value,
      }))
      seriesRef.current.setData(chartData)
    }
  }, [data])

  return (
    <div className="card p-4">
      <h3 className="section-title mb-3">Cumulative P&L</h3>
      <div ref={containerRef} />
    </div>
  )
}
