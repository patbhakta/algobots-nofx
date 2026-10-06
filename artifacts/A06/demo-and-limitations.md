# A06-1 — Nautilus paper workers, one isolated process per demo account (ALG-3255)

Parent: ALG-3248 (demo sprint) · Packet: A06 (ALG-3102) · nautilus_trader 1.231.0

## What runs

`ALGOBOTS_DEMO_WORKERS_ENABLED=1` makes the API's lifespan start a
`Supervisor` (`src/algobots/workers/supervisor.py`), which spawns one OS
process per demo account:

    python -m algobots.workers.paper --account {laya|jev|coin} --poll 15

Each worker (`src/algobots/workers/paper.py`) owns its own Nautilus kernel:

| account | trader_id   | strategy_id      | order_id_tag | paper venue  | venue account   |
|---------|-------------|------------------|--------------|--------------|-----------------|
| laya    | PAPER-LAYA  | DemoPaper-LAYA   | LAYA         | PAPER_LAYA   | PAPER_LAYA-001  |
| jev     | PAPER-JEV   | DemoPaper-JEV    | JEV          | PAPER_JEV    | PAPER_JEV-001   |
| coin    | PAPER-COIN  | DemoPaper-COIN   | COIN         | PAPER_COIN   | PAPER_COIN-001  |

Nautilus numbers every simulated account `<venue>-001`, so the venue name
carries the account key; instrument IDs are therefore namespaced too
(`KXBTC15M-26OCT061830-NO.PAPER_LAYA`). Client order IDs embed the trader and
order tags (`O-20261005-224504-LAYA-LAYA-164`), and every order is tagged
`acct:<key>` and `event:<kalshi event>`.

**Orders are driven by the existing live decisions.** Every poll the worker
replays the Laya forward-observer feed through `algobots.demo.ledger.build`
with the live kill-switch state. That is the same function the dashboard
uses, so the risk envelope, daily-loss cap and kill switch decide identically.
For each new FILLED decision it lists that interval's YES/NO `BinaryOption`
on its paper venue, quotes the PoC's assumed 50c mid, and submits a market
BUY for `floor(stake / 0.50)` contracts. The venue is Nautilus's simulated
exchange (sandbox/paper). No live data or execution client exists in the
process, so it cannot reach a broker.

## Status: `GET /demo/api/workers`

`WorkerStatus` per account comes from two independent sources. `/proc`
supplies alive, RSS and CPU seconds, and the worker's own heartbeat file
(`<state_dir>/workers/<acct>.json`) supplies readiness, last heartbeat and
order counts. The states are `not_started`, `starting`, `ready`, `stale`
(heartbeat older than 60s), `exited` (died, with its exit code) and `stopped`
(stopped by the supervisor). A dead worker is **not** auto-restarted, so a
kill stays visible. `Supervisor.start("<acct>")` restarts a single account.

## Evidence (live feed, 2026-10-06 ~22:49Z, poll 5s)

- `processes.txt`: three separate PIDs, all children of the API process. The
  ledger's fills (`laya 164 / jev 83 / coin 130`) equal each worker's
  `orders_filled`.
- `workers-before-kill.json`: all `ready`, startup ~1.8s, RSS ~345 MB each.
- `workers-after-kill.json`: after `kill -9` on jev, jev is `exited` with
  `exit_code -9`. laya and coin are still `ready`, with heartbeats after the
  kill.
- `after-next-interval.json`: the next 15-minute interval arrived with jev
  still dead, and the surviving workers' order counts advanced.
- Tests: `tests/workers/test_supervisor.py` covers N processes, kill
  isolation, restart and stop. `tests/workers/test_paper.py` checks that
  orders equal ledger fills, that nothing is resubmitted, that the kill
  switch blocks orders, and that IDs are unique.

## Limitations (honest)

- **No settlement in the paper venue yet.** The venue account is frozen and
  positions stay open, so `demo/ledger.py` remains the P&L source of truth.
  The workers prove isolated per-account order flow, not P&L.
- Fills are at the assumed 50c mid because the PoC feed records no order book.
  Contract counts are floored, so a $5.40 stake becomes 10 contracts ($5.00
  notional).
- Each worker replays the feed from `demo_start` on boot, so a restarted
  worker re-submits the history into its fresh in-memory venue. Nautilus
  state is not persisted between restarts.
- About 345 MB RSS per worker. Three accounts use about 1 GB, which is fine
  on this 15 GB host but is the number to watch for fan-out (A11).
- The terminal Accounts-pane worker column (slice c) belongs with A10-2
  (ALG-3254), which renders `/demo/api/workers`.
