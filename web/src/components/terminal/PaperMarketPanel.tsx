import type { PaperLoopLive } from '../../lib/api/paperLoop'

// Venue wiring for the unchanged upstream panel slots. No third-party sockets,
// paid feeds, fabricated books, candles, or holder statistics in paper mode.
export function PaperMarketPanel({kind, live}: {kind: string; live?: PaperLoopLive}) {
  const feed = live?.feed
  const title = {liquidation: 'Cost / liquidation map', book: 'Kalshi YES quotes', prices: 'Kalshi observations', winrate: 'Holder win-rate matrix'}[kind] || kind
  return <div className="tm-mono" style={{fontSize: 12, padding: '10px 0'}}>
    <div className="tm-px" style={{marginBottom: 12}}>{title}</div>
    {kind === 'book' && feed ? <>
      <p>{feed.market || feed.event || 'Market unavailable'}</p>
      <p>YES bid {feed.yes_bid ?? '—'} · ask {feed.yes_ask ?? '—'}</p>
      <p>{feed.state} · {feed.last_observed_ts ? new Date(feed.last_observed_ts * 1000).toISOString() : 'Timestamp unavailable'}</p>
      <p className="tm-sc">Top of book only; full depth unavailable.</p>
    </> : kind === 'prices' && feed ? <>
      <p>{feed.source} · {feed.state}</p>
      <p>Strike {feed.strike ?? '—'}</p>
      <p className="tm-sc">Candle history unavailable from this observation feed.</p>
    </> : <p className="tm-sc">Unavailable for this Kalshi paper feed.</p>}
    {feed?.reason && <p className="tm-sc">{feed.reason}</p>}
  </div>
}
