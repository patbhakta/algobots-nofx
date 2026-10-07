# A06-1 — Nautilus paper workers, one isolated process per demo account (ALG-3255)

Parent: ALG-3248 (demo sprint) · Packet: A06 (ALG-3102) · nautilus_trader 1.231.0

## What runs

`ALGOBOTS_DEMO_WORKERS_ENABLED=1` makes the API's lifespan start a
`Supervisor` (`src/algobots/engine/workers/supervisor.py`), which spawns one OS
process per demo account:

    python -m algobots.engine.workers.paper --account {laya|jev|coin} --poll 15

Each worker (`src/algobots/engine/workers/paper.py`) owns its own Nautilus kernel:

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

Captured at commit 761ccf8, when the module was still `algobots.workers`
(hence the `ps` command lines). It moved to `algobots.engine.workers` to sit
inside A06's write scope in `docs/repository-map.json`, and the code is
otherwise unchanged; `smoke-after-move.txt` re-runs it from the new path.

- `processes.txt`: three separate PIDs, all children of the API process. The
  ledger's fills (`laya 164 / jev 83 / coin 130`) equal each worker's
  `orders_filled`.
- `workers-before-kill.json`: all `ready`, startup ~1.8s, RSS ~345 MB each.
- `workers-after-kill.json`: after `kill -9` on jev, jev is `exited` with
  `exit_code -9`. laya and coin are still `ready`, with heartbeats after the
  kill.
- `after-next-interval.json` and `heartbeats-after-next-interval.txt` (23:00Z):
  the next live interval arrived while jev was dead. laya and coin processed
  it (`intervals` 397 → 398) and jev did not (stuck at 397). That interval had
  no FILLED decision in the ledger (Laya abstained, Jev's sleeve is exhausted,
  Coin hit the −$40 daily cap), so correctly no new orders were placed. Order
  submission on new intervals is covered by
  `test_worker_submits_exactly_the_ledger_fills_and_only_new_ones`.
- Tests: `tests/engine/workers/test_supervisor.py` covers N processes, kill
  isolation, restart and stop. `tests/engine/workers/test_paper.py` checks that
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

## A06-2 — ownership lease, takeover denial, reconcile-before-entries (ALG-3258)

**Ownership.** `src/algobots/engine/workers/lease.py` keeps one lease per
tenant/account/environment at
`<state_dir>/workers/leases/demo.<account>.paper.lease`. Each lease holds the
owner PID, its kernel start time, its host and its PID namespace.
`Supervisor.start` runs check, spawn and record under an `flock`, so two API
processes can't both win. The worker re-acquires the lease itself at boot, and
a worker that loses the race exits with code 75 (state `denied`). `start` raises
`LeaseDenied`, and `WorkerStatus.state` is `denied` with `denied_reason` and
`lease_pid`, when:

- a live process holds the lease (the same PID with the same start time), or
- liveness can't be confirmed: the lease is from another host or PID namespace
  (e.g. a container that was hard-killed), the file is unreadable, or `/proc`
  can't be read.

Takeover happens only when the old owner is confirmed terminated: its PID is
gone, a zombie, or reused by another process. A clean stop releases the lease.
A crash leaves it behind, and the next start takes it over once the PID is
confirmed dead. For the uncertain case:

    python -m algobots.engine.workers.lease show          --account laya
    python -m algobots.engine.workers.lease force-release --account laya   # refuses a live owner

**Lifecycle.** `starting → reconciling → ready → stopped | exited | denied`,
plus `stale`. A fresh or restarted worker is entry-frozen: `queue()` refuses and
counts every entry (`orders_rejected_frozen`) until `reconcile()` has replayed
the durable ledger, which restores past fills into the paper venue
(`orders_restored`). Then the heartbeat reports `reconciled: true` and the
supervisor reports `ready`. There is still no auto-restart. A crashed account
stays `exited`, and therefore frozen, until someone starts it again, while the
other accounts keep trading.

**Verification.** `make verify-A06` runs `tests/engine/workers` and
`tests/packets/A06`, then writes `artifacts/A06/acceptance.json`: AC2–AC4 PASS,
and AC1 and AC5 PENDING. AC1 is PENDING because the demo has 3 accounts, not 4;
AC5's p95 RSS/CPU measurement is A06-3. `test_paper` needs the `workers` extra.
Without it, AC1 and AC3 report PENDING, never PASS.

**Limitations.** Ownership is per host. There is no distributed lock and no
automatic failover, as the A06 exclusions state. A hard-killed container leaves
leases that the next container can't verify, so they need `force-release`. A
clean `docker compose up` sends SIGTERM to the API, which stops the workers and
releases the leases.

