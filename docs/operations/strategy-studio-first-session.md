# Pat first-session walkthrough — October 23, 2026

Live demo: http://100.82.57.72:8201 (tailnet; existing invited login)

All five requested screens passed an actual Chromium walkthrough against the deployed frontend and backend:

1. A freshly invited user signed in through the login form and landed at `/dashboard`.
2. Data displayed the Kalshi feed: 105 observations, 312 logged decisions, 147 settled decisions. The probability source was `mom3x15m/vol20`; missing/stale inputs retain explicit states.
3. Pat's active tenant received `Kalshi BTC 15m momentum`. Studio shows editable controls immediately; the long paper-receipt history is collapsible. A separate temporary invited user created, edited, saved, and activated a strategy through the UI. The active record was confirmed through the API.
4. Leaderboard displayed Laya, Jev, and Coin scores from the same decision-quality scorer as `/demo/api/decisions`, including sample counts, hit rate, Brier score, and verdicts. Jev's zero settled decisions remain explicit.
5. Config showed account/workspace information and a link to Studio; unsupported personal provider/credential settings are explained rather than rendering a blank screen.

Both `/api/data` and `/api/leaderboard`, and their `/api/nofx/*` counterparts, returned 200 with the invited session and 401 without a session. Nginx configuration validation passed. All 17 scoped API regression tests passed. Both local and deployed frontend production builds passed. Chromium reported no uncaught page errors. Temporary QA users were disabled and their sessions revoked after verification.

## Execution boundary

Saving or activating a Studio draft persists configuration and selects the active draft. It does not reconfigure the running Nautilus paper worker or submit orders. The actual worker thresholds and risk caps are retained in the seeded configuration metadata; the running daily-loss envelope is unchanged. Compilation/deployment of edited drafts remains a separate engine integration boundary.

## Source and rollout

- Gateway + tests + nginx aliases: https://github.com/patbhakta/algobots/tree/fix/alg3352-walkthrough (`af5555f`).
- Frontend, preserving deployed evidence/marimo links: https://github.com/patbhakta/algobots-nofx/tree/fix/alg3352-walkthrough-live (`69bb240c4`).
- Frontend image: `algobots/nofx-frontend:alg3352-walkthrough`.
- Rollback copies of the stack compose and nginx configurations are on the deployment host with `.bak-alg3352-walkthrough` suffixes.

## Runtime recovery

The API restart left leases owned by its removed predecessor container. Normal supervisor recovery requires ten minutes of heartbeat silence. Automatic approval review rejected early force-release because of potential duplicate-worker risk; no override was performed. At 11:14 UTC the normal supervisor recovered all three workers: `ready=true`, each account `state=ready` and `reconciled=true`, with no denied leases. Laya restored 22 fills, Coin restored 54, and Jev restored zero. These are restored historical receipts, not new fills. `workers-after-recovery.json` preserves the final runtime result.

The PNGs capture Dashboard, Data, Strategy, Leaderboard, and Config. `verification.json` contains redacted machine-readable API/UI results; it contains no credentials or session tokens.

## Durable issue artifacts

- [Five-screen walkthrough and verification JSON](/api/attachments/ba015507-f59b-47cd-b6ab-f4c54dc169be/content).
- [Strategy controls screenshot](/api/attachments/2632dda8-aac3-44f3-802e-4c79d51281b7/content).
