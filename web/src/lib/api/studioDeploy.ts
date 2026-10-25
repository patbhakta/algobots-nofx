// ALG-3423: Studio deployments through the evidence gate. POST /api/deployments
// refuses (422) any compiled Studio artifact that has no published marimo
// backtest evidence for its exact artifact hash; this client and the deploy
// panel surface that contract instead of hiding it.
import { API_BASE, httpClient } from './helpers'

export interface DeployAccount {
  id: string
  label: string
  broker: string
  mode: string
}

export interface DeploymentCreatePayload {
  strategy_id: string
  account_id: string
  symbol: string
  max_order_value: string
  max_daily_loss: string
}

export interface StudioEvidence {
  backtest_row_id: string
  artifact_hash: string
  snapshot_id: string
  dataset_sha256: string
  notebook_url: string
  result_sha256: string
}

export interface Deployment {
  id: string
  strategy_id: string
  account_id: string
  symbol: string
  status: string
  artifact_hash: string
  frozen_spec: { studio_evidence?: StudioEvidence; [key: string]: unknown }
  breaker_state: string
  effective_state: string
  created_at: string
}

function detail(r: { message?: string; errorData?: any }) {
  const d = r.errorData?.detail
  if (d && typeof d === 'object' && d.message) return `${d.field}: ${d.message}`
  if (typeof d === 'string') return d
  return r.message || 'Deploy failed'
}

export const studioDeployApi = {
  accounts: async (): Promise<DeployAccount[]> => {
    const r = await httpClient.get<DeployAccount[]>(`${API_BASE}/accounts`)
    if (!r.success || !r.data) throw new Error(detail(r))
    return r.data
  },
  createAccount: async (label: string): Promise<DeployAccount> => {
    const r = await httpClient.request<DeployAccount>(`${API_BASE}/accounts`, {
      method: 'POST',
      data: { label, broker: 'kalshi', mode: 'paper' },
    })
    if (!r.success || !r.data) throw new Error(detail(r))
    return r.data
  },
  create: async (payload: DeploymentCreatePayload): Promise<Deployment> => {
    const r = await httpClient.request<Deployment>(`${API_BASE}/deployments`, {
      method: 'POST',
      data: payload,
    })
    if (!r.success || !r.data) throw new Error(detail(r))
    return r.data
  },
}
