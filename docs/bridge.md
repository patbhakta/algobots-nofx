# NoFX <-> Nautilus order bridge (ALG-3340, ALG-3339 ms3)

Law (ADR 0001): every order and fill goes through a Nautilus `ExecutionClient`.
The control plane admits intents; it never executes, simulates, or proxies.
OpenAlgo is a feature reference only (patterns, no code — AGPL).

## Components

| Piece | Where | Role |
| --- | --- | --- |
| `src/algobots/bridge/router.py` | control plane | HTTP surface (`/bridge/*`) |
| `src/algobots/bridge/admission.py` | control plane | scope → PAPER-only → worker-up → ALG-3262 gate |
| `src/algobots/bridge/channel.py` | both sides | intents/ + fills/ file channel (stdlib) |
| `src/algobots/bridge/stats.py` | control plane | traffic + latency registry (OpenAlgo pull #6) |
| `engine.workers.paper` | per-account worker | executes claimed intents on `PAPER_<ACCT>`, mirrors `OrderFilled` |

Enable on the control plane with `ALGOBOTS_BRIDGE_DIR` (compose:
`ALGOBOTS_BRIDGE_HOST_DIR` bind-mounts the stack dir at `/bridge`). Empty
setting = bridge disabled (typed `503 bridge_disabled`).

## Endpoints

- `POST /bridge/intents` — `{account, side: buy|sell, qty, symbol?, ts_utc?, mode?}`.
  Admission order: account scope (404 unknown / 403 ungranted) → side/qty/symbol
  shape (422) → `mode != PAPER` (403 `live_disabled`) → worker reconciled +
  heartbeat-fresh + lease-live (503 `worker_unavailable`, no fallback) →
  `gate.pre_trade` (kill switch, sleeve floor, daily-loss envelope, order-value
  clamp, affordability; 403 with the gate's typed code). An admitted intent is
  answered `201` with its `intent_id` and clamped `qty`/`notional`, then written
  to `bridge/intents/<intent_id>.json`. Refused intents are never written.
- `GET /bridge/fills?account=&limit=` — the account's fill records from
  `bridge/fills/<account>.jsonl` (written by ITS worker, oldest-first tail).
- `GET /bridge/positions/{account}` — open positions as the worker's venue
  cache reports them (the same read the demo order API serves).
- `GET /bridge/intents/{intent_id}` — `admitted → processing → done` plus the
  terminal outcome (`filled` with fill ref, or `rejected` with reason).
- `GET /bridge/stats` — per-endpoint traffic + latency p50/p95/max and on-disk
  channel counters (intents by state, fills recorded, last fill ts).

## File-channel contract (v1)

```
bridge/
  intents/<intent_id>.json        admitted intents (control plane writes, atomic)
  processing/<account>/<id>.json  claimed by that account's worker (rename)
  done/<intent_id>.json           terminal outcome: filled / rejected
  fills/<account>.jsonl           Nautilus OrderFilled events, one JSON per line
```

- Intent record: `intent_id, account, symbol (<event>-<YES|NO>), side (buy|sell),
  qty, notional, kind (entry|exit), ts_utc, admitted_ts, status: admitted,
  mode: PAPER, venue: PAPER_<ACCT>, source: bridge`.
- Fill record (`bridge-fill/1`): `intent_id, account, symbol, side, qty, px,
  notional, commission, client_order_id, trade_id, trader_id, order_id_tag,
  venue, venue_account_id, ts_event, ts_utc, ts_recorded`.
- Delivery is **at-least-once**: a claim that survives a worker crash is
  replayed on the next drain, so a fill line can appear twice; consumers
  dedupe on `intent_id` (or `trade_id`). Outcomes in `done/` are idempotent.
- Nothing in this directory is an order route: files under `intents/` are only
  honored after control-plane admission, and only a worker's Nautilus engine
  can turn them into fills.

## Acceptance (from the stack, Oct 13 2026)

From the NoFX host network (`nofx` container): `POST http://algobots-api:8000/bridge/intents`
with `{account: laya, side: buy, qty: 10}` → 201 → the account's worker claims,
executes on `PAPER_LAYA`, appends an `OrderFilled` record to
`bridge/fills/laya.jsonl`, finishes the intent `done/filled`, and the position
is visible at `GET /bridge/positions/laya` and in the worker heartbeat.
