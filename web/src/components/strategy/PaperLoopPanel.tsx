import { useCallback, useEffect, useState } from 'react'
import { Copy, KeyRound, Loader2, RefreshCw, ShieldOff } from 'lucide-react'
import { notify } from '../../lib/notify'
import {
  paperLoopApi,
  type FeedStatus,
  type FunderInvite,
  type LoopDecision,
  type PaperLoopLive,
  type StudioMe,
} from '../../lib/api/paperLoop'

// ALG-3414: the funder view of the running loop. Everything here is read from
// the AlgoBots backend: Kalshi observer rows, the decision log with its risk
// verdicts, and the Nautilus paper-fill receipts from the worker heartbeats.
// Missing or stale inputs are labelled as such; nothing is filled in.

const POLL_MS = 20_000
const CARD =
  'rounded-lg border border-[rgba(26,24,19,0.14)] bg-nofx-bg-lighter p-4'

function utc(ts?: number | null) {
  if (!ts) return '—'
  return new Date(ts * 1000).toISOString().replace('T', ' ').slice(0, 19) + 'Z'
}

function age(s?: number) {
  if (s === undefined) return ''
  if (s < 90) return `${Math.round(s)}s ago`
  if (s < 5400) return `${Math.round(s / 60)} min ago`
  return `${(s / 3600).toFixed(1)} h ago`
}

