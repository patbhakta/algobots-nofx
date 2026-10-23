# ALG-3403 — full-loop demo verification on .243

Verifier: `python tests/demo/full_loop.py` (read-only; exits 0 only when all
five hops are wired). Judgement rules are pinned by `tests/demo/test_full_loop.py`.

## Run 1 — 2026-10-22 06:3x UTC, `.243` (`100.82.57.72`)

Output: [`full-loop-run-1.md`](full-loop-run-1.md). Result: **0/5 wired, exit 1**.

| # | Hop | Exists today | Missing for the demo |
| --- | --- | --- | --- |
| 1 | Studio config saved | `/demo/studio` (demo-only studio on the API, 6 built-in template versions, frozen-hash deploys). Design contract `docs/design/strategy-studio-nautilus-bridge.md` (ALG-3352, in review) | `/api/studio/strategies` draft + compile routes; NoFX Studio saving through them |
| 2 | Gateway accepts + dispatches | `src/algobots/gateway` (P1.1–P1.3, G1 test green in CI) | Not deployed: `GET /health` 404 on :8000, no gateway service in either compose file, Redis has 0 keys (no `algobots:cmd:*`) |
| 3 | Nautilus paper fills | 3 paper workers (laya/jev/coin) ready, 2 fills on laya — but on **nautilus_trader 1.231.0** (API image, `pyproject` pins `>=1.231`) as `BacktestEngine` kernels fed from inbox files | A 2.0.0rc6 node (only `nautilus-marimo` has rc6) running `CommandActor` against `algobots:cmd:<node>` |
| 4 | Market data reaches node | Datafeed notebooks in marimo (Binance public, Massive, IBKR draft) | Worker feed `/feeds/kalshi/observations.jsonl` does not exist on the host (`/opt/laya/kalshi/` empty); workers processed 0 intervals. No replay feed into a node; IBKR paper blocked on login (ALG-3357) |
| 5 | marimo evidence | marimo 0.25.1 up on :8202 with rc6 | No notebook reads a paper run's fills/PnL/data timestamps; marimo cannot see the API's `algobots_demostate` volume (only `bridge/` is shared) |

Deployed API is `/opt/algobots/repo` @ `a68604f`, built 2026-10-13 — behind
`origin/main` (`3599abc`).
