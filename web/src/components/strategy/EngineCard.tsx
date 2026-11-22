import { useCallback, useEffect, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  Ban,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  Save,
  Settings,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_BASE || ''

export interface EngineParams {
  qty: number
  windowTiming: 'begin' | 'middle' | 'end'
  series: '15m' | '5m'
}

interface WorkerState {
  account: string
  state: 'ready' | 'stale' | 'unavailable'
  positions?: Array<{
    instrument: string
    side: string
    qty: string
    avg_price: string
    unrealized_pnl: string | null
  }>
  funds?: {
    strategy_pnl: string
    equity: string
  }
  orders_submitted?: number
  orders_filled?: number
  open_positions?: number
}

interface Decision {
  decision_id: string
  strategy: string
  instrument_id: string
  side: 'YES' | 'NO'
  status: string
  decided_at: string
  reason: string
  execution?: string
  outcome?: 'HIT' | 'MISS' | null
  risk_blocked?: boolean
  receipt?: {
    client_order_id: string
    trade_id: string
  } | null
}

interface FleetBreakerState {
  state: 'open' | 'closed'
  reason: string
  updated_at: string | null
}

interface Props {
  token: string | null
  engineName: string
  engineLabel: string
  engineDescription: string
  strategyId: string | null
  isBenched?: boolean
  defaultParams?: EngineParams
  onError?: (message: string) => void
}

export function EngineCard({
  token,
  engineName,
  engineLabel,
  engineDescription,
  strategyId,
  isBenched = false,
  defaultParams,
  onError,
}: Props) {
  const [enabled, setEnabled] = useState(false)
  const [_deploymentId, setDeploymentId] = useState<string | null>(null)
  const [params, setParams] = useState<EngineParams>(
    defaultParams || {
      qty: 1,
      windowTiming: 'middle',
      series: '15m',
    }
  )
  const [savedParams, setSavedParams] = useState<EngineParams | null>(null)
  const [worker, setWorker] = useState<WorkerState | null>(null)
  const [decisions, setDecisions] = useState<Decision[]>([])
  const [fleetBreaker, setFleetBreaker] = useState<FleetBreakerState | null>(
    null
  )
  const [blockedReasons, setBlockedReasons] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [toggling, setToggling] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showSettings, setShowSettings] = useState(false)

  const hasUnsavedChanges =
    savedParams !== null &&
    (params.qty !== savedParams.qty ||
      params.windowTiming !== savedParams.windowTiming ||
      params.series !== savedParams.series)

  const fetchFleetBreaker = useCallback(async () => {
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/api/deployments/fleet/breaker`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setFleetBreaker(data)
      }
    } catch {
      // Fleet breaker fetch is non-critical
    }
  }, [token])

  const fetchLive = useCallback(async () => {
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/api/nofx/studio/live`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error('Failed to fetch live data')
      const data = await res.json()

      // Find this engine's worker
      const engineWorker = (data.workers || []).find(
        (w: WorkerState) => w.account === engineName
      )
      setWorker(engineWorker || null)

      // Find this engine's decisions and extract blocked reasons
      const engineDecisions = (data.decisions || []).filter(
        (d: Decision) => d.strategy === engineName
      )
      setDecisions(engineDecisions)

      const blocked = engineDecisions
        .filter((d: Decision) => d.risk_blocked || d.execution === 'BLOCKED')
        .map((d: Decision) => d.reason)
        .filter((r: string) => r) as string[]
      setBlockedReasons([...new Set(blocked)])

      // Find deployment for this engine
      const engineDeployment = (data.deployments || []).find(
        (d: { strategy?: string; deployment_id?: string; status?: string }) =>
          d.strategy?.toLowerCase().includes(engineName)
      )
      if (engineDeployment) {
        setDeploymentId(engineDeployment.deployment_id)
        setEnabled(engineDeployment.status === 'running')
      } else {
        setDeploymentId(null)
        setEnabled(engineWorker?.state === 'ready')
      }
    } catch (err) {
      onError?.(err instanceof Error ? err.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [token, engineName, onError])

  useEffect(() => {
    fetchLive()
    fetchFleetBreaker()
    const interval = setInterval(fetchLive, 15000)
    return () => clearInterval(interval)
  }, [fetchLive, fetchFleetBreaker])

  // Load strategy params if strategyId provided
  useEffect(() => {
    if (!token || !strategyId) return
    const loadStrategy = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/nofx/strategies/${strategyId}`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (res.ok) {
          const data = await res.json()
          const baseline = data.config?.baseline
          if (baseline) {
            const loaded: EngineParams = {
              qty: baseline.qty || baseline.contracts || 1,
              windowTiming: baseline.window_timing || baseline.entry_timing || 'middle',
              series: baseline.series || '15m',
            }
            setParams(loaded)
            setSavedParams(loaded)
          }
        }
      } catch {
        // Strategy load is non-critical
      }
    }
    loadStrategy()
  }, [token, strategyId])

  const handleToggle = async () => {
    if (!strategyId) {
      onError?.(`No ${engineLabel} strategy configured`)
      return
    }
    setToggling(true)
    try {
      if (enabled) {
        // Deactivate: get default config and PUT to reset
        const defaultRes = await fetch(
          `${API_BASE}/api/nofx/strategies/default-config?template=${engineName}`,
          { headers: { Authorization: `Bearer ${token}` } }
        )
        if (!defaultRes.ok) throw new Error('Failed to get default config')
        const defaultConfig = await defaultRes.json()

        const res = await fetch(`${API_BASE}/api/nofx/strategies/${strategyId}`, {
          method: 'PUT',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ config: defaultConfig }),
        })
        if (!res.ok) throw new Error('Failed to deactivate')
        setEnabled(false)
      } else {
        // Activate
        const res = await fetch(
          `${API_BASE}/api/nofx/strategies/${strategyId}/activate`,
          {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}` },
          }
        )
        if (!res.ok) {
          const data = await res.json().catch(() => ({}))
          throw new Error(
            data.detail || data.error || data.message || 'Failed to activate'
          )
        }
        setEnabled(true)
      }
      await fetchLive()
    } catch (err) {
      onError?.(err instanceof Error ? err.message : 'Toggle failed')
    } finally {
      setToggling(false)
    }
  }

  const handleSaveParams = async () => {
    if (!token || !strategyId) {
      onError?.('No strategy to save')
      return
    }
    setSaving(true)
    try {
      // First get current strategy
      const getRes = await fetch(`${API_BASE}/api/nofx/strategies/${strategyId}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!getRes.ok) throw new Error('Failed to load strategy')
      const strategy = await getRes.json()

      // Update baseline params
      const config = strategy.config || {}
      config.baseline = {
        ...config.baseline,
        strategy: engineName,
        qty: params.qty,
        contracts: params.qty,
        window_timing: params.windowTiming,
        entry_timing: params.windowTiming,
        series: params.series,
      }

      // Save
      const res = await fetch(`${API_BASE}/api/nofx/strategies/${strategyId}`, {
        method: 'PUT',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: strategy.name,
          config,
        }),
      })
      if (!res.ok) throw new Error('Failed to save parameters')
      setSavedParams({ ...params })
    } catch (err) {
      onError?.(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const recentDecisions = decisions.slice(0, 5)
  const ordersTotal = worker?.orders_submitted || decisions.length
  const fillsTotal =
    worker?.orders_filled ||
    decisions.filter((d) => d.execution === 'FILLED').length
  const hitRate = (() => {
    const settled = decisions.filter((d) => d.outcome !== null)
    const hits = settled.filter((d) => d.outcome === 'HIT').length
    return settled.length > 0 ? (hits / settled.length) * 100 : 0
  })()
  const equity = worker?.funds?.equity || null
  const pnl = worker?.funds?.strategy_pnl || null
  const isFleetBreakered = fleetBreaker?.state === 'open'

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-[rgba(25,36,52,0.14)] bg-nofx-bg-lighter">
        <Loader2 className="h-6 w-6 animate-spin text-nofx-gold" />
      </div>
    )
  }

  return (
    <div
      className={`rounded-lg border bg-nofx-bg-lighter ${
        isBenched
          ? 'border-nofx-text-muted/30 opacity-60'
          : 'border-[rgba(25,36,52,0.14)]'
      }`}
    >
      <div className="flex items-center justify-between border-b border-[rgba(25,36,52,0.14)] p-4">
        <div className="flex items-center gap-3">
          <div
            className={`flex h-10 w-10 items-center justify-center rounded-lg ${
              isBenched
                ? 'bg-nofx-bg-deeper text-nofx-text-muted'
                : enabled
                  ? 'bg-nofx-success/20 text-nofx-success'
                  : 'bg-nofx-bg-deeper text-nofx-text-muted'
            }`}
          >
            {isBenched ? (
              <Ban className="h-5 w-5" />
            ) : (
              <Activity className="h-5 w-5" />
            )}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold text-nofx-text">
                {engineLabel}
              </h3>
              {isBenched && (
                <span className="rounded bg-nofx-text-muted/20 px-2 py-0.5 text-xs text-nofx-text-muted">
                  Benched
                </span>
              )}
            </div>
            <p className="mt-0.5 text-xs text-nofx-text-muted">
              {engineDescription}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {!isBenched && (
            <>
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
                <RefreshCw
                  className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`}
                />
              </button>
              <button
                type="button"
                onClick={handleToggle}
                disabled={toggling || !strategyId || isFleetBreakered}
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
                {enabled ? 'Stop' : 'Start'}
              </button>
            </>
          )}
        </div>
      </div>

      {showSettings && !isBenched && (
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
                {[1, 2, 5, 10, 20].map((q) => (
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
          <div className="mt-4 flex items-center justify-between">
            <p className="text-xs text-nofx-text-muted">
              Window timing affects results — beginning has different market
              conditions than end of window.
            </p>
            <button
              type="button"
              onClick={handleSaveParams}
              disabled={saving || !hasUnsavedChanges}
              className="inline-flex items-center gap-2 rounded-lg bg-nofx-gold px-3 py-2 text-sm font-semibold text-nofx-bg disabled:opacity-50"
            >
              {saving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Save
            </button>
          </div>
          {hasUnsavedChanges && (
            <p className="mt-2 text-xs text-nofx-gold">Unsaved changes</p>
          )}
        </div>
      )}

      {/* Fleet breaker warning */}
      {isFleetBreakered && (
        <div className="border-b border-nofx-danger/30 bg-nofx-danger/10 px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-nofx-danger">
            <AlertTriangle className="h-4 w-4" />
            <span className="font-semibold">Fleet Breaker Active</span>
            {fleetBreaker?.reason && (
              <span className="text-nofx-danger/80">
                — {fleetBreaker.reason}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Blocked reasons */}
      {blockedReasons.length > 0 && (
        <div className="border-b border-nofx-gold/30 bg-nofx-gold/10 px-4 py-3">
          <div className="text-xs font-semibold text-nofx-gold">
            Blocked entries:
          </div>
          {blockedReasons.map((reason, i) => (
            <div key={i} className="mt-1 text-xs text-nofx-gold/80">
              {reason}
            </div>
          ))}
        </div>
      )}

      {/* Stats grid */}
      <div className="grid gap-px bg-[rgba(25,36,52,0.14)] sm:grid-cols-5">
        <StatTile
          label="Orders"
          value={ordersTotal.toString()}
          sublabel="total"
        />
        <StatTile
          label="Fills"
          value={fillsTotal.toString()}
          sublabel="executed"
        />
        <StatTile
          label="Hit Rate"
          value={hitRate > 0 ? `${hitRate.toFixed(1)}%` : '—'}
          sublabel="settled"
          tone={hitRate >= 50 ? 'green' : hitRate > 0 ? 'red' : 'neutral'}
        />
        <StatTile
          label="Equity"
          value={equity ? `$${parseFloat(equity).toFixed(2)}` : '—'}
          sublabel="current"
          tone="cyan"
        />
        <StatTile
          label="P&L"
          value={pnl ? `${parseFloat(pnl) >= 0 ? '+' : ''}$${parseFloat(pnl).toFixed(2)}` : '—'}
          sublabel="strategy"
          tone={pnl ? (parseFloat(pnl) >= 0 ? 'green' : 'red') : 'neutral'}
        />
      </div>

      {/* Worker status */}
      {worker && (
        <div className="border-t border-[rgba(25,36,52,0.14)] px-4 py-2">
          <div className="flex items-center gap-2 text-xs">
            <span
              className={`h-2 w-2 rounded-full ${
                worker.state === 'ready'
                  ? 'bg-nofx-success'
                  : worker.state === 'stale'
                    ? 'bg-nofx-gold'
                    : 'bg-nofx-danger'
              }`}
            />
            <span className="text-nofx-text-muted">
              Worker:{' '}
              <span className="font-mono text-nofx-text">{worker.state}</span>
            </span>
            {worker.open_positions !== undefined && worker.open_positions > 0 && (
              <span className="text-nofx-text-muted">
                · {worker.open_positions} open position
                {worker.open_positions > 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Recent decisions */}
      {recentDecisions.length > 0 && !isBenched && (
        <div className="p-4">
          <h4 className="mb-3 text-sm font-semibold text-nofx-text">
            Recent Decisions
          </h4>
          <div className="space-y-2">
            {recentDecisions.map((d, i) => (
              <div
                key={`${d.decision_id}-${i}`}
                className="flex items-center justify-between rounded-md bg-nofx-bg-deeper px-3 py-2 text-sm"
              >
                <div className="flex items-center gap-3">
                  {d.side === 'YES' ? (
                    <TrendingUp className="h-4 w-4 text-nofx-success" />
                  ) : (
                    <TrendingDown className="h-4 w-4 text-nofx-danger" />
                  )}
                  <span className="font-mono text-nofx-text">
                    {d.instrument_id}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs">
                  <span
                    className={`rounded px-2 py-0.5 ${
                      d.execution === 'FILLED'
                        ? 'bg-nofx-success/20 text-nofx-success'
                        : d.risk_blocked || d.execution === 'BLOCKED'
                          ? 'bg-nofx-danger/20 text-nofx-danger'
                          : 'bg-nofx-bg-lighter text-nofx-text-muted'
                    }`}
                  >
                    {d.risk_blocked ? 'BLOCKED' : d.execution || d.status}
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
  tone?: 'neutral' | 'green' | 'red' | 'yellow' | 'cyan'
}) {
  const toneClass =
    tone === 'green'
      ? 'text-nofx-success'
      : tone === 'red'
        ? 'text-nofx-danger'
        : tone === 'yellow'
          ? 'text-nofx-gold'
          : tone === 'cyan'
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

export default EngineCard
