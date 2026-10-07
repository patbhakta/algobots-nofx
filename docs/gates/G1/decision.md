# G1 gate decision — five-capability paper demo (A12-1, ALG-3257)

Date: 2026-10-07 · Repo: `algobots@origin/main` · Run: `make demo-g1`
(evidence: `artifacts/A12/`, screenshots `demo-1440.png` / `demo-390.png`)

**The call:** the five G1 capabilities are **proven as machinery** on this VPS,
on paper, on synthetic feeds. That is all that is proven. The strategies have
**no edge** — expected, they are reference deciders — so nothing here is
evidence of profitability, and no live venue is wired or approved. Going to
live money is **blocked** on real edge + venue integration + risk sign-off.

## Proven (this run, `artifacts/A12/demo-run.json`)

| # | Capability | Evidence |
|---|------------|----------|
| C1 | Multi-account | three paper accounts (`laya`, `jev`, `coin`), per-account scoping: `GET /demo/api/decisions?account=jev` returns jev only; grants enforced (403/404 on ungranted keys — A10-2 tests) |
| C2 | Multi-strategy | all three strategies deciding from the same feed (per-strategy books, decisions, P&L in `/demo/api/state`) |
| C3 | Multi-worker isolation | one OS process per account, distinct PIDs, separate Nautilus traders (`PAPER-LAYA-001` …); a fill on one account is executed by that account's worker only (`worker_trader_id` in the order book) |
| C4 | Risk denial with stated reason | LIVE mode refused (`live_disabled`, 422); kill switch engaged → next order's legs `blocked`, `denial_code=kill_switch`, reason "kill switch engaged — entry blocked", every flip audited in `kill-switch.json` history |
| C5 | Kill / restart / reconciliation | app level: SIGKILL one worker → the other two keep heartbeating, the dead account refuses entries (`worker_unavailable`, 503, reason names the dead lease — no fallback exists). Engine level (`artifacts/A12/engine/`): kill → restart → entry-frozen `reconciling` → `ready` with orders restored from the durable ledger; other accounts never paused |

Trace IDs (parent / leg / worker order / worker trade per fill, plus denial
records) are collected in `artifacts/A12/demo-run.json` → `trace_ids`.
Resource report (per-worker and pooled RSS/CPU p50/p95, startup, engine
callback latency): `artifacts/A12/resource-report.json` and
`artifacts/A12/engine/measurements.json`. Measured on this host for this run
only; no fleet capacity is inferred.

## Simulated (honest stand-ins, not the real thing)

- **Market data**: a synthetic feed of prior settled 15 m intervals stands in
  for Laya/Kalshi observations; fills at the assumed 0.50 mid with Kalshi
  taker fee on the paper venue (Nautilus BacktestEngine), not real quotes.
- **The newspaper-style narrative layer is gone** (ALG-3288 rebuilt /demo as a
  functional terminal: accounts / positions / orders / risk blotters, dense
  data, no vintage styling).
- Kill/restart at the **app** layer shows refusal + visibility only; the
  restart-with-reconcile proof runs at the engine layer (by design: the app
  does not auto-restart a killed worker — a kill stays visible).

## Blocked (needs other work before true)

- **Live trading**: no venue integration, no LIVE mode (refused at the gate),
  no approvals path for real money.
- **Any edge claim**: blocked on strategy research; nothing in A12 measures or
  implies profitability.
- **Fleet capacity**: blocked on more accounts/hosts than this demo runs.

## Failed

- Nothing in this run. (Prior gate runs' failures, if any, are superseded by
  this run's green `make demo-g1`.)

## How to demo it

The collapsible **HOW TO DEMO G1 — 5 steps** card sits at the top of the
terminal (`/demo`), or run `uv run --extra workers make demo-g1` and read
`artifacts/A12/`.
