# ALG-3406 — DEMO hop 4: replay market data into the rc6 paper node

**Result: hop 4 reports `wired`** (`python tests/demo/full_loop.py`, .243, 2026-10-22T06:46Z).
Raw output: `verifier-243.txt`.

## What was replayed

The Nautech base image the node is built on (pinned by digest) ships a Nautilus
Parquet catalog: `/catalog/data/quote_tick/EURUSD.SIM/part-0.parquet`, with
**1,637,768 recorded EUR/USD quotes** from 2020-01-01T17:00Z to 2020-01-31.
EUR/USD.SIM is already the node's instrument. I used this slice and not the Kalshi
data because Kalshi contracts do not map to the sandbox FX venue.
`/opt/laya/kalshi/` on .243 is empty.

## How

| | |
| --- | --- |
| Client | `REPLAY` data client in `paper_node.py` (`ALGOBOTS_FEED=replay`, default) |
| Reader | `algobots.node.replay.read_quotes`, which streams row groups via pyarrow. Prices and sizes are 16-byte LE fixed-point (scale 1e16) → `Price/Quantity.from_raw` |
| Clock | Recorded inter-arrival gaps at `ALGOBOTS_REPLAY_SPEED` (1x), capped at `ALGOBOTS_REPLAY_MAX_GAP_S` (2 s); loops at end of file |
| Stamping | `ts_event = ts_init = node clock`, so the sandbox venue matches against them as current prices. The recorded `ts_event` is carried in the feed signal and the node log |
| Feed signal | The strategy's `on_quote` (rc6's name; 1.x was `on_quote_tick`) does `XADD algobots:feed:<node>` at most once a second with `source, instrument, node_ts, recorded_ts, row, laps, bid, ask, received`. Capped with `MAXLEN ~3600` |
| Fallback | `ALGOBOTS_FEED=synthetic` keeps the ALG-3405 random walk. It is labelled `synthetic`, and the verifier refuses it |

## Verifier change (`tests/demo/full_loop.py`)

Hop 4 now reads the newest entry of `algobots:feed:*`. The entry is aged against Redis's own `TIME`, so clock skew between machines doesn't matter. The hop is:

- **wired** when the entry is ≤ 60 s old and its source is not synthetic;
- **stubbed** when the feed is synthetic or stale;
- judged by the old worker feed-file check when no node feed stream exists.

## Evidence on .243

- Node log: `feed received=1 node_ts=1792651535658602239 recorded_ts=1577898010447000000 row=0 bid=1.12120 ask=1.12192`
- `scripts/rc6_node_smoke.py` (gateway `POST /v1/orders` → rc6 fill): filled at **1.12172**, a recorded ask. The synthetic walk started at 1.10000.
- Verifier hop 4: `algobots:feed:nautilus-paper: 32 signals, last 1s ago; source replay:/catalog/data/quote_tick/EURUSD.SIM/part-0.parquet EUR/USD.SIM; quotes received by the node: 65; recorded ts 2020-01-01T17:04:19Z (row 64, lap 0) -> node ts 2026-10-22T06:46:37Z`

Deploy: `/opt/algobots/nautilus-node` on branch `alg-3406-replay-feed`, then
`docker compose -f deploy/compose.nautilus-node.yaml up -d --build`. Only the
`nautilus-node` container was recreated.
