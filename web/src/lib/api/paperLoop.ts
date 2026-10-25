// ALG-3414: the AlgoBots backend's funder surface. Every call carries the
// session token from the single NoFX login; the backend re-checks the session,
// the user and the membership on each request.
import { API_BASE, httpClient } from './helpers'

export interface FeedRow {
  event: string | null
  ts: number | null
  strike: number | null
  outcome: number | null
  settle_value: string | null
  settled_ts: number | null
}

export interface FeedStatus {
  source: string
  state: 'live' | 'stale' | 'unavailable'
  reason?: string
  last_observed_ts?: number
  age_s?: number
  event?: string
  market?: string
  strike?: number
  yes_bid?: number
  yes_ask?: number
  close_ts?: number
  recent?: FeedRow[]
}

export interface FillReceipt {
  kind: 'fill' | 'position'
  client_order_id?: string
  trade_id?: string
  account_id?: string
  instrument: string
  qty: string
  px?: string
  avg_price?: string
  ts_event?: number
  opened_ts?: number
}

export interface LoopDecision {
  decision_id: string
  strategy: string
  provider: string | null
  event: string
  decided_at: string | null
  status: string | null
  side: string | null
  p_up: number | null
  reason: string | null
  execution: string | null
  risk_blocked: boolean
  qty: number | null
  fill_px: string | null
  stake: string | null
  px_source: string | null
  outcome: number | null
  receipt: FillReceipt | null
}

export interface LoopWorker {
  account: string
  state: string
  heartbeat_age_s?: number
  mode?: string
  execution?: string
  trader_id?: string
  venue_account_id?: string
  orders_submitted?: number
  orders_filled?: number
  open_positions?: number
  positions?: Array<{ instrument: string; side: string; qty: string; avg_price: string; unrealized_pnl: string | null }>
  funds?: Record<string, string> | null
  fills: FillReceipt[]
}

export interface PaperLoopLive {
  as_of: number
  environment: { mode: string; execution: string; market_data: string }
  viewer: { user_id: string; role: string }
  feed: FeedStatus
  workers: LoopWorker[]
  decisions: LoopDecision[]
  counts: {
    logged: Record<string, number>
    logged_total: number
    settled: number
  }
  decisions_error: string | null
}

export interface StudioMe {
  user_id: string
  email: string
  role: string
  tenant_id: string | null
  can_mint_invites: boolean
}

export interface FunderInvite {
  id: string
  code: string | null
  code_hint: string
  state: 'open' | 'active' | 'revoked' | 'expired'
  expires_at: string
  created_at: string
  claimed_at: string | null
  claimed_by: { user_id: string; email: string; active: boolean } | null
}

async function unwrap<T>(
  p: Promise<{ success: boolean; data?: T; message?: string }>
) {
  const r = await p
  if (!r.success || r.data === undefined) {
    throw new Error(r.message || 'Request failed')
  }
  return r.data
}

export const paperLoopApi = {
  live: () =>
    unwrap(httpClient.get<PaperLoopLive>(`${API_BASE}/nofx/studio/live`)),
  me: () => unwrap(httpClient.get<StudioMe>(`${API_BASE}/nofx/studio/me`)),
  invites: () =>
    unwrap(
      httpClient.get<{ invites: FunderInvite[] }>(
        `${API_BASE}/nofx/studio/invites`
      )
    ).then((r) => r.invites),
  mintInvite: () =>
    unwrap(httpClient.post<FunderInvite>(`${API_BASE}/nofx/studio/invites`)),
  revokeInvite: (id: string) =>
    unwrap(
      httpClient.post<FunderInvite>(
        `${API_BASE}/nofx/studio/invites/${id}/revoke`
      )
    ),
}
