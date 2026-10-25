// ALG-3418: AlgoBots Studio backtests. The draft id comes from the NoFX
// strategy's `studio.draft_id`; the backend runs the draft's compiled artifact
// on a frozen KXBTC15M recorder dataset in a Nautilus BacktestEngine.
import { API_BASE, httpClient } from './helpers'

export interface BacktestDataset {
  id: string
  name: string
  source: string
  sha256: string
  rows: number
  first_event: string
  last_event: string
  start: string
  end: string
}

export interface BacktestMetrics {
  intervals: number
  scored: number
  filled: number
  abstain: number
  blocked: number
  wins: number
  starting_equity: string
  ending_equity: string
  pnl: string
  fees: string
  max_drawdown: string
  hit_rate: number | null
  brier: number | null
  px_sources: Record<string, number>
  blocked_by: Record<string, number>
}

export interface StudioBacktest {
  id: string
  draft_id: string
  draft_revision: number
  artifact: {
    artifact_hash: string
    implementation: string
    compiler_version: string
    strategy_id: string
  }
  dataset: BacktestDataset
  executor: string
  metrics: BacktestMetrics
  equity_curve: { ts: number; event: string; equity: string }[]
  created_at: string
}

// A Nautilus run over the whole recorder takes tens of seconds.
const BACKTEST_TIMEOUT_MS = 240_000

function detail(r: { message?: string; errorData?: any }) {
  const d = r.errorData?.detail
  if (d && typeof d === 'object' && d.message) return `${d.field}: ${d.message}`
  if (typeof d === 'string') return d
  return r.message || 'Backtest failed'
}

export const studioBacktestApi = {
  run: async (draftId: string, datasetId?: string) => {
    const r = await httpClient.request<StudioBacktest>(
      `${API_BASE}/studio/strategies/${draftId}/backtest`,
      {
        method: 'POST',
        data: datasetId ? { dataset_id: datasetId } : {},
        timeout: BACKTEST_TIMEOUT_MS,
      }
    )
    if (!r.success || !r.data) throw new Error(detail(r))
    return r.data
  },
  list: async (draftId: string) => {
    const r = await httpClient.get<{ backtests: StudioBacktest[] }>(
      `${API_BASE}/studio/strategies/${draftId}/backtests`
    )
    if (!r.success || !r.data) throw new Error(detail(r))
    return r.data.backtests
  },
}
