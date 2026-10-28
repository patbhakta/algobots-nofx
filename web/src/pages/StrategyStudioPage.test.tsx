import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StrategyStudioPage from './StrategyStudioPage'

const mocks = vi.hoisted(() => ({
  getStrategies: vi.fn(),
  createStrategy: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}))
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ token: 'test-token' }),
}))
vi.mock('../contexts/LanguageContext', () => ({
  useLanguage: () => ({ language: 'en' }),
}))
vi.mock('../lib/api', () => ({ api: mocks }))
vi.mock('../lib/notify', () => ({
  notify: { success: mocks.success, error: mocks.error },
  confirmToast: vi.fn(),
}))
vi.mock('../components/strategy/PaperLoopPanel', () => ({
  PaperLoopPanel: () => null,
}))
vi.mock('../components/strategy/StudioBacktestPanel', () => ({
  StudioBacktestPanel: () => null,
}))
vi.mock('../components/strategy/StudioDeployPanel', () => ({
  StudioDeployPanel: () => null,
}))

const config = {
  baseline: { strategy: 'coin', entry_delay_seconds: 0, stake: '10.00' },
  demo_worker: {
    min_edge: 0.02,
    max_order_value: '5.00',
    max_daily_loss: '20.00',
  },
  ai_config: {
    coin_source: { source_type: 'static', static_coins: ['KXBTC15M'] },
  },
}

describe('Add strategy flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getStrategies.mockResolvedValue([])
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => ({
        ok: true,
        json: async () =>
          url.includes('default-config') ? config : { observations: [] },
      }))
    )
  })
  it('creates the selected template and opens its editable parameters', async () => {
    mocks.createStrategy.mockImplementation(async (input) => {
      const created = {
        id: 'coin-1',
        ...input,
        studio: { status: 'compiled', artifact_hash: 'a'.repeat(64) },
      }
      mocks.getStrategies.mockResolvedValue([created])
      return created
    })
    render(<StrategyStudioPage />)
    fireEvent.click(
      await screen.findByRole('button', {
        name: /Coinflip baseline Edit entry delay/,
      })
    )
    expect(
      await screen.findByLabelText('Entry delay after market open (seconds)')
    ).toHaveValue(0)
    expect(mocks.createStrategy.mock.calls[0][0].config.baseline.strategy).toBe(
      'coin'
    )
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('template=coin'),
      expect.anything()
    )
    expect(mocks.success).toHaveBeenCalled()
  })
  it('keeps the template picker usable when creation fails', async () => {
    mocks.createStrategy.mockRejectedValue(new Error('Connection lost'))
    render(<StrategyStudioPage />)
    fireEvent.click(
      await screen.findByRole('button', {
        name: /Coinflip baseline Edit entry delay/,
      })
    )
    await waitFor(() =>
      expect(mocks.error).toHaveBeenCalledWith('Connection lost')
    )
    expect(
      screen.getByRole('button', { name: /Coinflip baseline Edit entry delay/ })
    ).toBeEnabled()
  })
})
