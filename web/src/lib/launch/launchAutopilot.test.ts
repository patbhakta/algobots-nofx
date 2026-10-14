import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ensureMarketDataStrategy,
  isBuiltInStrategyName,
  launchAutopilot,
  MARKET_DATA_STRATEGY_NAME,
} from './launchAutopilot'
import { ApiError } from '../httpClient'
import type { LaunchPreflightResult } from './types'

const mocks = vi.hoisted(() => ({
  api: {
    getTraders: vi.fn(),
    createTrader: vi.fn(),
    updateTrader: vi.fn(),
    startTrader: vi.fn(),
    getStrategies: vi.fn(),
    createStrategy: vi.fn(),
    activateStrategy: vi.fn(),
    getDefaultStrategyConfig: vi.fn(),
  },
  runLaunchPreflight: vi.fn(),
  resolveLaunchModel: vi.fn(),
  resolveLaunchExchange: vi.fn(),
}))

vi.mock('../api', () => ({ api: mocks.api }))
vi.mock('./preflight', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./preflight')>()),
  runLaunchPreflight: mocks.runLaunchPreflight,
}))
vi.mock('./resolve', () => ({
  resolveLaunchModel: mocks.resolveLaunchModel,
  resolveLaunchExchange: mocks.resolveLaunchExchange,
}))

function readyPreflight(): LaunchPreflightResult {
  return {
    ready: true,
    checks: [],
    min_ai_fee_usdc: 1,
    min_trading_usdc: 12,
    checked_at: new Date().toISOString(),
  }
}

function failedPreflight(): LaunchPreflightResult {
  return {
    ready: false,
    checks: [
      {
        id: 'ai_wallet_funds',
        status: 'failed',
        code: 'AI_WALLET_INSUFFICIENT_FUNDS',
        message: 'AI wallet needs 1 USDC.',
      },
    ],
    min_ai_fee_usdc: 1,
    min_trading_usdc: 12,
    checked_at: new Date().toISOString(),
  }
}

