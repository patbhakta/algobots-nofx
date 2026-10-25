import useSWR from 'swr'
import { getAuthHeaders, handleJSONResponse } from '../lib/api/helpers'

interface DataFeed {
  feed: { state: string; reason?: string; age_s?: number }
  row_count: number
  observations: { ts: number; event: string; p: number | null; p_source: string | null; outcome: number | null }[]
  counts: { logged_total: number; settled: number }
  error?: string
}
export function DataPage() {
  const { data, error, mutate } = useSWR<DataFeed>('/api/nofx/data',
    url => fetch(url, { headers: getAuthHeaders() }).then(handleJSONResponse<DataFeed>), { refreshInterval: 15000 })
  return <section className="max-w-6xl mx-auto p-8 space-y-4">
    <h1 className="text-2xl font-semibold">Live Kalshi data</h1>
    <p>BTC 15 minute markets · Nautilus paper execution</p>
    {error && <p role="alert">Data unavailable. <button onClick={() => void mutate()}>Retry</button></p>}
    {!data && !error && <p>Loading observations…</p>}
    {data && <>
      <p>Feed: {data.feed.state} · {data.row_count} observations · {data.counts.logged_total} logged decisions · {data.counts.settled} settled</p>
      {data.feed.reason && <p role="status">{data.feed.reason}</p>}
      {data.error && <p role="alert">{data.error}</p>}
      {!data.observations.length && <p>No observations available yet.</p>}
      <div className="overflow-x-auto"><table className="w-full text-left"><thead><tr><th>Observed (UTC)</th><th>Market</th><th>P(up)</th><th>Signal</th><th>Outcome</th></tr></thead>
      <tbody>{data.observations.map((r, i) => <tr key={`${r.event}-${i}`}><td>{new Date(r.ts * 1000).toISOString()}</td><td>{r.event}</td><td>{r.p == null ? '—' : r.p.toFixed(3)}</td><td>{r.p_source ?? 'unknown'}</td><td>{r.outcome ?? 'pending'}</td></tr>)}</tbody></table></div>
    </>}
  </section>
}