**Live check (A06-2).** `artifacts/A06/lease-live-check.txt` was captured on the API image built
from `origin/main` `4e340c6`, in an isolated container: network none, a copy of the live demo
state, and the live feed mounted read-only. It shows:

- All 3 workers `ready` and `reconciled`. Each reconciled to exactly the order counts on the
  live API (203/120/159).
- A second API process denied on every account, with no spawn.
- `force-release` refusing a live owner.
- After a SIGKILL of coin: coin `exited`, its lease confirmed dead, and the others still `ready`.
- A takeover going `starting → reconciling` (0 submitted) `→ ready` (159 restored), and the
  lease released on stop.

**Production.** `algobots-api-1` was rebuilt at 2026-10-07T11:52Z from `0f0c469`, which
includes A06-2. `GET /demo/api/workers` reports `enabled/ready: true`, with all three
accounts `ready`. Each worker is `reconciled: true` with `lease_pid == pid` (19/20/21), and
`orders_restored` is 203/120/159 with 0 frozen rejections. Leases are at
`/var/lib/algobots-demo/workers/leases/demo.<acct>.paper.lease`.

## A06-3 — isolation hardening + 4-account / 8-deployment measurements (ALG-3259)

**Isolation.** Every worker now starts through `algobots.engine.workers.sandbox`.
It gets a scoped env (only its own `ALGOBOTS_ACCT_<ACCT>_*` secrets),
`RLIMIT_AS` 4 GB, `nice +10`, an optional non-root UID, and it fails closed if
research code or `stock-vaults` is readable. Each worker records what was
enforced and what was only asserted in `<state>/workers/<acct>.sandbox.json`.
The full table is in `deploy/workers/README.md`. In short: UID, memory, env and
forbidden paths are **enforced**. Network egress and a per-worker CPU-rate cap
are **asserted only** in the container (there is no `CAP_SYS_ADMIN` and no
cgroup delegation). The live compose doesn't set `ALGOBOTS_WORKER_UID` yet, so
production workers still run as root until it does.

**Declared fixture.** `algobots.engine.workers.fixture` defines four synthetic
paper accounts, `syn1`–`syn4` (the fourth makes AC1's "four accounts"
literal). Each runs two strategies, `EveryN-<ACCT>` and `Dip-<ACCT>`, so there
are **eight deployments**. Each account has its own Nautilus kernel, paper
venue `PAPER_<ACCT>`, lease and heartbeat. A deterministic synthetic quote
stream drives it at 4 Hz per instrument, and the poll is 1 s.

**Run** (`demo-run.log`, `demo-run.json`, `measurements.json`). The run used
the API image `algobots-api:latest` with this branch's `src` mounted, the
supervisor as root and workers dropped to **UID 65534**, sampling for 120 s on
a host with 8 vCPU (kernel 6.8).

| metric (pooled, 4 workers) | p50 | p95 |
|---|---|---|
| RSS (MB, 1 Hz /proc samples, n=480) | 343.3 | 348.2 |
| CPU (% of one core per 1 s step, n=476) | 0.0 | 1.0 |
| startup (spawn → reconciled, s, n=4) | 3.34 | 3.49 |
| strategy callback latency (scheduled tick → `on_quote_tick`, ms, n=2000) | 503 | 963 |
| queue depth at drain (p95, worst worker) | — | 8 |
| queue age at drain (p95, worst worker, ms) | — | 995 |

The callback latency and queue age are dominated by the 1 s poll. Quotes wait
in the inbound queue until the next drain. The engine's own per-tick cost is
in `workers.*.per_tick_engine_ms_p95`. **No fleet capacity is inferred**
(`capacity_extrapolation: null`). These numbers hold only for this fixture on
this host.

**Demo.** All four accounts were `ready` with four distinct PIDs and trader
IDs, and every worker reported `uid 65534`. `syn2` was SIGKILLed after the
sampling window. syn2 went `exited`, and in the next 5 s syn1, syn3 and syn4
each processed +40 ticks while syn2 processed 0. After the restart, syn2's
heartbeat went `reconciling → ready`. It stayed entry-frozen until it had
replayed its durable fill log (156 fills restored), and only then traded.

**Limitations.**
- No per-worker CPU-rate cap. Only the container-level compose limit is
  honest on this host, and it isn't set yet.
- Egress is blocked only where `unshare(CLONE_NEWNET)` is allowed, which is
  not the case in the API container. There, "no broker egress" means no
  live client and no broker credentials.
- The fixture is synthetic: no Laya feed and no ledger. The three real demo
  accounts still run `paper.py`.