function Badge({
  tone,
  children,
}: {
  tone: 'ok' | 'warn' | 'bad' | 'muted'
  children: React.ReactNode
}) {
  const cls = {
    ok: 'bg-nofx-success/15 text-nofx-success',
    warn: 'bg-nofx-gold/20 text-nofx-gold',
    bad: 'bg-red-500/15 text-red-600',
    muted: 'bg-[rgba(26,24,19,0.08)] text-nofx-text-muted',
  }[tone]
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${cls}`}
    >
      {children}
    </span>
  )
}

function stateTone(state: string): 'ok' | 'warn' | 'bad' | 'muted' {
  if (state === 'live' || state === 'ready') return 'ok'
  if (state === 'stale' || state === 'reconciling') return 'warn'
  if (state === 'unavailable') return 'bad'
  return 'muted'
}

function FeedCard({ feed }: { feed: FeedStatus }) {
  return (
    <div className={CARD} data-testid="feed-card">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-nofx-text">
        Kalshi market feed{' '}
        <Badge tone={stateTone(feed.state)}>{feed.state}</Badge>
      </div>
      <div className="text-xs text-nofx-text-muted">{feed.source}</div>
      {feed.state === 'unavailable' ? (
        <div className="mt-2 text-sm text-red-600">{feed.reason}</div>
      ) : (
        <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-nofx-text">
          <span className="text-nofx-text-muted">Last observation</span>
          <span data-testid="feed-ts">
            {utc(feed.last_observed_ts)} ({age(feed.age_s)})
          </span>
          <span className="text-nofx-text-muted">Market</span>
          <span>{feed.market || feed.event}</span>
          <span className="text-nofx-text-muted">Strike</span>
          <span>{feed.strike ?? '—'}</span>
          <span className="text-nofx-text-muted">YES bid / ask</span>
          <span>
            {feed.yes_bid ?? '—'} / {feed.yes_ask ?? '—'}
          </span>
          {feed.reason ? (
            <span className="col-span-2 text-nofx-gold">{feed.reason}</span>
          ) : null}
        </div>
      )}
    </div>
  )
}

function ExecutionCell({ d }: { d: LoopDecision }) {
  if (d.risk_blocked) {
    return <Badge tone="warn">risk blocked</Badge>
  }
  if (d.execution === 'FILLED') return <Badge tone="ok">paper fill</Badge>
  return <Badge tone="muted">{(d.execution || '—').toLowerCase()}</Badge>
}

function ReceiptCell({ d }: { d: LoopDecision }) {
  if (d.risk_blocked) {
    return <span className="text-nofx-gold">{d.reason}</span>
  }
  const r = d.receipt
  if (d.execution === 'FILLED' && !r) {
    return (
      <span className="text-nofx-text-muted">
        receipt not in the worker's recent window
      </span>
    )
  }
  if (!r) return <span className="text-nofx-text-muted">{d.reason || '—'}</span>
  if (r.kind === 'position') {
    return (
      <span className="font-mono text-xs">
        Nautilus position {r.instrument} · {r.qty} @ {r.avg_price}
      </span>
    )
  }
  return (
    <span className="font-mono text-xs" data-testid="receipt">
      {r.client_order_id} · {r.trade_id} · {r.qty} @ {r.px}
    </span>
  )
}

function InvitesCard() {
  const [invites, setInvites] = useState<FunderInvite[]>([])
  const [minted, setMinted] = useState<FunderInvite | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setInvites(await paperLoopApi.invites())
    } catch (err) {
      notify.error(err instanceof Error ? err.message : 'Invites unavailable')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const mint = async () => {
    setBusy(true)
    try {
      setMinted(await paperLoopApi.mintInvite())
      await load()
    } catch (err) {
      notify.error(err instanceof Error ? err.message : 'Mint failed')
    } finally {
      setBusy(false)
    }
  }

  const revoke = async (inv: FunderInvite) => {
    try {
      await paperLoopApi.revokeInvite(inv.id)
      if (minted?.id === inv.id) setMinted(null)
      await load()
      notify.success(
        inv.claimed_by ? 'Funder access revoked' : 'Invite revoked'
      )
    } catch (err) {
      notify.error(err instanceof Error ? err.message : 'Revoke failed')
    }
  }

  const registerUrl = `${window.location.origin}/register`

  return (
    <div className={CARD} data-testid="invites-card">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="text-sm font-semibold text-nofx-text">
          Funder invites (owner only)
        </div>
        <button
          type="button"
          onClick={mint}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-lg bg-nofx-gold px-3 py-1.5 text-xs font-semibold text-nofx-bg hover:bg-nofx-gold-highlight"
        >
          {busy ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <KeyRound className="h-3.5 w-3.5" />
          )}
          Mint funder invite
        </button>
      </div>
      {minted?.code ? (
        <div
          className="mb-3 rounded-lg border border-nofx-gold/40 bg-nofx-gold/10 p-3 text-sm text-nofx-text"
          data-testid="minted-invite"
        >
          <div className="mb-1 font-semibold">
            New single-use invite — shown once, expires{' '}
            {minted.expires_at.slice(0, 10)}
          </div>
          <div className="flex items-center gap-2">
            <code
              className="break-all font-mono text-xs"
              data-testid="minted-code"
            >
              {minted.code}
            </code>
            <button
              type="button"
              onClick={() => {
                void navigator.clipboard?.writeText(minted.code || '')
                notify.success('Invite code copied')
              }}
              className="rounded p-1 hover:bg-nofx-gold/20"
              title="Copy invite code"
            >
              <Copy className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="mt-1 text-xs text-nofx-text-muted">
            Send the funder {registerUrl} and this code over a private channel.
            They choose their own password; the code cannot be reused.
          </div>
        </div>
      ) : null}
      <table className="w-full text-left text-xs">
        <thead className="text-nofx-text-muted">
          <tr>
            <th className="py-1">Invite</th>
            <th>State</th>
            <th>Funder</th>
            <th>Expires</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {invites.map((inv) => (
            <tr key={inv.id} className="border-t border-[rgba(26,24,19,0.08)]">
              <td className="py-1 font-mono">{inv.code_hint}</td>
              <td>
                <Badge
                  tone={
                    inv.state === 'active' || inv.state === 'open'
                      ? 'ok'
                      : 'muted'
                  }
                >
                  {inv.state}
                </Badge>
              </td>
              <td>{inv.claimed_by?.email || '—'}</td>
              <td>{inv.expires_at.slice(0, 10)}</td>
              <td className="text-right">
                {inv.state === 'open' || inv.state === 'active' ? (
                  <button
                    type="button"
                    onClick={() => void revoke(inv)}
                    className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-red-600 hover:bg-red-500/10"
                  >
                    <ShieldOff className="h-3 w-3" /> Revoke
                  </button>
                ) : null}
              </td>
            </tr>
          ))}
          {invites.length === 0 ? (
            <tr>
              <td colSpan={5} className="py-2 text-nofx-text-muted">
                No invites minted yet.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  )
}

export function PaperLoopPanel() {
  const [live, setLive] = useState<PaperLoopLive | null>(null)
  const [me, setMe] = useState<StudioMe | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      setLive(await paperLoopApi.live())
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Paper loop unavailable')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void paperLoopApi
      .me()
      .then(setMe)
      .catch(() => setMe(null))
    void refresh()
    const id = window.setInterval(() => void refresh(), POLL_MS)
    return () => window.clearInterval(id)
  }, [refresh])

  return (
    <section className="space-y-3" data-testid="paper-loop-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold text-nofx-text">
            Live paper loop
          </h2>
          <Badge tone="warn">paper</Badge>
          <Badge tone="warn">sandbox · no real money</Badge>
        </div>
        <div className="flex items-center gap-2 text-xs text-nofx-text-muted">
          {live ? `as of ${utc(live.as_of)}` : null}
          <button
            type="button"
            onClick={() => void refresh()}
            className="rounded p-1 hover:bg-[rgba(26,24,19,0.08)]"
            title="Refresh"
          >
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>
      {live ? (
        <p className="text-xs text-nofx-text-muted">
          {live.environment.execution}. Market data:{' '}
          {live.environment.market_data}. Decisions below are the strategies'
          own logged calls; fills are the Nautilus paper venue's receipts.
        </p>
      ) : null}
      {error ? (
        <div className={`${CARD} text-sm text-red-600`}>
          Paper loop unavailable: {error}
        </div>
      ) : null}
      {live ? (
        <>
          <div className="grid gap-3 md:grid-cols-2">
            <FeedCard feed={live.feed} />
            <div className={CARD} data-testid="workers-card">
              <div className="mb-2 text-sm font-semibold text-nofx-text">
                Nautilus paper workers
              </div>
              <table className="w-full text-left text-xs">
                <thead className="text-nofx-text-muted">
                  <tr>
                    <th className="py-1">Strategy</th>
                    <th>State</th>
                    <th>Venue account</th>
                    <th>Fills</th>
                    <th>Equity</th>
                  </tr>
                </thead>
                <tbody>
                  {live.workers.map((w) => (
                    <tr
                      key={w.account}
                      className="border-t border-[rgba(26,24,19,0.08)]"
                    >
                      <td className="py-1 font-semibold">{w.account}</td>
                      <td>
                        <Badge tone={stateTone(w.state)}>{w.state}</Badge>{' '}
                        <span className="text-nofx-text-muted">
                          {age(w.heartbeat_age_s)}
                        </span>
                      </td>
                      <td className="font-mono">{w.venue_account_id || '—'}</td>
                      <td>{w.orders_filled ?? '—'}</td>
                      <td>{w.funds?.equity ? `$${w.funds.equity}` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="mt-2 text-xs text-nofx-text-muted">
                Decisions logged: {live.counts.logged_total} · settled:{' '}
                {live.counts.settled}
                {live.decisions_error ? ` · ${live.decisions_error}` : ''}
              </div>
            </div>
          </div>
          <div className={CARD} data-testid="decisions-card">
            <div className="mb-2 text-sm font-semibold text-nofx-text">
              Decisions → Nautilus receipts
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-nofx-text-muted">
                  <tr>
                    <th className="py-1">Decided (UTC)</th>
                    <th>Strategy</th>
                    <th>Kalshi event</th>
                    <th>Side</th>
                    <th>Execution</th>
                    <th>Receipt / risk reason</th>
                    <th>Outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {live.decisions.map((d) => (
                    <tr
                      key={d.decision_id}
                      className="border-t border-[rgba(26,24,19,0.08)] align-top"
                      data-testid="decision-row"
                      data-execution={d.execution || ''}
                    >
                      <td className="py-1 whitespace-nowrap">
                        {(d.decided_at || '').slice(0, 19).replace('T', ' ')}
                      </td>
                      <td className="font-semibold">{d.strategy}</td>
                      <td className="font-mono">{d.event}</td>
                      <td>{d.side || '—'}</td>
                      <td>
                        <ExecutionCell d={d} />
                      </td>
                      <td className="max-w-[28rem]">
                        <ReceiptCell d={d} />
                      </td>
                      <td>
                        {d.outcome === null || d.outcome === undefined
                          ? 'open'
                          : d.outcome
                            ? 'YES settled'
                            : 'NO settled'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}
      {me?.can_mint_invites ? <InvitesCard /> : null}
    </section>
  )
}
