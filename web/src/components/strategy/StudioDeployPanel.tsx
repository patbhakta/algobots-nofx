import { useEffect, useState } from 'react'
import { Loader2, Rocket } from 'lucide-react'
import type { StudioCompileStatus } from '../../types'
import { studioBacktestApi } from '../../lib/api/studioBacktest'
import { studioDeployApi, type Deployment } from '../../lib/api/studioDeploy'

// ALG-3423: the deploy leg of the Studio lifecycle. The backend refuses to
// deploy (422) a compiled artifact unless a marimo backtest notebook is
// published for its exact artifact hash, so the panel states eligibility
// instead of letting the button fail opaquely.
export function StudioDeployPanel({
  studio,
  stale,
}: {
  studio?: StudioCompileStatus | null
  stale: boolean
}) {
  const draftId = studio?.status === 'compiled' ? studio.draft_id : null
  const hash = studio?.artifact_hash
  const strategyId = studio?.strategy_id
  const [accounts, setAccounts] = useState<{ id: string; label: string }[]>([])
  const [accountId, setAccountId] = useState('')
  const [symbol, setSymbol] = useState('KXBTC15M')
  const [maxOrderValue, setMaxOrderValue] = useState('5')
  const [maxDailyLoss, setMaxDailyLoss] = useState('20')
  const [evidenceUrl, setEvidenceUrl] = useState<string | null>(null)
  const [eligible, setEligible] = useState(false)
  const [deploying, setDeploying] = useState(false)
  const [creatingAccount, setCreatingAccount] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deployment, setDeployment] = useState<Deployment | null>(null)

  useEffect(() => {
    setDeployment(null)
    setError(null)
    setEligible(false)
    setEvidenceUrl(null)
    if (!draftId || !hash) return
    let live = true
    studioBacktestApi
      .list(draftId)
      .then((rows) => {
        if (!live) return
        const published = rows.find(
          (r) => r.artifact.artifact_hash === hash && r.evidence
        )
        setEligible(Boolean(published))
        setEvidenceUrl(published?.evidence?.notebook_url || null)
      })
      .catch(() => undefined)
    return () => {
      live = false
    }
  }, [draftId, hash])

  useEffect(() => {
    let live = true
    studioDeployApi
      .accounts()
      .then((rows) => {
        if (!live) return
        setAccounts(rows)
        setAccountId((current) => current || rows[0]?.id || '')
      })
      .catch(() => undefined)
    return () => {
      live = false
    }
  }, [])

  const createAccount = async () => {
    setCreatingAccount(true)
    setError(null)
    try {
      const account = await studioDeployApi.createAccount('Kalshi paper')
      setAccounts((rows) => [...rows, account])
      setAccountId(account.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Account creation failed')
    } finally {
      setCreatingAccount(false)
    }
  }

  const deploy = async () => {
    if (!strategyId || !accountId) return
    setDeploying(true)
    setError(null)
    try {
      setDeployment(
        await studioDeployApi.create({
          strategy_id: strategyId,
          account_id: accountId,
          symbol,
          max_order_value: maxOrderValue,
          max_daily_loss: maxDailyLoss,
        })
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Deploy failed')
    } finally {
      setDeploying(false)
    }
  }

  const disabledReason = !draftId
    ? 'Compile the config before deploying.'
    : stale
      ? 'Save changes so the compiled artifact matches this config.'
      : studio?.deployable === false
        ? 'Research replay only. This implementation has no deployment worker; use Backtest to inspect evidence.'
        : !eligible
          ? 'Marimo backtest evidence required — run Backtest first.'
          : !accountId
            ? 'Select or create a paper account.'
            : null

  return (
    <div
      data-testid="studio-deploy-panel"
      className="mt-3 rounded-lg border border-[rgba(26,24,19,0.14)] px-3 py-2 text-xs"
    >
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-semibold">Deploy</span>
        <select
          aria-label="Deploy account"
          value={accountId}
          disabled={deploying}
          onChange={(event) => setAccountId(event.target.value)}
        >
          {!accounts.length && <option value="">No paper account</option>}
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.label}
            </option>
          ))}
        </select>
        {!accounts.length ? (
          <button
            type="button"
            data-testid="studio-deploy-create-account"
            onClick={createAccount}
            disabled={creatingAccount}
            className="underline"
          >
            {creatingAccount ? 'Creating…' : 'Create paper account'}
          </button>
        ) : null}
        <label>
          Symbol{' '}
          <input
            aria-label="Deploy symbol"
            value={symbol}
            disabled={deploying}
            onChange={(event) => setSymbol(event.target.value)}
            className="w-24 rounded border border-[rgba(26,24,19,0.2)] px-1 py-0.5"
          />
        </label>
        <label>
          Max order ${' '}
          <input
            aria-label="Max order value"
            value={maxOrderValue}
            disabled={deploying}
            onChange={(event) => setMaxOrderValue(event.target.value)}
            className="w-16 rounded border border-[rgba(26,24,19,0.2)] px-1 py-0.5"
          />
        </label>
        <label>
          Daily loss ${' '}
          <input
            aria-label="Max daily loss"
            value={maxDailyLoss}
            disabled={deploying}
            onChange={(event) => setMaxDailyLoss(event.target.value)}
            className="w-16 rounded border border-[rgba(26,24,19,0.2)] px-1 py-0.5"
          />
        </label>
        <button
          type="button"
          data-testid="studio-deploy-button"
          onClick={deploy}
          disabled={deploying || disabledReason !== null}
          className="inline-flex items-center gap-1.5 rounded-lg bg-nofx-gold px-3 py-1.5 text-sm font-semibold text-nofx-bg disabled:cursor-not-allowed disabled:opacity-45"
        >
          {deploying ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Rocket className="h-4 w-4" />
          )}
          Deploy
        </button>
      </div>
      {disabledReason ? (
        <div
          data-testid="studio-deploy-reason"
          className="mt-1 text-nofx-text-muted"
        >
          {disabledReason}
        </div>
      ) : null}
      {eligible && evidenceUrl ? (
        <div className="mt-1">
          Evidence:{' '}
          <a
            data-testid="studio-deploy-evidence-link"
            href={evidenceUrl}
            target="_blank"
            rel="noreferrer"
            className="underline"
          >
            marimo backtest notebook
          </a>
        </div>
      ) : null}
      {error ? (
        <div
          data-testid="studio-deploy-error"
          className="mt-1 text-nofx-danger"
        >
          {error}
        </div>
      ) : null}
      {deployment ? (
        <div data-testid="studio-deploy-result" className="mt-1">
          Deployment {deployment.id.slice(0, 8)} · {deployment.symbol} ·{' '}
          {deployment.status}
          {deployment.frozen_spec.studio_evidence?.notebook_url ? (
            <>
              {' · frozen evidence '}
              <a
                href={deployment.frozen_spec.studio_evidence.notebook_url}
                target="_blank"
                rel="noreferrer"
                className="underline"
              >
                notebook
              </a>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
