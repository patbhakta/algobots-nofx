# ALG-3414 — NoFX Studio funder demo: deployment + walkthrough evidence

Credential-safe: no password, session token or invite code appears in this
directory. Minted codes are redacted in the DOM before each screenshot; the
walkthrough reads the owner password from a run-scratch file and writes only
`summary.json` and screenshots here. Leak-scanned against every live secret
before commit.

## What is deployed (.243, 100.82.57.72)

| Piece | Source | Deployed |
|---|---|---|
| API `/api/nofx/*` (A03 gate, Studio CRUD, `/studio/live`) | `algobots` `53cc87e` (branch `alg-3414-nofx-funder-demo`) | `/opt/algobots/repo` @ `53cc87e`, `algobots-api-1` |
| Worker heartbeat fills (`client_order_id`/`trade_id`) | same commit, `engine/workers/paper.py` | live in `workers/{account}.json` |
| NoFX frontend | `algobots-nofx` `1ed27581` (branch `feat/alg-3414-funder-demo`, on v15 lane tip `71ca5133`) | `algobots/nofx-frontend:algobots-v19` on `:8201` |
| nginx routing | `algobots-nofx` `deploy/algobots/nofx-frontend-nginx.conf` | `/opt/algobots-stack/nofx-frontend-nginx.conf` (previous: `.bak-alg3414`) |

nginx on `:8201` rewrites NoFX's `/api/login|register|logout|config|strategies`
onto the AlgoBots `/api/nofx` surface, answers 410 for every other `/api` path
(the retired NoFX Go execution loop, Vergex boards, wallets), and never
proxies the synthetic-principal `/demo` routes.

## Walkthrough (`funder-walkthrough.mjs`, results in `walkthrough/summary.json`)

1. Owner logs in through the NoFX form → Strategy Studio with the live paper loop (`01`).
2. Owner mints a single-use, 7-day funder invite in the UI (`02`, code redacted).
3. Funder redeems it on `/register`, lands in the Studio with no second login (`03`).
4. A coin decision is shown with its actual Nautilus receipt
   (`O-20261023-100017-COIN-COIN-51 · T-616401dfdf6d61e4-001 · 22 @ 0.45`, `04`);
   the same interval's Laya decision shows the real risk block
   (`daily-loss envelope (−40 USD) exhausted`, `05`). Limits untouched.
5. Studio config: create → Save configuration (PUT 200, activate 200) → persists after reload (`04b`).
6. Owner revokes the funder: their session gets 401 and re-login returns `Access revoked` (`06`, `07`).
7. An invite revoked before use (expired) is refused at registration (`08`).

Also verified over HTTP: wrong password 401; missing / unknown / reused invite
refused; funder cannot mint invites (403); anonymous and forged-token
`/studio/live` 401.

## Honest-data notes

- Worker cards show `STALE` whenever a heartbeat is > 90 s old (seen during the
  10:01–10:11 UTC lease reclaim after the API redeploy); the Kalshi feed shows
  `STALE` after 20 min without an observer row (e.g. Thursday Kalshi maintenance).
- The client-side Shift+D showcase engine on the trader dashboard was removed (`6bbddbb3`).
- Older fills that rolled out of a worker's in-heartbeat history are correlated to
  the open Nautilus position for that instrument instead (labelled "Nautilus position").
