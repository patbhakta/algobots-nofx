import { useState } from 'react'
import { Loader2, Plus, X } from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_BASE || ''

type EngineTemplate = 'coin' | 'laya' | 'jev'

interface Props {
  token: string | null
  isOpen: boolean
  onClose: () => void
  onCreated: () => void
  onError?: (message: string) => void
}

const templates: Array<{
  value: EngineTemplate
  label: string
  description: string
}> = [
  {
    value: 'coin',
    label: 'Coinflip',
    description: 'Random yes/no each window for baseline comparison',
  },
  {
    value: 'laya',
    label: 'Laya System One',
    description: 'Momentum-based edge detection with risk management',
  },
  {
    value: 'jev',
    label: 'Jev',
    description: 'High-confidence pattern recognition (experimental)',
  },
]

export function AddStrategyModal({
  token,
  isOpen,
  onClose,
  onCreated,
  onError,
}: Props) {
  const [step, setStep] = useState<'template' | 'params'>('template')
  const [template, setTemplate] = useState<EngineTemplate>('coin')
  const [name, setName] = useState('')
  const [qty, setQty] = useState(1)
  const [windowTiming, setWindowTiming] = useState<'begin' | 'middle' | 'end'>(
    'middle'
  )
  const [series, setSeries] = useState<'15m' | '5m'>('15m')
  const [creating, setCreating] = useState(false)

  const handleCreate = async () => {
    if (!token) return
    setCreating(true)
    try {
      // Get default config for the template
      const configRes = await fetch(
        `${API_BASE}/api/nofx/strategies/default-config?template=${template}`,
        { headers: { Authorization: `Bearer ${token}` } }
      )
      if (!configRes.ok) throw new Error('Failed to load template')
      const config = await configRes.json()

      // Update baseline with user params
      config.baseline = {
        ...config.baseline,
        strategy: template,
        qty,
        contracts: qty,
        window_timing: windowTiming,
        entry_timing: windowTiming,
        series,
      }

      // Create the strategy
      const createRes = await fetch(`${API_BASE}/api/nofx/strategies`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: name || `${templates.find((t) => t.value === template)?.label} Strategy`,
          description: `${template} strategy with ${qty} contracts, ${windowTiming} timing, ${series} series`,
          config,
        }),
      })

      if (!createRes.ok) {
        const data = await createRes.json().catch(() => ({}))
        throw new Error(data.error || data.message || 'Failed to create strategy')
      }

      onCreated()
      handleClose()
    } catch (err) {
      onError?.(err instanceof Error ? err.message : 'Create failed')
    } finally {
      setCreating(false)
    }
  }

  const handleClose = () => {
    setStep('template')
    setTemplate('coin')
    setName('')
    setQty(1)
    setWindowTiming('middle')
    setSeries('15m')
    onClose()
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-lg rounded-lg border border-[rgba(25,36,52,0.14)] bg-nofx-bg shadow-xl">
        <div className="flex items-center justify-between border-b border-[rgba(25,36,52,0.14)] px-4 py-3">
          <h2 className="text-lg font-semibold text-nofx-text">
            {step === 'template' ? 'Add Strategy' : 'Configure Strategy'}
          </h2>
          <button
            type="button"
            onClick={handleClose}
            className="rounded p-1 text-nofx-text-muted hover:text-nofx-text"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-4">
          {step === 'template' ? (
            <div className="space-y-3">
              <p className="text-sm text-nofx-text-muted">
                Choose an engine template for your strategy:
              </p>
              {templates.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => setTemplate(t.value)}
                  className={`w-full rounded-lg border p-4 text-left transition ${
                    template === t.value
                      ? 'border-nofx-gold bg-nofx-gold/10'
                      : 'border-[rgba(25,36,52,0.14)] bg-nofx-bg-deeper hover:border-[rgba(25,36,52,0.24)]'
                  }`}
                >
                  <div className="font-semibold text-nofx-text">{t.label}</div>
                  <div className="mt-1 text-xs text-nofx-text-muted">
                    {t.description}
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="space-y-4">
              <label className="block space-y-2">
                <span className="text-xs font-medium text-nofx-text-muted">
                  Strategy Name
                </span>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={`${templates.find((t) => t.value === template)?.label} Strategy`}
                  className="w-full rounded-lg border border-[rgba(25,36,52,0.14)] bg-nofx-bg-deeper px-3 py-2 text-sm text-nofx-text placeholder:text-nofx-text-muted/50"
                />
              </label>

              <div className="grid gap-4 sm:grid-cols-3">
                <label className="space-y-2">
                  <span className="text-xs font-medium text-nofx-text-muted">
                    Contracts
                  </span>
                  <select
                    value={qty}
                    onChange={(e) => setQty(Number(e.target.value))}
                    className="w-full rounded-lg border border-[rgba(25,36,52,0.14)] bg-nofx-bg-deeper px-3 py-2 text-sm text-nofx-text"
                  >
                    {[1, 2, 5, 10, 20].map((q) => (
                      <option key={q} value={q}>
                        {q}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="space-y-2">
                  <span className="text-xs font-medium text-nofx-text-muted">
                    Window Timing
                  </span>
                  <select
                    value={windowTiming}
                    onChange={(e) =>
                      setWindowTiming(
                        e.target.value as 'begin' | 'middle' | 'end'
                      )
                    }
                    className="w-full rounded-lg border border-[rgba(25,36,52,0.14)] bg-nofx-bg-deeper px-3 py-2 text-sm text-nofx-text"
                  >
                    <option value="begin">Begin</option>
                    <option value="middle">Middle</option>
                    <option value="end">End</option>
                  </select>
                </label>

                <label className="space-y-2">
                  <span className="text-xs font-medium text-nofx-text-muted">
                    Series
                  </span>
                  <select
                    value={series}
                    onChange={(e) => setSeries(e.target.value as '15m' | '5m')}
                    className="w-full rounded-lg border border-[rgba(25,36,52,0.14)] bg-nofx-bg-deeper px-3 py-2 text-sm text-nofx-text"
                  >
                    <option value="15m">15-minute</option>
                    <option value="5m">5-minute</option>
                  </select>
                </label>
              </div>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 border-t border-[rgba(25,36,52,0.14)] px-4 py-3">
          {step === 'params' && (
            <button
              type="button"
              onClick={() => setStep('template')}
              className="rounded-lg border border-[rgba(25,36,52,0.14)] px-4 py-2 text-sm text-nofx-text-muted hover:text-nofx-text"
            >
              Back
            </button>
          )}
          <button
            type="button"
            onClick={handleClose}
            className="rounded-lg border border-[rgba(25,36,52,0.14)] px-4 py-2 text-sm text-nofx-text-muted hover:text-nofx-text"
          >
            Cancel
          </button>
          {step === 'template' ? (
            <button
              type="button"
              onClick={() => setStep('params')}
              className="inline-flex items-center gap-2 rounded-lg bg-nofx-gold px-4 py-2 text-sm font-semibold text-nofx-bg"
            >
              Next
            </button>
          ) : (
            <button
              type="button"
              onClick={handleCreate}
              disabled={creating}
              className="inline-flex items-center gap-2 rounded-lg bg-nofx-success px-4 py-2 text-sm font-semibold text-nofx-bg disabled:opacity-50"
            >
              {creating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              Create Strategy
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default AddStrategyModal
