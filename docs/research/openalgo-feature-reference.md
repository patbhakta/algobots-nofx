# OpenAlgo feature reference — ALG-3339 microsprint 2 pull

- Status: reference (ADR 0001 §3: OpenAlgo is reference-only — not imported, proxied, or used as an order route)
- Date: 2026-10-13
- Source: github.com/marketcalls/openalgo README @ main (fetched 2026-10-13)
- License note: OpenAlgo is **AGPL-3.0**. We pull *patterns and ideas only*. No code, no asset copying.

## What OpenAlgo is (Oct 2026)

Self-hosted Flask + React 19 trading platform: 36 broker plugins, unified `/api/v1`
REST contract (57 method/path pairs), WebSocket/ZMQ market data, no-code Flow builder,
hosted Python strategies, AI agent with per-order approval, 12 options tools.

## Feature pull matrix (pattern → where it lands in our stack)

| # | OpenAlgo pattern | Worth pulling? | Landing zone in AlgoBots |
| --- | --- | --- | --- |
| 1 | Unified REST order contract: place/modify/cancel, basket orders, smart orders w/ position sizing, auto-split | Yes — contract shape only | `src/algobots/api/` surface for the NoFX↔Nautilus bridge (orders flow through control plane → Nautilus `ExecutionClient`, never around it) |
| 2 | Analyzer Mode sandbox: virtual capital, MARKET/LIMIT/SL/SL-M, margin w/ leverage, scheduled square-off, isolated DB | Yes — square-off schedule + margin realism | Nautilus `sandbox` venue (`PAPER_<ACCT>` workers); square-off as engine schedule, not ledger logic |
| 3 | Action Center: auto vs semi-auto order approval, bulk approve, IST-stamped audit trail | Yes — UX pattern | A06 Authority line: approval *before* adapter specs; our `approvals` router + audit trail already exist; add bulk-approve UX later |
| 4 | Webhook triggers (TradingView/ChartInk/generic) | Yes — generic webhook intake | Control-plane API endpoint that creates *intents* (file channel `bridge/intents/` shape matches) |
| 5 | WebSocket + ZMQ bus for normalized market data | Later | Market-data distribution to NoFX frontend; Nautilus is the source of record for fills |
| 6 | PnL Tracker / Latency Monitor / Traffic Monitor | Yes — bridge observability | Latency + traffic stats on the bridge endpoints (microsprint 3 acceptance criteria) |
| 7 | Telegram bot: alerts, orderbook/positions on demand | Later | Notification surface; requires bot credential (secret-proposal path) |
| 8 | Security stack: Argon2, Fernet+PBKDF2, TOTP, rate limits, IP ban dashboard, CSP/CSRF | Yes — checklist | Control-plane hardening audit (separate card) |
| 9 | Options analytics suite (12 tools: vol surface, GEX, max pain…) | No — not our product (US binaries cousin exists via ForecastEx per ADR 0001) | — |
| 10 | AI agent: per-order explicit approval, LLM-agnostic (LiteLLM) | Pattern only | Already our law: external mutations need authorization; any AI surface inherits A06 gates |
| 11 | Hosted Python strategy editor w/ process isolation + scheduling | No — Nautilus jupyter (:8202) is our strategy surface | — |

## Law guardrails (from ADR 0001, restated)

1. Every order and fill goes through a Nautilus `ExecutionClient` — a NoFX-side
   order route that bypasses the engine is a violation, not a feature.
2. OpenAlgo is never an order route, proxy, or import — including its unified API
   shape being *deployed* rather than mirrored in our own contracts.
3. Broker connections (paper included) are external mutations needing authorization.

## Microsprint-3 candidates ranked from this pull

1. Order-intent webhook on the control plane → `PaperWorker` (Nautilus) → fills JSONL → NoFX view (matrix #1+#4+#6).
2. Square-off schedules for sandbox venue (#2).
3. Control-plane security audit vs #8 checklist.
