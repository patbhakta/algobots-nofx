# ADR 0001 — Nautilus is the execution spine

- Status: accepted
- Date: 2026-10-07
- Issue: ALG-3270 (A06-4), parent ALG-3102 (A06)
- Decision owner: Pat Bhakta (role decision, 2026-10-06 23:12Z)

## Context

The A06-1 paper workers already run `DemoPaperStrategy` inside a Nautilus engine against a simulated
venue (`PAPER_<ACCT>`). Their fills were never surfaced as the record, though, and `demo/ledger.py`
computed P&L independently. OpenAlgo had been considered as a broker bridge. Pat decided that
NautilusTrader is both the broker bridge and the execution engine for US markets, and that OpenAlgo is
a feature reference only.

## Decision

1. **Every order and every fill goes through a Nautilus `ExecutionClient`.** Strategies submit
   orders through `Strategy.submit_order`. Fills are recorded only from Nautilus `OrderFilled`
   events (`DemoPaperStrategy.fills`). No code path computes a fill outside the engine.
2. **The client is chosen per account by config** (`AccountWorkerSpec.execution`, read from
   `ALGOBOTS_WORKER_EXECUTION`):
   - `sandbox` (default in tests and on the demo): the in-process simulated venue, matched by
     Nautilus' own matching engine;
   - `adapter:<name>`: a shipped Nautilus `LiveExecutionClient` in a `TradingNode`, running the
     same strategy class with the same config.
3. **OpenAlgo is reference-only.** It is not imported, proxied, or used as an order route.
4. **The ledger becomes a reconciliation target, not the fill source.** `reconcile_fills` diffs the
   Nautilus fill events against the ledger's FILLED decisions. The only difference today is
   whole-contract flooring at 50c (`artifacts/A06/fills-reconciliation.json`: coin $0.00,
   jev $17.10, laya $28.08 of stake not filled, with 0 missing or extra fills). Moving P&L truth to
   the Nautilus portfolio waits until settlement is modelled in the venue.
5. **Connecting any broker account, paper included, is an external mutation.** It needs separate
   authorization under the A06 Authority line. Until it is granted, `PaperWorker` refuses adapter
   specs with `AdapterNotAuthorized`.

## First US paper adapter: Interactive Brokers (`adapter:interactive_brokers`)

Reasons:
- **It is a real paper account at a US broker.** IB paper accounts (`DU…`) use IB's own simulated
  matching under the same API as live, so moving paper to live changes credentials, not code.
- **Its asset class coverage fits the product.** It covers US equities, options, futures, and ETFs,
  plus event contracts through ForecastEx. That is the nearest regulated cousin of the Kalshi
  binaries the demo trades today.
- **Nautilus' most mature live adapter.** It has a dockerized gateway option and is the reference
  US-equities integration.

Costs: it needs the `nautilus_trader[ib]` extra (`ibapi` is not installed today), an IB Gateway
process (port 4002, `read_only_api=False`), and an IB account with paper trading enabled.

Rejected as first choice:
- **Kraken futures demo.** It needs no gateway and is easy to try, but it is crypto-only, and its
  futures are not the US-person product.
- **Binance.US.** It has no paper mode.
- **AX.** Its US-person eligibility is unverified.
- **Polymarket.** It is not available to US persons.
- **Kalshi.** Nautilus has no adapter for it. See `artifacts/A06/adapters.md`.

## Consequences

- One strategy codebase serves the sandbox, paper, and live paths. Config swaps the venue.
- Kalshi stays sandbox-only unless someone writes a custom Kalshi `LiveExecutionClient`, which would
  be a separate card.
- Before an adapter spec can start, it needs an authorization record plus the credentials listed
  in `execution.ADAPTERS`.
