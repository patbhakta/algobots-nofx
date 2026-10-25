import useSWR from 'swr'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getAuthHeaders, handleJSONResponse } from '../lib/api/helpers'

interface Scores {
  accounts: { strategy: string; n: number; hits: number; hit_rate: number | null; brier: number | null; verdict: string }[]
  equity_curves?: Record<string, { ts: number; equity: string }[]>
  equity_source?: string
  logged?: number; settled?: number; error?: string
}
const colors = ['#19836b', '#bd8532', '#5b71b5']
export function LeaderboardPage() {
  const { data, error } = useSWR<Scores>('/api/nofx/leaderboard',
    url => fetch(url, { headers: getAuthHeaders() }).then(handleJSONResponse<Scores>), { refreshInterval: 15000 })
  return <section className="max-w-6xl mx-auto p-8 space-y-6">
    <h1 className="text-2xl font-semibold">Scored accounts</h1>
    <p>Settled decision quality · paper environment · hit rate does not establish profitability.</p>
    {error && <p role="alert">Scores unavailable. Please retry shortly.</p>}
    {!data && !error && <p>Loading scores…</p>}
    {data?.error && <p role="alert">{data.error}</p>}
    {data && !data.error && !data.accounts.length && <p>No scored decisions yet.</p>}
    {!!data?.accounts.length && <>
      <div className="grid gap-6 md:grid-cols-2">
        {(['hit_rate', 'brier'] as const).map(metric => <figure key={metric} aria-label={metric === 'hit_rate' ? 'Hit rate by account' : 'Brier score by account'}>
          <figcaption className="font-semibold mb-3">{metric === 'hit_rate' ? 'Hit rate · higher is better' : 'Brier score · lower is better'}</figcaption>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={data.accounts} accessibilityLayer><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="strategy" /><YAxis domain={[0, 1]} /><Tooltip /><Bar dataKey={metric} fill={metric === 'hit_rate' ? colors[0] : colors[1]} /></BarChart>
          </ResponsiveContainer>
        </figure>)}
      </div>
      <h2 className="text-lg font-semibold">Paper equity by account · USD</h2>
      <p className="text-sm">{data.equity_source || 'Equity history unavailable.'}</p>
      <div className="grid gap-6 md:grid-cols-2">
        {data.accounts.map((account, i) => {
          const points = (data.equity_curves?.[account.strategy] || []).filter(p => Number.isFinite(Number(p.equity))).map(p => ({...p, equity: Number(p.equity)}))
          return <figure key={account.strategy} aria-label={`${account.strategy} equity curve`}>
            <figcaption className="font-semibold">{account.strategy}</figcaption>
            {points.length ? <ResponsiveContainer width="100%" height={220}>
              <LineChart data={points} accessibilityLayer><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="ts" type="number" domain={['dataMin', 'dataMax']} tickFormatter={ts => new Date(ts * 1000).toLocaleDateString()} /><YAxis domain={['auto', 'auto']} /><Tooltip labelFormatter={ts => new Date(Number(ts) * 1000).toISOString()} /><Line dataKey="equity" stroke={colors[i % colors.length]} dot={points.length === 1} isAnimationActive={false} /></LineChart>
            </ResponsiveContainer> : <p>Equity history unavailable for this account.</p>}
            <p className="text-sm">{account.n} settled · {account.hit_rate == null ? 'hit rate unavailable' : `${(account.hit_rate * 100).toFixed(1)}% hit rate`} · Brier {account.brier?.toFixed(3) ?? 'unavailable'} · {account.verdict}</p>
          </figure>
        })}
      </div>
    </>}
  </section>
}
