# A06-4 — Nautilus execution adapter inventory (ALG-3270)

Source: the installed `nautilus_trader==1.231.0` (`.venv/lib/python3.12/site-packages/nautilus_trader/adapters/`),
read from each adapter's `config.py` / `factories.py`. Nothing was connected.

## Answer first: the demo venue

**There is no Nautilus adapter for Kalshi.** The demo trades Kalshi binaries via the Laya feed
(`/opt/laya/kalshi/observations.jsonl`), and `grep -ri kalshi nautilus_trader/` returns nothing.
The closest shipped adapter, `polymarket`, is a different venue (Polygon CLOB, wallet-signed). Its
international venue is not open to US persons. So the demo keeps its Kalshi-shaped instruments on
the in-process `sandbox` venue. A real Kalshi path would need a custom `LiveExecutionClient`, and
that is out of scope here.

## US-relevant execution adapters

| Adapter | Asset classes | Paper / sandbox | Credentials (env) | Infra |
|---|---|---|---|---|
| `interactive_brokers` (Python, needs the `nautilus_trader[ib]` extra; `ibapi` is **not installed** today) | US equities, ETFs, options, futures, FOPs, FX, bonds, CFDs, crypto (Paxos) | **Yes.** An IB paper account through the paper gateway, port 4002 (TWS paper 7497) | `TWS_USERNAME`, `TWS_PASSWORD`, `TWS_ACCOUNT` (paper `DU…` id) | IB Gateway or TWS running and logged in. Self-hosted, or the adapter's `DockerizedIBGatewayConfig` (needs Docker). Set `read_only_api=False` |
| `interactive_brokers_pyo3` | Same as above (Rust bindings) | Same | Same | Same. Config only in 1.231 (no `factories.py`), so not wireable yet |
| `kraken` | Spot crypto; crypto futures | **Futures only:** `environment=DEMO` (demo-futures.kraken.com). Spot has no demo | `KRAKEN_API_KEY`/`SECRET`; demo: `KRAKEN_FUTURES_DEMO_API_KEY`/`SECRET` | None (REST and WebSocket). Kraken spot serves the US except some states. Kraken futures for US persons is a separate entity, so the demo is a test bed only |
| `binance` with `us=True` (Binance.US) | Spot crypto | **No.** Binance testnets are for binance.com only, and Binance.US has none | `BINANCE_US_API_KEY`/`SECRET` | None |
| `architect_ax` | Perpetual futures (AX Exchange) | **Yes.** `AxEnvironment.SANDBOX` is the default | `AX_API_KEY`, `AX_API_SECRET` | None. US-person eligibility not verified |
| `sandbox` | Any instrument (simulated fills on live data) | It *is* the paper mode | None | Needs a live **data** client to feed its matching engine |

## Shipped but not usable from the US (recorded so they are not re-evaluated)

`binance` (.com), `bybit`, `okx`, `bitmex`, `deribit`, `hyperliquid`, `dydx`, and `polymarket`
(international) all exclude or geoblock US persons. `betfair` serves UK/EU betting exchanges. Most
have testnets (`environment=TESTNET/DEMO`), but those are not a route to US execution.

`databento` and `tardis` are data only and have no execution client.

## Seam mapping (this slice)

`src/algobots/engine/workers/execution.py` `ADAPTERS` knows `interactive_brokers` and `kraken`.
`AccountWorkerSpec(account, "adapter:<name>")` builds the `TradingNodeConfig` with that adapter's
exec client and the same `DemoPaperStrategy`. `PaperWorker` refuses to start it
(`AdapterNotAuthorized`) until the A06 Authority line authorizes a broker connection.