describe('launchAutopilot', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.resolveLaunchModel.mockResolvedValue({ id: 'model-1' })
    mocks.resolveLaunchExchange.mockResolvedValue({
      exchange: { id: 'ex-1' },
    })
    mocks.api.getTraders.mockResolvedValue([])
    mocks.api.createTrader.mockResolvedValue({
      trader_id: 't-1',
      is_running: false,
    })
    mocks.api.startTrader.mockResolvedValue(undefined)
  })

  it('never touches the strategy when preflight fails', async () => {
    mocks.runLaunchPreflight.mockResolvedValue(failedPreflight())
    const ensureStrategy = vi.fn()

    const outcome = await launchAutopilot({ ensureStrategy })

    expect(ensureStrategy).not.toHaveBeenCalled()
    expect(mocks.api.createTrader).not.toHaveBeenCalled()
    expect(outcome.ok).toBe(false)
    if (outcome.ok || outcome.kind !== 'preflight') {
      throw new Error('expected a preflight failure outcome')
    }
    expect(outcome.setupTarget).toBe('marketData')
    expect(outcome.message).toContain('AI wallet needs 1 USDC.')
  })

  it('creates and starts the trader after preflight passes', async () => {
    mocks.runLaunchPreflight.mockResolvedValue(readyPreflight())
    const ensureStrategy = vi.fn().mockResolvedValue('strat-1')

    const outcome = await launchAutopilot({
      ensureStrategy,
      scanIntervalMinutes: 15,
    })

    expect(ensureStrategy).toHaveBeenCalledTimes(1)
    expect(mocks.api.createTrader).toHaveBeenCalledWith(
      expect.objectContaining({
        strategy_id: 'strat-1',
        scan_interval_minutes: 15,
        ai_model_id: 'model-1',
        exchange_id: 'ex-1',
      })
    )
    expect(mocks.api.startTrader).toHaveBeenCalledWith('t-1')
    expect(outcome).toEqual(
      expect.objectContaining({ ok: true, traderId: 't-1' })
    )
  })

  it('updates the existing autopilot instead of creating a duplicate', async () => {
    mocks.runLaunchPreflight.mockResolvedValue(readyPreflight())
    mocks.api.getTraders.mockResolvedValue([
      {
        trader_id: 't-old',
        trader_name: 'AlgoBots Autopilot',
        is_running: false,
      },
    ])
    mocks.api.updateTrader.mockResolvedValue({
      trader_id: 't-old',
      is_running: true,
    })

    const outcome = await launchAutopilot({
      ensureStrategy: vi.fn().mockResolvedValue('strat-1'),
    })

    expect(mocks.api.updateTrader).toHaveBeenCalled()
    expect(mocks.api.createTrader).not.toHaveBeenCalled()
    expect(mocks.api.startTrader).not.toHaveBeenCalled()
    expect(outcome).toEqual(
      expect.objectContaining({ ok: true, traderId: 't-old' })
    )
  })

  it('treats a racing already-running rejection as success', async () => {
    mocks.runLaunchPreflight.mockResolvedValue(readyPreflight())
    mocks.api.getTraders.mockResolvedValue([
      {
        trader_id: 't-1',
        trader_name: 'AlgoBots Autopilot',
        is_running: false,
      },
    ])
    mocks.api.updateTrader.mockResolvedValue({
      trader_id: 't-1',
      is_running: false,
    })
    mocks.api.startTrader.mockRejectedValue(
      new ApiError(
        'Trader is already running',
        'trader.start.already_running',
        undefined,
        400
      )
    )

    const outcome = await launchAutopilot({
      ensureStrategy: vi.fn().mockResolvedValue('strat-1'),
    })

    expect(outcome).toEqual(
      expect.objectContaining({ ok: true, traderId: 't-1' })
    )
  })

  it('surfaces the server-side preflight result when start is rejected', async () => {
    mocks.runLaunchPreflight.mockResolvedValue(readyPreflight())
    mocks.api.startTrader.mockRejectedValue(
      new ApiError(
        'preflight failed',
        'trader.start.preflight_failed',
        undefined,
        400,
        { preflight: failedPreflight() }
      )
    )

    const outcome = await launchAutopilot({
      ensureStrategy: vi.fn().mockResolvedValue('strat-1'),
    })

    expect(outcome.ok).toBe(false)
    if (outcome.ok || outcome.kind !== 'preflight') {
      throw new Error('expected a preflight failure outcome')
    }
    expect(outcome.setupTarget).toBe('marketData')
  })

  // Regression (ALG-3355 rename): the trader fallback lookup matches on the
  // strategy display name. A needle that no longer matches that name silently
  // creates a second "AlgoBots Autopilot" instead of updating the first.
  it.each([
    ['current', MARKET_DATA_STRATEGY_NAME],
    ['legacy pre-rename', 'AlgoBots Claw402 Auto Strategy'],
  ])(
    'reuses a renamed autopilot trader found by its %s strategy name',
    async (_label, strategyName) => {
      mocks.runLaunchPreflight.mockResolvedValue(readyPreflight())
      mocks.api.getTraders.mockResolvedValue([
        {
          trader_id: 't-renamed',
          trader_name: 'My Renamed Bot',
          strategy_name: strategyName,
          is_running: false,
        },
      ])
      mocks.api.updateTrader.mockResolvedValue({
        trader_id: 't-renamed',
        is_running: true,
      })

      const outcome = await launchAutopilot({
        ensureStrategy: vi.fn().mockResolvedValue('strat-1'),
      })

      expect(mocks.api.updateTrader).toHaveBeenCalledWith(
        't-renamed',
        expect.objectContaining({ strategy_id: 'strat-1' })
      )
      expect(mocks.api.createTrader).not.toHaveBeenCalled()
      expect(outcome).toEqual(
        expect.objectContaining({ ok: true, traderId: 't-renamed' })
      )
    }
  )

  it('routes missing exchange setup to the hyperliquid anchor', async () => {
    mocks.resolveLaunchExchange.mockResolvedValue({
      exchange: null,
      reason: 'No Hyperliquid account is connected.',
    })

    const outcome = await launchAutopilot({ ensureStrategy: vi.fn() })

    expect(outcome).toEqual(
      expect.objectContaining({
        ok: false,
        kind: 'setup',
        setupTarget: 'hyperliquid',
      })
    )
    expect(mocks.runLaunchPreflight).not.toHaveBeenCalled()
  })
})

