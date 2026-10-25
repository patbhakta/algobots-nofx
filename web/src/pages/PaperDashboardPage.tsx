import { useState } from 'react'
import useSWR from 'swr'
import { TerminalDashboard } from '../components/terminal/TerminalDashboard'
import { paperLoopApi } from '../lib/api/paperLoop'
import type { AccountInfo, DecisionRecord, TraderInfo } from '../types'

// Keep upstream visual structure; translate only the authenticated evidence.
export function PaperDashboardPage() {
  const {data, error} = useSWR('paper-dashboard', paperLoopApi.live, {refreshInterval: 20000})
  const [selected, setSelected] = useState('')
  const traders: TraderInfo[] = (data?.workers || []).map(w => ({trader_id:w.account, trader_name:`${w.account} · PAPER`, ai_model:'', strategy_name:'Kalshi BTC 15m', is_running:w.state === 'ready'}))
  const id = traders.some(t => t.trader_id === selected) ? selected : traders[0]?.trader_id
  const worker = data?.workers.find(w => w.account === id)
  const number = (value?: string) => value == null || !Number.isFinite(Number(value)) ? undefined : Number(value)
  const equity = number(worker?.funds?.equity)
  const allocated = number(worker?.funds?.allocated)
  const pnl = equity != null && allocated != null ? equity - allocated : undefined
  const account: Partial<AccountInfo> = {total_equity:equity, initial_balance:allocated, total_pnl:pnl, total_pnl_pct:pnl != null && allocated ? pnl / allocated * 100 : undefined, position_count:worker?.open_positions}
  const decisions: DecisionRecord[] = (data?.decisions || []).filter(d => d.strategy === id).map((d, i) => ({
    timestamp:d.decided_at || '', cycle_number:i + 1, system_prompt:'', input_prompt:'', cot_trace:d.reason || '', decision_json:JSON.stringify(d),
    account_state:{total_balance:NaN,available_balance:NaN,total_unrealized_profit:NaN,position_count:0,margin_used_pct:NaN},
    positions:[],candidate_coins:[d.event],
    decisions:[{action:d.execution || d.status || 'unknown',symbol:d.event,quantity:d.qty || 0,leverage:1,price:Number(d.fill_px),order_id:0,timestamp:d.decided_at || '',success:d.execution === 'FILLED',reasoning:d.reason || '',error:d.risk_blocked ? d.reason || 'Risk blocked' : undefined}],
    execution_log:[d.reason || '', d.receipt?.client_order_id || 'No receipt in current worker window'], success:d.execution === 'FILLED',error_message:d.risk_blocked ? d.reason || 'Risk blocked' : undefined,
  }))
  return <>
    <p role={error ? 'alert' : 'status'} className="max-w-7xl mx-auto px-4 py-2 text-xs">PAPER · Nautilus sandbox · {error ? 'Evidence unavailable; retry shortly.' : data ? `${data.feed.state} Kalshi feed · ${data.environment.execution}` : 'Loading authenticated paper evidence…'}</p>
    <TerminalDashboard paper={data || true} traders={traders} selectedTraderId={id} selectedTrader={traders.find(t=>t.trader_id===id)} onTraderSelect={setSelected} decisions={decisions} account={account} status={{is_running:worker?.state === 'ready', call_count:id ? data?.counts.logged[id] : undefined, scan_interval:'15m', ai_model:data?.decisions.find(d=>d.strategy === id)?.provider || ''}} />
  </>
}
