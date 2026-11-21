import { useCallback, useEffect, useState } from 'react'
import {
  Activity,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  Settings,
  TrendingUp,
  TrendingDown,
} from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_BASE || ''

interface CoinflipParams {
  qty: number
  windowTiming: 'begin' | 'middle' | 'end'
  series: '15m' | '5m'
}

interface LiveStats {
  ordersTotal: number
  fillsTotal: number
  hitRate: number
  lastDecisionAt: string | null
  lastSide: 'YES' | 'NO' | null
  feedState: 'live' | 'stale' | 'unavailable'
  feedAge: number
  recentDecisions: Array<{
    event: string
    side: string
    status: string
    outcome: 'HIT' | 'MISS' | null
    decidedAt: string
  }>
}

interface Props {
  token: string | null
  onError?: (message: string) => void
}

export function CoinflipStrategyCard({ token, onError }: Props) {
  const [enabled, setEnabled] = useState(false)
  const [deploymentId, setDeploymentId] = useState<string | null>(null)
  const [params, setParams] = useState<CoinflipParams>({
    qty: 1,
    windowTiming: 'middle',
    series: '15m',
  })
  const [stats, setStats] = useState<LiveStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [toggling, setToggling] = useState(false)
  const [showSettings, setShowSettings] = useState(false)

  const fetchLive = useCallback(async () => {
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/api/nofx/studio/live`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error('Failed to fetch live data')
      const data = await res.json()

      const decisions = data.decisions || []
      const filled = decisions.filter(
        (d: any) => d.execution === 'FILLED'
      ).length
      const settled = decisions.filter((d: any) => d.outcome !== null)
      const hits = settled.filter(
        (d: any) =>
          d.outcome === 'HIT' ||
          (d.side === 'YES' && d.outcome === 1) ||
          (d.side === 'NO' && d.outcome === 0)
      ).length

      setStats({
        ordersTotal: decisions.length,
        fillsTotal: filled,
        hitRate: settled.length > 0 ? (hits / settled.length) * 100 : 0,
        lastDecisionAt: decisions[0]?.decided_at || null,
        lastSide: decisions[0]?.side || null,
        feedState: data.feed?.state || 'unavailable',
        feedAge: Math.round(data.feed?.age_s || 0),
        recentDecisions: decisions.slice(0, 5).map((d: any) => ({
          event: d.event || '',
          side: d.side || '',
          status: d.execution || d.status || '',
          outcome:
            d.outcome === 'HIT'
              ? 'HIT'
              : d.outcome === 'MISS'
                ? 'MISS'
                : null,
          decidedAt: d.decided_at || '',
        })),
      })

      const coinflipDeployment = data.deployments?.find(
        (d: any) =>
          d.strategy?.toLowerCase().includes('coinflip') ||
          d.symbol?.includes('KXBTC')
      )
      if (coinflipDeployment) {
        setDeploymentId(coinflipDeployment.deployment_id)
        setEnabled(coinflipDeployment.status === 'running')
      } else {
        setDeploymentId(null)
        const isRunning = data.workers?.some((w: any) => w.state === 'running')
        setEnabled(isRunning)
      }
    } catch (err) {
      onError?.(err instanceof Error ? err.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [token, onError])

  useEffect(() => {
    fetchLive()
    const interval = setInterval(fetchLive, 15000)
    return () => clearInterval(interval)
  }, [fetchLive])

  const handleToggle = async () => {
    if (!deploymentId) {
      onError?.('No coinflip deployment found')
      return
    }
    setToggling(true)
    try {
      const newStatus = enabled ? 'paused' : 'running'
      const res = await fetch(`${API_BASE}/api/deployments/${deploymentId}`, {
        method: 'PATCH',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ status: newStatus }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || data.error || data.message || `Failed to ${newStatus}`)
      }
      setEnabled(!enabled)
      await fetchLive()
    } catch (err) {
      onError?.(err instanceof Error ? err.message : 'Toggle failed')
    } finally {
      setToggling(false)
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-[rgba(25,36,52,0.14)] bg-nofx-bg-lighter">
        <Loader2 className="h-6 w-6 animate-spin text-nofx-gold" />
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-[rgba(25,36,52,0.14)] bg-nofx-bg-lighter">
      <div className="flex items-center justify-between border-b border-[rgba(25,36,52,0.14)] p-4">
        <div className="flex items-center gap-3">
          <div
            className={`h-10 w-10 rounded-lg flex items-center justify-center ${
              enabled
                ? 'bg-nofx-success/20 text-nofx-success'
                : 'bg-nofx-bg-deeper text-nofx-text-muted'
            }`}
          >
            <Activity className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-nofx-text">
              Kalshi BTC {params.series === '15m' ? '15-minute' : '5-minute'}{' '}
              Coinflip
            </h3>
            <p className="mt-0.5 text-xs text-nofx-text-muted">
              Random yes/no each window · paper venue · real Kalshi prices
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowSettings(!showSettings)}
            className="rounded-lg border border-[rgba(25,36,52,0.14)] bg-nofx-bg-deeper p-2 text-nofx-text-muted hover:text-nofx-text"
          >
            <Settings className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={fetchLive}
            disabled={loading}
            className="rounded-lg border border-[rgba(25,36,52,0.14)] bg-nofx-bg-deeper p-2 text-nofx-text-muted hover:text-nofx-text disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            type="button"
            onClick={handleToggle}
            disabled={toggling || !deploymentId}
            className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50 ${
              enabled
                ? 'bg-nofx-danger/20 text-nofx-danger hover:bg-nofx-danger/30'
                : 'bg-nofx-success text-nofx-bg hover:bg-nofx-success/90'
            }`}
          >
            {toggling ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : enabled ? (
              <Pause className="h-4 w-4" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            {enabled ? 'Pause' : 'Start'}
          </button>
        </div>
      </div>

      {showSettings && (
        <div className="border-b border-[rgba(25,36,52,0.14)] bg-nofx-bg-deeper p-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <label className="space-y-2">
              <span className="text-xs font-medium text-nofx-text-muted">
                Contracts per trade
              </span>
              <select
                value={params.qty}
                onChange={(e) =>
                  setParams({ ...params, qty: Number(e.target.value) })
                }
                className="w-full rounded-lg border border-[rgba(25,36,52,0.14)] bg-nofx-bg px-3 py-2 text-sm text-nofx-text"
              >
                {[1, 2, 5, 10].map((q) => (
                  <option key={q} value={q}>
                    {q} contract{q > 1 ? 's' : ''}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-2">
              <span className="text-xs font-medium text-nofx-text-muted">
                Window timing
              </span>
              <select
                value={params.windowTiming}
                onChange={(e) =>
                  setParams({
                    ...params,
                    windowTiming: e.target.value as 'begin' | 'middle' | 'end',
                  })
                }
                className="w-full rounded-lg border border-[rgba(25,36,52,0.14)] bg-nofx-bg px-3 py-2 text-sm text-nofx-text"
              >
                <option value="begin">Beginning of window</option>
                <option value="middle">Middle of window</option>
                <option value="end">End of window</option>
              </select>
            </label>
            <label className="space-y-2">
              <span className="text-xs font-medium text-nofx-text-muted">
                Series
              </span>
              <select
                value={params.series}
                onChange={(e) =>
                  setParams({
                    ...params,
                    series: e.target.value as '15m' | '5m',
                  })
                }
                className="w-full rounded-lg border border-[rgba(25,36,52,0.14)] bg-nofx-bg px-3 py-2 text-sm text-nofx-text"
              >
                <option value="15m">15-minute (KXBTC15M)</option>
                <option value="5m">5-minute (KXBTC5M)</option>
              </select>
            </label>
          </div>
          <p className="mt-3 text-xs text-nofx-text-muted">
            Window timing affects results — beginning has different market
            conditions than end of window.
          </p>
        </div>
      )}

      <div className="grid gap-px bg-[rgba(25,36,52,0.14)] sm:grid-cols-4">
        <StatTile
          label="Orders"
          value={stats?.ordersTotal?.toString() || '—'}
          sublabel="total decisions"
        />
        <StatTile
          label="Fills"
          value={stats?.fillsTotal?.toString() || '—'}
          sublabel="executed"
        />
        <StatTile
          label="Hit Rate"
          value={stats?.hitRate ? `${stats.hitRate.toFixed(1)}%` : '—'}
          sublabel="settled correct"
          tone={
            stats?.hitRate
              ? stats.hitRate >= 50
                ? 'green'
                : 'red'
              : 'neutral'
          }
        />
        <StatTile
          label="Feed"
          value={stats?.feedState || 'unavailable'}
          sublabel={stats?.feedAge ? `${stats.feedAge}s ago` : ''}
          tone={
            stats?.feedState === 'live'
              ? 'green'
              : stats?.feedState === 'stale'
                ? 'yellow'
                : 'red'
          }
        />
      </div>

      {stats?.recentDecisions && stats.recentDecisions.length > 0 && (
        <div className="p-4">
          <h4 className="mb-3 text-sm font-semibold text-nofx-text">
            Recent Decisions
          </h4>
          <div className="space-y-2">
            {stats.recentDecisions.map((d, i) => (
              <div
                key={`${d.event}-${i}`}
                className="flex items-center justify-between rounded-md bg-nofx-bg-deeper px-3 py-2 text-sm"
              >
                <div className="flex items-center gap-3">
                  {d.side === 'YES' ? (
                    <TrendingUp className="h-4 w-4 text-nofx-success" />
                  ) : (
                    <TrendingDown className="h-4 w-4 text-nofx-danger" />
                  )}
                  <span className="font-mono text-nofx-text">{d.event}</span>
                </div>
                <div className="flex items-center gap-3 text-xs">
                  <span
                    className={`rounded px-2 py-0.5 ${
                      d.status === 'FILLED'
                        ? 'bg-nofx-success/20 text-nofx-success'
                        : d.status === 'BLOCKED'
                          ? 'bg-nofx-danger/20 text-nofx-danger'
                          : 'bg-nofx-bg-lighter text-nofx-text-muted'
                    }`}
                  >
                    {d.status}
                  </span>
                  {d.outcome && (
                    <span
                      className={`rounded px-2 py-0.5 font-semibold ${
                        d.outcome === 'HIT'
                          ? 'bg-nofx-success/20 text-nofx-success'
                          : 'bg-nofx-danger/20 text-nofx-danger'
                      }`}
                    >
                      {d.outcome}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function StatTile({
  label,
  value,
  sublabel,
  tone = 'neutral',
}: {
  label: string
  value: string
  sublabel?: string
  tone?: 'neutral' | 'green' | 'red' | 'yellow'
}) {
  const toneClass =
    tone === 'green'
      ? 'text-nofx-success'
      : tone === 'red'
        ? 'text-nofx-danger'
        : tone === 'yellow'
          ? 'text-nofx-gold'
          : 'text-nofx-text'

  return (
    <div className="bg-nofx-bg-lighter p-4 text-center">
      <div className="text-xs text-nofx-text-muted">{label}</div>
      <div className={`mt-1 text-xl font-semibold ${toneClass}`}>{value}</div>
      {sublabel && (
        <div className="mt-1 text-xs text-nofx-text-muted">{sublabel}</div>
      )}
    </div>
  )
}
