import useSWR from 'swr'
import { getAuthHeaders, handleJSONResponse } from '../lib/api/helpers'

interface Scores {
  accounts: { strategy: string; n: number; hits: number; hit_rate: number | null; brier: number | null; verdict: string }[]
  logged?: number; settled?: number; error?: string
}
export function LeaderboardPage() {
  const { data, error } = useSWR<Scores>('/api/nofx/leaderboard',
    url => fetch(url, { headers: getAuthHeaders() }).then(handleJSONResponse<Scores>), { refreshInterval: 15000 })
  return <section className="max-w-6xl mx-auto p-8 space-y-4">
    <h1 className="text-2xl font-semibold">Scored accounts</h1>
    <p>Settled decision quality · paper environment · hit rate does not establish profitability.</p>
    {error && <p role="alert">Scores unavailable. Please retry shortly.</p>}
    {!data && !error && <p>Loading scores…</p>}
    {data?.error && <p role="alert">{data.error}</p>}
    {data && !data.error && !data.accounts.length && <p>No scored decisions yet.</p>}
    <div className="overflow-x-auto"><table className="w-full text-left"><thead><tr><th>Account</th><th>Settled</th><th>Hits</th><th>Hit rate</th><th>Brier</th><th>Verdict</th></tr></thead><tbody>
      {data?.accounts.map(a => <tr key={a.strategy}><td>{a.strategy}</td><td>{a.n}</td><td>{a.hits}</td><td>{a.hit_rate == null ? '—' : `${(a.hit_rate * 100).toFixed(1)}%`}</td><td>{a.brier?.toFixed(3) ?? '—'}</td><td>{a.verdict}</td></tr>)}
    </tbody></table></div>
  </section>
}
