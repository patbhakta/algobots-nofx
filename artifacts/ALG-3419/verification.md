# Live Kalshi paper-loop visibility

Deployed 2026-10-25 on http://100.82.57.72:8201/strategy.

The existing authenticated `/api/nofx/studio/live` API reads Kalshi observer freshness, strategy decisions, and Nautilus paper-worker heartbeat reports. It now preserves worker positions. The NoFX panel opens by default and shows a strategy selector, submitted orders, fill counts, equity, settled strategy PnL, open positions, and the latest ten actual fill receipts with order/trade IDs. The existing twenty-second poll updates all fields. Unknown unrealized PnL stays unavailable.

Validation: 18 authenticated API tests passed; frontend TypeScript/Vite production build passed; one UI regression passed, proving strategy filtering and a polling-driven fill-count update. Deployed frontend returns 200; live API rejects unauthenticated callers with 401. After graceful API recreation, laya/jev/coin workers were ready (24/0/209 fills).

API commit: bcdc3b7. NoFX commits: ffe31c3d and ea01808d (layout correction). Exact patches are attached. GitHub pushes failed: HTTPS has no usable credential helper, and SSH identity was refused. No pushes or main merges are claimed. The deployed NoFX baseline itself is 29 commits ahead of remote main before this issue’s changes, so that existing branch history must also be reconciled for the requested main-merge acceptance.

Deployment: UI image `algobots/nofx-frontend:alg3419-paper-loop`, prior image `alg3418-backtest`; compose backup `/opt/algobots-stack/docker-compose.yml.bak-alg3419`. API image `algobots-api:alg3419`, prior `algobots-api:before-alg3419`. The API image applies only the position-preservation deletion to the installed module, preserving a pre-existing deployed seed-lock fix. Source checkout edits were preserved. API workers shut down through the existing 45-second grace period and resumed ready.

Browser screenshots and summary accompany this report. A polling refresh is separate from observing a new natural fill; consult `fills_increased` in the summary before claiming that acceptance condition.
