// ALG-3418: the Studio Backtest button. Runs the strategy's compiled artifact
// through /api/studio/strategies/{draft_id}/backtest and renders the stored
// result: P&L, hit rate, Brier and the Nautilus equity curve, tied to the
// named frozen dataset it ran on.
import { useEffect, useState } from 'react'
import { FlaskConical, Loader2 } from 'lucide-react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { StudioCompileStatus } from '../../types'
import {
  studioBacktestApi,
  type StudioBacktest,
  type WarehouseSnapshot,
} from '../../lib/api/studioBacktest'

const pct = (x: number | null) => (x == null ? '—' : `${(x * 100).toFixed(1)}%`)

function Stat({
  label,
  value,
  testId,
}: {
  label: string
  value: string
  testId: string
}) {
  return (
    <div className="rounded-md bg-nofx-bg-deeper px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-wide text-nofx-text-muted">
        {label}
      </div>
      <div data-testid={testId} className="font-mono text-sm text-nofx-text">
        {value}
      </div>
    </div>
  )
}

export function StudioBacktestResult({ result }: { result: StudioBacktest }) {
  const m = result.metrics
  const pnl = Number(m.pnl)
  const points = result.equity_curve.map((p) => ({
    ts: p.ts,
    equity: Number(p.equity),
  }))
  return (
    <div data-testid="studio-backtest-result" className="mt-2 space-y-2">
      <div className="text-nofx-text-muted">
        Dataset{' '}
        <span data-testid="studio-backtest-dataset" className="text-nofx-text">
          {result.dataset.name}
        </span>{' '}
        · <code title={result.dataset.sha256}>{result.dataset.id}</code> ·
        artifact{' '}
        <code title={result.artifact.artifact_hash}>
          {result.artifact.artifact_hash.slice(0, 12)}
        </code>{' '}
        · {result.executor}
      </div>
      {result.evidence && (
        <a
          href={result.evidence.notebook_url}
          target="_blank"
          rel="noopener noreferrer"
          data-testid="studio-view-evidence"
          className="text-nofx-accent underline"
        >
          View evidence
        </a>
      )}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat
          label="P&L (USD)"
          testId="studio-backtest-pnl"
          value={`${pnl > 0 ? '+' : ''}${m.pnl}`}
        />
        <Stat
          label="Hit rate"
          testId="studio-backtest-hit-rate"
          value={`${pct(m.hit_rate)} (${m.wins}/${m.filled})`}
        />
        <Stat
          label="Brier"
          testId="studio-backtest-brier"
          value={m.brier == null ? '—' : m.brier.toFixed(3)}
        />
        <Stat
          label="Max drawdown"
          testId="studio-backtest-drawdown"
          value={m.max_drawdown}
        />
      </div>
      <div className="text-nofx-text-muted">
        {m.intervals} intervals · {m.filled} filled · {m.abstain} abstained ·{' '}
        {m.blocked} blocked
        {Object.keys(m.blocked_by || {}).length
          ? ` (${Object.entries(m.blocked_by)
              .map(([k, v]) => `${k} ${v}`)
              .join(', ')})`
          : ''}{' '}
        · fees {m.fees} · equity {m.starting_equity} → {m.ending_equity}
      </div>
      <figure aria-label="Backtest equity curve">
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={points} accessibilityLayer>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="ts"
              type="number"
              domain={['dataMin', 'dataMax']}
              tickFormatter={(ts) =>
                new Date(ts * 1000).toISOString().slice(5, 16).replace('T', ' ')
              }
            />
            <YAxis domain={['auto', 'auto']} />
            <Tooltip
              labelFormatter={(ts) => new Date(Number(ts) * 1000).toISOString()}
            />
            <Line
              dataKey="equity"
              stroke="#19836b"
              dot={points.length === 1}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </figure>
    </div>
  )
}

export function StudioBacktestPanel({
  studio,
  stale,
}: {
  studio?: StudioCompileStatus | null
  stale: boolean
}) {
  const draftId = studio?.status === 'compiled' ? studio.draft_id : null
  const hash = studio?.artifact_hash
  const [result, setResult] = useState<StudioBacktest | null>(null)
  const [snapshots, setSnapshots] = useState<WarehouseSnapshot[]>([])
  const [snapshotId, setSnapshotId] = useState('')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setResult(null)
    setError(null)
    setSnapshots([])
    setSnapshotId('')
    if (!draftId) return
    let live = true
    studioBacktestApi
      .snapshots(draftId)
      .then((rows) => {
        if (live) {
          setSnapshots(rows)
          setSnapshotId(rows[rows.length - 1]?.snapshot_id || '')
        }
      })
      .catch((e) => {
        if (live)
          setError(e instanceof Error ? e.message : 'Snapshot discovery failed')
      })
    studioBacktestApi
      .list(draftId)
      .then((rows) => {
        if (live)
          setResult(rows.find((r) => r.artifact.artifact_hash === hash) || null)
      })
      .catch(() => undefined)
    return () => {
      live = false
    }
  }, [draftId, hash])

  const run = async () => {
    if (!draftId || !snapshotId) return
    setRunning(true)
    setError(null)
    try {
      setResult(await studioBacktestApi.run(draftId, snapshotId))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Backtest failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div
      data-testid="studio-backtest-panel"
      className="mt-3 rounded-lg border border-[rgba(26,24,19,0.14)] px-3 py-2 text-xs"
    >
      <div className="flex flex-wrap items-center gap-3">
        <label>
          Warehouse snapshot{' '}
          <select
            aria-label="Warehouse snapshot"
            value={snapshotId}
            disabled={running || stale}
            onChange={(event) => setSnapshotId(event.target.value)}
          >
            {!snapshots.length && (
              <option value="">No published snapshots</option>
            )}
            {snapshots.map((snapshot) => (
              <option key={snapshot.snapshot_id} value={snapshot.snapshot_id}>
                {snapshot.instrument_id} · {snapshot.snapshot_id} ·{' '}
                {snapshot.row_count} rows
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          data-testid="studio-backtest-button"
          onClick={run}
          disabled={!draftId || !snapshotId || stale || running}
          className="inline-flex items-center gap-1.5 rounded-lg bg-nofx-gold px-3 py-1.5 text-sm font-semibold text-nofx-bg disabled:cursor-not-allowed disabled:opacity-45"
        >
          {running ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FlaskConical className="h-4 w-4" />
          )}
          {running ? 'Backtesting…' : 'Backtest'}
        </button>
        <span className="text-nofx-text-muted">
          {!draftId
            ? 'Save a valid config to compile it before a backtest.'
            : stale
              ? 'Save first: the backtest runs the compiled artifact.'
              : 'Nautilus BacktestEngine · selected warehouse snapshot · paper'}
        </span>
      </div>
      {error ? (
        <div
          role="alert"
          data-testid="studio-backtest-error"
          className="mt-2 text-nofx-danger"
        >
          {error}
        </div>
      ) : null}
      {result ? <StudioBacktestResult result={result} /> : null}
    </div>
  )
}
