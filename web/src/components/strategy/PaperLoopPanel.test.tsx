import { act, fireEvent, render, screen, within, cleanup } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { PaperLoopPanel } from './PaperLoopPanel'
import { paperLoopApi, type PaperLoopLive } from '../../lib/api/paperLoop'
vi.mock('../../lib/api/paperLoop', () => ({ paperLoopApi: { live: vi.fn(), me: vi.fn() } }))
vi.mock('../../lib/notify', () => ({ notify: vi.fn() }))
afterEach(() => { cleanup(); vi.useRealTimers(); vi.resetAllMocks() })
function snapshot(fills = 2): PaperLoopLive {
  return { as_of: 1700000000, environment: { mode: 'paper', execution: 'sandbox', market_data: 'Kalshi' },
    viewer: { user_id: 'u', role: 'member' }, feed: { source: 'Kalshi', state: 'live' },
    workers: ['coin', 'laya'].map(account => ({ account, state: 'ready', orders_submitted: 3,
      orders_filled: fills, open_positions: 0, positions: [], funds: { strategy_pnl: '-2.30', equity: '97.70' },
      fills: [{ kind: 'fill', client_order_id: `order-${account}`, trade_id: `trade-${account}`, instrument: 'KXBTC15M.PAPER', qty: '19', px: '0.52' }] })),
    decisions: [], counts: { logged: {}, logged_total: 0, settled: 0 }, decisions_error: null }
}
it('filters worker receipts and PnL by strategy and refreshes fill counts', async () => {
  vi.useFakeTimers()
  vi.mocked(paperLoopApi.me).mockResolvedValue({ user_id: 'u', email: 'u@example.com', role: 'member', tenant_id: null, can_mint_invites: false })
  vi.mocked(paperLoopApi.live).mockResolvedValueOnce(snapshot()).mockResolvedValue(snapshot(3))
  render(<PaperLoopPanel />)
  await act(async () => { await Promise.resolve() })
  fireEvent.change(screen.getByLabelText('Paper strategy'), { target: { value: 'coin' } })
  expect(screen.queryByText('order-laya')).toBeNull()
  expect(screen.getByText('order-coin')).toBeTruthy()
  expect(screen.getByText('$-2.30')).toBeTruthy()
  expect(screen.getByText('No open positions reported.')).toBeTruthy()
  expect(within(screen.getByTestId('workers-card')).getByText('2')).toBeTruthy()
  await act(async () => { await vi.advanceTimersByTimeAsync(20000) })
  expect(within(screen.getByTestId('workers-card')).queryByText('2')).toBeNull()
  expect(paperLoopApi.live).toHaveBeenCalledTimes(2)
})
it('shows the viewer deployment orders and fills from its own node', async () => {
  vi.mocked(paperLoopApi.me).mockResolvedValue({ user_id: 'u', email: 'u@example.com', role: 'member', tenant_id: null, can_mint_invites: false })
  vi.mocked(paperLoopApi.live).mockResolvedValue({ ...snapshot(), deployments: [
    { deployment_id: '3d030739-88c1', strategy: 'owned momentum', symbol: 'KXBTC15M', status: 'running', breaker_state: 'closed',
      artifact_hash: 'bb4c4150ddae0000', node: 'deployment-3d03', fills: 1, orders: [
        { client_order_id: 'dp1-abcdef0123456789', symbol: 'KXBTC15M/USD.DEP3D03', side: 'buy', qty: '10', filled_qty: '10', status: 'filled',
          limit_px: '0.49', avg_px: '0.49', reason: null, submitted_at: '2026-10-25T22:00:28.000Z',
          fills: [{ trade_id: 't1', qty: '10', px: '0.49', ts_event: '2026-10-25T22:00:28.100Z' }] }] },
    { deployment_id: 'ffff0000-1111', strategy: 'stopped one', symbol: 'KXBTC15M', status: 'stopped', breaker_state: 'closed',
      artifact_hash: 'cc', node: 'deployment-ffff', fills: 0, orders: [] }] })
  render(<PaperLoopPanel />)
  await act(async () => { await Promise.resolve() })
  const card = screen.getByTestId('deployments-card')
  expect(within(card).getByText('owned momentum')).toBeTruthy()
  expect(within(card).getByText('10 @ 0.49')).toBeTruthy()
  expect(within(card).getByText('stopped')).toBeTruthy()
  expect(within(card).getAllByTestId('deployment-row').map(r => r.dataset.fills)).toEqual(['1', '0'])
})
