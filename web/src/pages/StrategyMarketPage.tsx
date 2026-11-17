import { useEffect, useRef, useState } from 'react'
import {
  createChart,
  CandlestickSeries,
  type IChartApi,
  type ISeriesApi,
  CandlestickData,
  Time,
} from 'lightweight-charts'
import { useLanguage } from '../contexts/LanguageContext'
import { t } from '../i18n/translations'

interface Kline {
  openTime: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  closeTime: number
}

// AlgoBots: Data tab — real KXBTC candles from the Nautilus paper feed.
// Replaces the upstream vergex.trade iframe (external site; blocked and
// against the "Nautilus is the only data source" law).
export function StrategyMarketPage() {
  const { language } = useLanguage()
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const [status, setStatus] = useState<'loading' | 'live' | 'error'>('loading')
  const [lastPx, setLastPx] = useState<string>('')
  const [lastTs, setLastTs] = useState<string>('')

  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      height: containerRef.current.clientHeight || 480,
      layout: { background: { color: '#F1ECE2' }, textColor: '#1A1813' },
      grid: {
        vertLines: { color: '#E7E0D2' },
        horzLines: { color: '#E7E0D2' },
      },
      timeScale: { timeVisible: true, secondsVisible: false },
    })
    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
      borderVisible: false,
    })
    chartRef.current = chart
    seriesRef.current = series

    let alive = true
    const load = async () => {
      try {
        const r = await fetch('/api/klines?symbol=KXBTC15M&interval=15m&limit=120')
        const data: Kline[] = await r.json()
        if (!alive) return
        if (!Array.isArray(data) || data.length === 0) {
          setStatus('error')
          return
        }
        const candles: CandlestickData<Time>[] = data.map((k) => ({
          time: (k.openTime / 1000) as Time,
          open: k.open,
          high: k.high,
          low: k.low,
          close: k.close,
        }))
        series.setData(candles)
        const last = data[data.length - 1]
        setLastPx(last.close.toFixed(2))
        setLastTs(
          new Date(last.closeTime).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
          })
        )
        setStatus('live')
        chart.timeScale().fitContent()
      } catch {
        if (alive) setStatus('error')
      }
    }
    load()
    const timer = window.setInterval(load, 60000)

    const onResize = () => {
      if (containerRef.current && chartRef.current)
        chartRef.current.applyOptions({
          height: containerRef.current.clientHeight,
        })
    }
    window.addEventListener('resize', onResize)
    return () => {
      alive = false
      window.clearInterval(timer)
      window.removeEventListener('resize', onResize)
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [])

  return (
    <div className="h-[calc(100vh-64px)] w-full flex flex-col">
      <div className="flex items-center gap-3 px-4 py-2 border-b border-[#E7E0D2] text-sm text-[#1A1813]">
        <span className="font-semibold">KXBTC 15m</span>
        <span className="text-[#6B655A]">Kalshi paper · Nautilus feed</span>
        {lastPx && (
          <span className="font-mono">
            {lastPx}
            <span className="text-[#6B655A]"> @ {lastTs}</span>
          </span>
        )}
        <span
          className={
            status === 'live'
              ? 'text-[#26a69a]'
              : status === 'loading'
                ? 'text-[#6B655A]'
                : 'text-[#ef5350]'
          }
        >
          {status === 'live'
            ? '● live'
            : status === 'loading'
              ? t('loading', language) || 'Loading…'
              : 'feed unavailable'}
        </span>
      </div>
      <div ref={containerRef} className="flex-1 w-full" />
    </div>
  )
}
