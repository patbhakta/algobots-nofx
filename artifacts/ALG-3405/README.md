# ALG-3405 — DEMO hop 3: Nautilus 2.0.0rc6 paper node on .243

**Result: hop 3 reports `wired`** (`python tests/demo/full_loop.py`, 2026-10-22T06:37Z).

## What runs

| | |
| --- | --- |
| Container | `nautilus-node` (`algobots/nautilus-node:rc6`), project `algobots-node`, network `algobots_default` |
| Source on .243 | `/opt/algobots/nautilus-node` (clone of branch `alg-3405-rc6-node`) |
| Deploy | `docker compose -f deploy/compose.nautilus-node.yaml up -d --build` |
| Engine | `nautilus_trader 2.0.0rc6`, Nautech base image pinned by digest; build asserts the version |
| Node | `LiveNode`, `Environment.SANDBOX`, trader `NAUTILUS-PAPER`, node name `nautilus-paper` |
| Venue | engine `SandboxExecutionClient`, venue `SIM`, account `SIM-001`, 100,000 USD, zero fees, paper only |
| Commands in | `algobots:cmd:nautilus-paper`, consumer group `algobots-node`, `CommandStream` → `CommandActor` → `NautilusExecution` (P1.3), polled every 200 ms on the node loop |
| Events out | rc6 `RedisMessageBusFactory` → `trader-NAUTILUS-PAPER:algobots:events.*` (P0.3), + `AlgoBotsHeartbeat` every 5 s |
| Prices | **synthetic** random-walk EUR/USD.SIM quotes (`SYNTHETIC` data client) until hop 4 (ALG-3406) replays real data |

## Gateway → rc6 fill (scripts/rc6_node_smoke.py)

The real gateway app (`build_gateway` + `RedisCommandBus` + `NodeEventIngest`,
in-memory projection) running on .243 against the stack Redis:

- `/health`: `ok`, node `nautilus-paper` reachable (heartbeat read off the event stream)
- `POST /v1/orders` (1000 EUR/USD.SIM market buy, PAPER) → `201 admitted`
- `GET /v1/orders/{id}` → `filled` in **0.179 s**: `venue_order_id SIM-0-1`, fill 1000 @ 1.10000, trade `T-a5f3ccbe89706e41-001`
- `/positions`: buy 1000 EUR/USD.SIM; `/accounts`: USD total 100000, free 99967, locked 33

## rc6 wire shape vs the 1.231 capture (fixed in the gateway's ingest)

Captured in `tests/gateway/fixtures/rc6_event_streams.json`:

1. Order/position events are wrapped in their enum variant: `{"Filled": {...}}`, `{"PositionOpened": {...}}`.
2. `AccountState` and position payloads carry no `type`; it is only on the stream entry.
3. Every `ts_*` is integer **nanoseconds** despite `timestamps_as_iso8601=True` — `iso()` overflowed on them.
4. Each order event is published twice: `events.order.<strategy>` (ordered) and a per-type topic
   (`events.order_submitted.<instrument>`, `events.order_filled.<instrument>`). Reading both
   regressed filled orders to `submitted`; the ingest now folds only `order/position/account/heartbeat`.
5. `events.portfolio.<account>` (`PortfolioSnapshot`) is new; not folded. No `AccountState` is published
   before the first fill, so balances appear with the first fill.

rc6 API notes: `add_simulated_exec_client` (not `add_exec_client`) for the sandbox; sandbox requires an
explicit `fee_model`; pyo3 `Strategy.__new__` takes only a config (bind wiring after construction);
`cancel_order(ClientOrderId)`; all model types under `nautilus_trader.model`.

## Verifier output (.243)

| # | Hop | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Studio config saved for a strategy | **stubbed** | no /api/studio/strategies (Studio->gateway draft contract, ALG-3352); demo-only studio serves 6 built-in template versions (/demo/studio); NoFX Studio does not save through the gateway |
| 2 | Gateway accepts and dispatches | **stubbed** | GET /health -> 404 (gateway contract health route); redis algobots:cmd:* streams: 1 |
| 3 | Nautilus 2.0.0rc6 paper run fills orders | **wired** | nautilus-node nautilus_trader: 2.0.0rc6 (pin 2.0.0rc6); fills on trader-*:algobots:events.order_filled.*: 1 |
| 4 | Market data reaches the node | **missing** | feed path: /feeds/kalshi/observations.jsonl; feed age: absent; intervals processed by workers: 0 |
| 5 | marimo renders evidence from the run | **stubbed** | marimo HTTP: 303; notebooks marked 'ALG-3403 evidence': none; marimo is up but no notebook reads the paper run's fills/PnL/data timestamps |

full loop: FAIL (1/5 hops wired)