describe('isBuiltInStrategyName', () => {
  // The guard that makes the rename-by-substitution failure impossible to
  // repeat: whatever name the launcher creates, the lookups must find it.
  it('recognises the name the launcher actually creates', () => {
    expect(isBuiltInStrategyName(MARKET_DATA_STRATEGY_NAME)).toBe(true)
  })

  it.each([
    'AlgoBots Market Data Auto Strategy',
    'AlgoBots Claw402 Auto Strategy',
    'market-data',
    'marketData',
    'MARKET DATA',
  ])('matches %s', (name) => {
    expect(isBuiltInStrategyName(name)).toBe(true)
  })

  it.each([undefined, null, '', 'My Momentum Strategy'])(
    'does not match %s',
    (name) => {
      expect(isBuiltInStrategyName(name)).toBe(false)
    }
  )
})

describe('ensureMarketDataStrategy', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.api.activateStrategy.mockResolvedValue(undefined)
    mocks.api.getDefaultStrategyConfig.mockResolvedValue({ ai_config: {} })
  })

  it.each([
    ['current', MARKET_DATA_STRATEGY_NAME],
    ['legacy pre-rename', 'AlgoBots Claw402 Auto Strategy'],
  ])(
    'reuses the inactive built-in strategy found by its %s name',
    async (_label, name) => {
      mocks.api.getStrategies.mockResolvedValue([
        { id: 's-1', name, is_active: false, config: {} },
      ])

      expect(await ensureMarketDataStrategy()).toBe('s-1')
      expect(mocks.api.activateStrategy).toHaveBeenCalledWith('s-1')
      expect(mocks.api.createStrategy).not.toHaveBeenCalled()
    }
  )

  it('prefers the active vergex_signal strategy over a name match', async () => {
    mocks.api.getStrategies.mockResolvedValue([
      {
        id: 's-active',
        name: 'Anything At All',
        is_active: true,
        config: {
          ai_config: { coin_source: { source_type: 'vergex_signal' } },
        },
      },
      { id: 's-named', name: MARKET_DATA_STRATEGY_NAME, is_active: false },
    ])

    expect(await ensureMarketDataStrategy()).toBe('s-active')
    expect(mocks.api.activateStrategy).not.toHaveBeenCalled()
  })

  it('creates and activates the strategy when none exists', async () => {
    mocks.api.getStrategies.mockResolvedValue([])
    mocks.api.createStrategy.mockResolvedValue({ id: 's-new' })

    expect(await ensureMarketDataStrategy()).toBe('s-new')
    expect(mocks.api.createStrategy).toHaveBeenCalledWith(
      expect.objectContaining({ name: MARKET_DATA_STRATEGY_NAME })
    )
    expect(mocks.api.activateStrategy).toHaveBeenCalledWith('s-new')
  })

  // Regression: when createStrategy returns no id the launcher re-scans for the
  // strategy it just created. A needle that cannot match that name turned this
  // recovery path into an unconditional "Failed to create Market Data strategy".
  it('recovers via re-scan when createStrategy returns no id', async () => {
    mocks.api.getStrategies
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        { id: 's-rescan', name: MARKET_DATA_STRATEGY_NAME, is_active: false },
      ])
    mocks.api.createStrategy.mockResolvedValue({})

    expect(await ensureMarketDataStrategy()).toBe('s-rescan')
    expect(mocks.api.activateStrategy).toHaveBeenCalledWith('s-rescan')
  })

  it('throws only when the re-scan genuinely finds nothing', async () => {
    mocks.api.getStrategies.mockResolvedValue([])
    mocks.api.createStrategy.mockResolvedValue({})

    await expect(ensureMarketDataStrategy()).rejects.toThrow(
      'Failed to create Market Data strategy'
    )
  })
})
