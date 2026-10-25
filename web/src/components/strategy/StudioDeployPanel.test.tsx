import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { StudioDeployPanel } from './StudioDeployPanel'
import type { StudioBacktest } from '../../lib/api/studioBacktest'
import type { Deployment } from '../../lib/api/studioDeploy'

const backtestMocks = vi.hoisted(() => ({ list: vi.fn() }))
vi.mock('../../lib/api/studioBacktest', () => ({
  studioBacktestApi: { list: backtestMocks.list },
}))
const deployMocks = vi.hoisted(() => ({
  accounts: vi.fn(),
  createAccount: vi.fn(),
  create: vi.fn(),
}))
vi.mock('../../lib/api/studioDeploy', () => ({
  studioDeployApi: {
    accounts: deployMocks.accounts,
    createAccount: deployMocks.createAccount,
    create: deployMocks.create,
  },
}))

const HASH = 'a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9'
const STUDIO = {
  status: 'compiled' as const,
  draft_id: 'draft-1',
  artifact_hash: HASH,
  implementation: 'kalshi_momentum.v1',
  strategy_id: 's-1',
}

const BACKTEST: StudioBacktest = {
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
    id: 'd',
    name: 'd',
    source: 'kalshi-kxbtc15m-recorder',
    sha256: '0'.repeat(64),
    rows: 48,
    first_event: 'a',
    last_event: 'b',
    start: '2026-10-24T09:00:00+00:00',
    end: '2026-10-24T21:00:00+00:00',
  },
  executor: 'NautilusTrader 2.0.0rc6 BacktestEngine',
  metrics: {
    intervals: 48,
    scored: 40,
    filled: 9,
    abstain: 4,
    blocked: 35,
    wins: 4,
    starting_equity: '100.00',
    ending_equity: '101.50',
    pnl: '1.50',
    fees: '0.90',
    max_drawdown: '6.00',
    hit_rate: 0.44,
    brier: 0.24,
    px_sources: {},
    blocked_by: {},
  },
  equity_curve: [],
  created_at: '2026-10-25T16:00:00+00:00',
  evidence: {
    backtest_row_id: 'bt-1',
    artifact_hash: HASH,
    snapshot_id: 'recorder-48',
    dataset_sha256: '0'.repeat(64),
    notebook_url: 'http://marimo/?file=evidence/bt-1.py',
    result_sha256: '1'.repeat(64),
  },
}

const DEPLOYMENT: Deployment = {
  id: 'd0e1f2a3-1111-2222-3333-444455556666',
  strategy_id: 's-1',
  account_id: 'acc-1',
  symbol: 'KXBTC15M',
  status: 'running',
  artifact_hash: HASH,
  frozen_spec: { studio_evidence: BACKTEST.evidence },
  breaker_state: 'closed',
  effective_state: 'running',
  created_at: '2026-10-25T16:05:00+00:00',
}

describe('Studio deploy gate (ALG-3423)', () => {
  beforeEach(() => {
    backtestMocks.list.mockReset().mockResolvedValue([])
    deployMocks.accounts.mockReset().mockResolvedValue([
      { id: 'acc-1', label: 'Kalshi paper', broker: 'kalshi', mode: 'paper' },
    ])
    deployMocks.createAccount.mockReset()
    deployMocks.create.mockReset()
  })

  it('stays disabled with the gate reason until evidence for the exact hash is published', async () => {
    render(<StudioDeployPanel studio={STUDIO} stale={false} />)
    const button = await screen.findByTestId('studio-deploy-button')
    expect(button).toBeDisabled()
    expect(screen.getByTestId('studio-deploy-reason').textContent).toContain(
      'Marimo backtest evidence required'
    )
    expect(backtestMocks.list).toHaveBeenCalledWith('draft-1')
  })

  it('surfaces the backend refusal detail when the deploy is refused', async () => {
    backtestMocks.list.mockResolvedValue([BACKTEST])
    deployMocks.create.mockRejectedValue(
      new Error(
        'Marimo backtest evidence required for this exact compiled artifact; run Backtest first'
      )
    )
    render(<StudioDeployPanel studio={STUDIO} stale={false} />)
    await waitFor(() =>
      expect(screen.getByTestId('studio-deploy-button')).not.toBeDisabled()
    )
    fireEvent.click(screen.getByTestId('studio-deploy-button'))
    expect(
      (await screen.findByTestId('studio-deploy-error')).textContent
    ).toContain('Marimo backtest evidence required')
    expect(deployMocks.create).toHaveBeenCalledWith({
      strategy_id: 's-1',
      account_id: 'acc-1',
      symbol: 'KXBTC15M',
      max_order_value: '5',
      max_daily_loss: '20',
    })
  })

  it('deploys with published evidence and renders the frozen deployment', async () => {
    backtestMocks.list.mockResolvedValue([BACKTEST])
    deployMocks.create.mockResolvedValue(DEPLOYMENT)
    render(<StudioDeployPanel studio={STUDIO} stale={false} />)
    await waitFor(() =>
      expect(screen.getByTestId('studio-deploy-button')).not.toBeDisabled()
    )
    expect(
      screen.getByTestId('studio-deploy-evidence-link').getAttribute('href')
    ).toBe('http://marimo/?file=evidence/bt-1.py')
    fireEvent.click(screen.getByTestId('studio-deploy-button'))
    const result = await screen.findByTestId('studio-deploy-result')
    expect(result.textContent).toContain('d0e1f2a3')
    expect(result.textContent).toContain('running')
    expect(result.textContent).toContain('frozen evidence')
  })
})
