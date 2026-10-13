# ALG-3282 — A11-3: instrument ownership, FanoutCampaign, partial-success UI, recovery

Live check (local API, `ALGOBOTS_DEMO_WORKERS_ENABLED=true`, scratch state dir),
two campaigns deployed 6h before start:

| campaign | version | children | outcome |
|---|---|---|---|
| cmp-c76ff035-1 | Trend crossover v2 (5m, 5/13, SPY) | eq-a 400 · eq-b 400 | `SUCCEEDED · 2/2` (both filled) |
| cmp-c9720de8-2 | Range / RSI v2 (5m, 6, 35/65, QQQ) | eq-a 600 · eq-b 2100 · eq-c 500 · laya skip | `PARTIAL · 2/4` |

cmp-c9720de8-2 children:

| account | child status | reason |
|---|---|---|
| eq-a | filled | 5 orders filled |
| eq-b | rejected-by-risk | 2100.00 USD over max order value; gate allows 1000 USD per deployment |
| eq-c | filled | 5 orders filled |
| laya | skipped | equities strategy cannot trade on a kalshi account |

- Instrument ownership: SPY on eq-a/eq-b is owned by the trend deployment;
  the QQQ campaign deploys alongside it — a conflicting SPY version is skipped
  at preview naming the owner (`tests/demo/test_campaigns.py`).
- No cross-account atomicity: eq-b's rejection left eq-a/eq-c fills in place.
- Recovery verified live: pausing cmp-c9720de8-2 → `PAUSED · 2/4` (new entries
  held, exits still fill); disabling Range / RSI v2 kept all 7 deployments and
  history, re-enable restored preview.
- `/demo/api/campaigns` exposes parents, per-child live status, and each
  campaign's order timeline (risk denials carry their reason).
- Screenshots: `studio-campaign-partial-{desktop,mobile}.png` (1440px / 390px,
  `/demo/studio?campaign=cmp-c9720de8-2` — Campaigns panel + order timeline).
