# NautilusTrader setup on .243 — ops + rc6 notes (ALG-3339 ms2a docs pass)

- Status: living doc (update on image/RC bumps)
- Date: 2026-10-13
- Scope: how the engine runs here, the 2.0.0rc6 API deltas that bite, backtest config,
  adapters law, data catalog — consolidated from microsprints 1–2a.

## Topology (tailnet-only, .243 = 100.82.57.72)

| Surface | Container | Endpoint | Notes |
| --- | --- | --- | --- |
| Research UI | nautilus-marimo (:8202) | marimo edit, token auth | 298 notebooks from FunnyTree |
| Dashboard | nofx-frontend (:8201) | nginx → nofx:8080 | resolver fix mounted (reboot-order safe) |
| Trading app | nofx-trading (:8200) | /api/health | |
| Control plane | algobots-api-1 (:8000) | /healthz | Nautilus paper workers inside |
| Bridge channel | /opt/algobots-stack/bridge | file channel | local disk by design (not sshfs): the PaperWorker drain path rides it every poll |

Statelessness law (Pat, RC-isolation): containers carry code only; notebooks/code/data on
FunnyTree. Runtime bridge state stays local — trading-path I/O does not cross sshfs.

## Kernel smoke test

`nautilus_smoke.py` in the marimo work dir (FunnyTree). PASS = `BacktestEngine(config=…)`
builds the full kernel and disposes cleanly. Re-verified 2026-10-13T21:09Z (ms2a docs pass).

## rc6 API notes (break vs 1.x tutorials)

1. `BacktestEngine(config=BacktestEngineConfig(…))` — `config` is a required kwarg now.
2. Testkit module is `nautilus_trader.testkit` (not `test_kit`).
3. Currencies moved (`nautilus_trader.model.currencies` paths differ from old tutorials).
4. `pandas` is NOT a nautilus dependency anymore — anything data-frame-facing imports it
   explicitly; the marimo image carries `pandas matplotlib plotly scipy statsmodels`.
5. marimo-converted notebooks: cross-file imports need plain modules (cells are function
   bodies) — see `notebooks/nautilus-tutorials/*_strategy.py` / `orderbook_frames.py`;
   `ImportableStrategyConfig` takes `module:Class` paths, which must point at those modules.
6. Old (1.x) nautilus tutorials are expected to break on imports — RC reality; the 6
   converted ones are fixed and 6/6 PASS headlessly (`marimo export html`).

## Backtest config — canonical in-repo example

`src/algobots/engine/workers/paper.py` (`PaperWorker`) is the maintained example:
venue + OMS + account type + frozen cash account, instrument registration, quote-tick
replay, fills from `OrderFilled` events only. The demo tutorials show the `BacktestNode`
catalog-driven variant (`backtest_orderbook_*.py`).

## Adapters law (ADR 0001, unchanged)

- Every order/fill goes through a Nautilus `ExecutionClient`. No bypass routes.
- Execution per account: `sandbox` (default) or `adapter:<name>`; adapter specs are
  **external mutations** — refused without an authorization record (A06 Authority line).
- First US paper adapter: Interactive Brokers (`adapter:interactive_brokers`), needs
  `nautilus_trader[ib]` + IB Gateway 4002 + paper-enabled account.
- OpenAlgo is reference-only (feature matrix: `docs/research/openalgo-feature-reference.md`).

## Data catalog

- `ParquetDataCatalog` is the engine-native store; tutorials write `catalog/` under the
  working dir and lazy-load by instrument/time-range from a `BacktestNode`.
- Bulk exchange archives (Binance/Bybit) are opt-in: `NAUTILUS_DATA_DIR` + row caps; the
  tutorials default to the 100-row test samples.

## NoFX fork decision (Pat to ratify)

Multi-tenant branding options:

| Option | Cost | When it's right |
| --- | --- | --- |
| **A. Stay stock + mounted overrides** (today: nginx conf override only) | ~zero; upgrade = `pull && up -d` | branding = colors/logo via env or runtime config if NoFX exposes it |
| **B. Fork frontend** for branding/i18n/multi-tenant chrome | drift maintenance; every upstream release needs a rebase; we own CI + image publishing | NoFX lacks runtime theming AND multi-tenant UI is a product requirement |
| **C. Thin proxy shell** — our own branding page/portal in front, NoFX embedded per tenant | medium; coupling only at embed boundary | fastest branding without forking; SSO seam needed anyway |

Recommendation: start at **A**, move to **C** when multi-tenant arrives, and treat **B** as
last resort (forking a fast-moving upstream for skin-deep changes buys a permanent rebase
tax). Decision owner: Pat.
