import type { BaselineParameters, StrategyConfig } from '../../types'

export function BaselineParameterEditor({
  config,
  onChange,
}: {
  config: StrategyConfig
  onChange: (config: StrategyConfig) => void
}) {
  // Older saved momentum configs have the same effective parameter in demo_worker.
  const baseline: BaselineParameters | undefined =
    config.baseline ||
    (config.demo_worker?.min_edge !== undefined
      ? { strategy: 'laya', min_edge: config.demo_worker.min_edge }
      : undefined)
  if (!baseline) return null
  const update = (next: BaselineParameters) =>
    onChange({ ...config, baseline: next })
  const field =
    'mt-1 block w-full rounded border bg-nofx-bg px-3 py-2 text-nofx-text'
  return (
    <section
      aria-label="Strategy parameters"
      className="rounded-lg border bg-nofx-bg-lighter p-4 text-nofx-text"
    >
      <h2 className="font-semibold">
        {baseline.strategy === 'coin'
          ? 'Coinflip'
          : baseline.strategy === 'jev'
            ? 'Jev'
            : 'Laya'}{' '}
        parameters
      </h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        {baseline.strategy === 'laya' && (
          <label>
            Minimum edge from 50% (0–0.5)
            <input
              className={field}
              type="number"
              min="0"
              max="0.5"
              step="0.01"
              value={baseline.min_edge}
              onChange={(e) =>
                update({ ...baseline, min_edge: e.target.valueAsNumber })
              }
            />
          </label>
        )}
        {baseline.strategy === 'coin' && (
          <>
            <label>
              Entry delay after market open (seconds)
              <input
                className={field}
                type="number"
                min="0"
                max="899"
                step="1"
                value={baseline.entry_delay_seconds}
                onChange={(e) =>
                  update({
                    ...baseline,
                    entry_delay_seconds: e.target.valueAsNumber,
                  })
                }
              />
            </label>
            <label>
              Stake (USD)
              <input
                className={field}
                type="number"
                min="0.01"
                step="0.01"
                value={baseline.stake}
                onChange={(e) => update({ ...baseline, stake: e.target.value })}
              />
            </label>
          </>
        )}
        {baseline.strategy === 'jev' && (
          <label>
            Minimum recorded confidence (0–1)
            <input
              className={field}
              type="number"
              min="0"
              max="1"
              step="0.01"
              value={baseline.min_confidence}
              onChange={(e) =>
                update({ ...baseline, min_confidence: e.target.valueAsNumber })
              }
            />
          </label>
        )}
      </div>
      <p className="mt-3 text-xs text-nofx-text-muted">
        Save → backtest a frozen dataset → review evidence. Saving does not
        change running workers.
        {baseline.strategy === 'coin' &&
          ' Replay needs a captured observation at or after the delay and before close; earlier observations abstain.'}
        {baseline.strategy === 'jev' &&
          ' Replay requires a timestamped Jev call before the captured book and market close. No inference calls are made.'}
      </p>
    </section>
  )
}
