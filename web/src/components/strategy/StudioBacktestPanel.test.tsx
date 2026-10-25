import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { StudioBacktestPanel } from './StudioBacktestPanel'
import type { StudioBacktest } from '../../lib/api/studioBacktest'

const mocks = vi.hoisted(() => ({ run: vi.fn(), list: vi.fn(), snapshots: vi.fn() }))
vi.mock('../../lib/api/studioBacktest', () => ({
  studioBacktestApi: { run: mocks.run, list: mocks.list, snapshots: mocks.snapshots },
}))

// recharts' ResponsiveContainer needs ResizeObserver; jsdom has none.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver

const HASH = 'a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9'
const STUDIO = {
  status: 'compiled' as const,
  draft_id: 'draft-1',
  artifact_hash: HASH,
  implementation: 'kalshi_momentum.v1',
}

const RESULT: StudioBacktest = {
  id: 'bt-1',
  draft_id: 'draft-1',
  draft_revision: 2,
  artifact: {
    artifact_hash: HASH,
    implementation: 'kalshi_momentum.v1',
    compiler_version: 'studio-compiler/1',
    strategy_id: 's-1',
  },
  dataset: {
    id: 'kalshi-kxbtc15m-recorder@1496a6bf9a30',
    name: 'KXBTC15M recorder 2026-10-22 09:00 to 2026-10-23 14:45 UTC (119 settled intervals)',
    source: 'kalshi-kxbtc15m-recorder',
    sha256: '1496a6bf9a30' + '0'.repeat(52),
    rows: 119,
    first_event: 'KXBTC15M-26OCT220515',
    last_event: 'KXBTC15M-26OCT231045',
    start: '2026-10-22T09:00:00+00:00',
    end: '2026-10-23T14:45:00+00:00',
  },
  executor: 'NautilusTrader 1.231.0 BacktestEngine',
  metrics: {
    intervals: 119,
    scored: 107,
    filled: 24,
    abstain: 17,
    blocked: 78,
    wins: 8,
    starting_equity: '100.00',
    ending_equity: '57.61',
    pnl: '-42.39',
    fees: '4.18',
    max_drawdown: '45.12',
    hit_rate: 1 / 3,
    brier: 0.3314,
    px_sources: { kalshi_yes_ask: 11, kalshi_no_ask: 13 },
    blocked_by: { max_daily_loss: 78 },
  },
  equity_curve: [
    { ts: 1792660500, event: 'a', equity: '100.00' },
    { ts: 1792661400, event: 'b', equity: '97.10' },
  ],
  created_at: '2026-10-23T15:00:00+00:00',
}

describe('Studio backtest (ALG-3418)', () => {
  beforeEach(() => {
    mocks.snapshots.mockReset().mockResolvedValue([{snapshot_id: "recorder-48", instrument_id: "KXBTC15M.KALSHI", row_count: 48}])
    mocks.run.mockReset()
    mocks.list.mockReset().mockResolvedValue([])
  })

  it('runs the compiled draft and renders the result with its dataset', async () => {
    mocks.run.mockResolvedValue(RESULT)
    render(<StudioBacktestPanel studio={STUDIO} stale={false} />)
    await waitFor(() => expect(mocks.list).toHaveBeenCalledWith('draft-1'))
    await waitFor(() => expect((screen.getByTestId('studio-backtest-button') as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(screen.getByTestId('studio-backtest-button'))
    await screen.findByTestId('studio-backtest-result')
    expect(mocks.run).toHaveBeenCalledWith('draft-1', 'recorder-48')
    expect(screen.getByTestId('studio-backtest-dataset').textContent).toContain(
      '119 settled intervals'
    )
    expect(screen.getByTestId('studio-backtest-pnl').textContent).toBe('-42.39')
    expect(screen.getByTestId('studio-backtest-hit-rate').textContent).toBe(
      '33.3% (8/24)'
    )
    expect(screen.getByTestId('studio-backtest-brier').textContent).toBe(
      '0.331'
    )
    expect(screen.getByText(/max_daily_loss 78/)).toBeTruthy()
  })

  it('shows the stored result for the current artifact on load', async () => {
    mocks.list.mockResolvedValue([
      {
        ...RESULT,
        id: 'old',
        artifact: { ...RESULT.artifact, artifact_hash: 'x' },
      },
      RESULT,
    ])
    render(<StudioBacktestPanel studio={STUDIO} stale={false} />)
    await screen.findByTestId('studio-backtest-result')
    expect(mocks.run).not.toHaveBeenCalled()
  })

  it('is disabled until saved and compiled, and surfaces the owning field', async () => {
    const { rerender } = render(
      <StudioBacktestPanel studio={STUDIO} stale={true} />
    )
    expect(
      (screen.getByTestId('studio-backtest-button') as HTMLButtonElement)
        .disabled
    ).toBe(true)
    rerender(
      <StudioBacktestPanel
        studio={{ status: 'invalid', field: 'x', message: 'y' }}
        stale={false}
      />
    )
    expect(
      (screen.getByTestId('studio-backtest-button') as HTMLButtonElement)
        .disabled
    ).toBe(true)
    mocks.run.mockRejectedValue(
      new Error('signals.entry: needs an OHLC bar dataset')
    )
    rerender(<StudioBacktestPanel studio={STUDIO} stale={false} />)
    await waitFor(() => expect((screen.getByTestId('studio-backtest-button') as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(screen.getByTestId('studio-backtest-button'))
    expect(
      (await screen.findByTestId('studio-backtest-error')).textContent
    ).toBe('signals.entry: needs an OHLC bar dataset')
  })
})
