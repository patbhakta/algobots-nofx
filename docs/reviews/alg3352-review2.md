# Pat UI review #2 — October 23, 2026

Dashboard reference: `patbhakta/algobots-nofx` main at
`fff86092cdbb4c62bee65fc808990e828a8e7a50`,
`web/src/components/terminal/TerminalDashboard.tsx`. The terminal panel layout,
CSS, typography, metrics strip, topology, execution log and book/history slots
come from that component. The route had substituted a receipt-only page.
The delta is data wiring: authenticated Nautilus paper evidence, account
selector and observed Kalshi quotes. Unsupported liquidation, holder statistics,
candle history and risk telemetry are explicitly unavailable. Paper mode makes
no retired backend, paid feed or Hyperliquid socket requests and cannot invoke
position-close controls or the upstream synthetic showcase toggle.

Navigation order in desktop and mobile: Dashboard, Data, Strategy, Leaderboard,
FAQ, Config. Config remains deferred.

Strategy save now uses the shared authenticated CRUD client. Risk defaults use
nullish fallback: zero is a valid confidence floor, not a missing value. The UI
includes the currently configured confidence value in its options and preserves
separate BTC/altcoin leverage values. Name-only PUT worked in the baseline
isolated browser test: Pat's exact production failure has not been reproduced.
A concrete load/save corruption was found: `min_confidence: 0` became `78` via
`||`. Browser regression verifies zero survives a name edit, then a changed
confidence value survives PUT and reload. No running paper worker is changed.

Leaderboard uses the existing Recharts dependency: hit-rate and Brier bars,
plus an equity line per account. Scores come from scoped settled decisions;
equity comes from the same demo ledger replay used by evidence. Values remain
decimal strings at the API boundary. The UI labels replay equity and sleeve
refills, and does not call those curves historical worker cash balances.
Unavailable values remain missing; no fabricated chart samples are inserted.

## OpenBB research (posted before Data integration)

The Oct 18 assessment remains applicable: an optional read-side research
adapter, with Nautilus execution/backtesting and marimo retained. No OpenBB
integration, package installation, or Data redesign is included here.

Current upstream `openbb` 5.0.0 supports Python >=3.10, but its meta-package
includes CLI, REST, MCP, charting/PyWry and many providers. Core 2.0.1 has no
Jupyter dependency; its FastAPI/Uvicorn/Pydantic/aiohttp/WebSockets requirements
must be resolved against the Python 3.12-slim API image before integration.
Python version compatibility is not dependency compatibility. Container disk,
RSS and cold-start footprint have not been measured. A minimal selected
extension and separately resolved lock is preferable to the default bundle.

No first-party Kalshi/Polymarket provider appears in the inspected provider
inventory. Those views require a separate adapter for market/event identifiers,
YES/NO quotes, timestamps, pagination and settlement lineage. OpenBB does not
provide our account-scoped decisions, scores or Nautilus paper receipts.

Sources checked October 23:

- https://raw.githubusercontent.com/OpenBB-finance/OpenBB/develop/openbb_platform/pyproject.toml
- https://raw.githubusercontent.com/OpenBB-finance/OpenBB/develop/openbb_platform/core/pyproject.toml
- https://docs.openbb.co/odp/python/migration-from-v4
- Cached provider inventory at upstream revision `cbf37e1f98a61d4e17ff1df43441fd4004774cac`.

## Verification scope

Production frontend build passes. The API regression suite covers authenticated
NoFX CRUD, tenant separation, feed projection, scored accounts and decimal,
account-scoped equity curves. Opt-in browser test uses the built frontend and
real API handlers against a migrated, isolated database with fixture credentials.
It verifies login/dashboard, navigation order, no external dashboard requests,
name/risk PUT/reload, and chart rendering. Fixture screenshots are layout
verification, not production execution evidence. Final invited production-login
review remains Pat's acceptance step; no deployed credentials were discovered.
