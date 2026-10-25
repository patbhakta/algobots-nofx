# OpenBB snapshot Studio backtest acceptance — 2026-10-25

[ALG-3421](/ALG/issues/ALG-3421), on main base `60a2617`.

Before: the [CEO walkthrough](/ALG/issues/ALG-3421#comment-64099ce3-43ac-401d-af7e-182c84ee6bab)
found that Studio listed the snapshot but rejected the compiled OHLC DSL with HTTP 422.

After: `scripts/verify_studio_openbb_http.py` provisions an operator-created
single-use invite and registers/logs in a fresh tenant over HTTP. Authentication
uses the API container's loopback port; Studio requests use the deployed :8201
frontend proxy. No credentials are included in the recorded evidence.

- Selected published snapshot: `openbb-spy-60430be3251945a6`, `SPY.NYSE`, 10 bars.
- Snapshot Parquet sha256: `acaceda6c930b2ecdafdfaee4c9a2ccd6972364e0c204113e2fb82ae76d3bf81`.
- Backtest HTTP 201; repeat HTTP 200, same result `032785c0-7b57-5452-b6a3-1c32b0bef949`.
- Draft: `3ebda6a4-c422-4b1f-9f09-7c4dba3af29d`. Exactly one stored result.
- Executor: NautilusTrader BacktestEngine **2.0.0rc6**, 10 iterations, one real BUY fill.
- Fill: one share at USD 773.17; signal at 2026-09-03T00:00Z, execution at 2026-09-04T00:00Z.
- Ending marked equity USD 99,984.22 from USD 100,000; PnL -15.78; zero assumed fees.
- [Immutable notebook](http://100.82.57.72:8205/?file=evidence%2F032785c0-7b57-5452-b6a3-1c32b0bef949.py)
  is token gated and carries artifact/snapshot/result hashes.
- UID-1000 marimo cache creation and notebook visibility verified.
- Image tests: **33 passed** (Studio, recorder backtest, OHLC dispatch, evidence). Ruff passes.
- Real-engine acceptance: prior-bar signals, future-data mutation invariance,
  false-entry/no-fill behavior and order caps all pass (`engine-acceptance.json`).

The original OpenBB publication, host permissions and rc6 catalog readback are
owned and recorded by [ALG-3424](/ALG/issues/ALG-3424#comment-b7e239e0-8d2f-4ecf-8fe3-b97fa5b9e636),
merged in PR #20. This integration consumes that existing snapshot; it makes no
provider query and publishes no replacement dataset.

## Execution and operational limits

The OHLC executor explicitly supports the published OpenBB SPY daily cash-equity
snapshot format, `condition_dsl.v1`, daily cadence, long-only, at most one share.
Signals see only previous completed bars. Engine fills use the current bar close;
buys are limit orders capped by order value, cash and optional gross-exposure cap.
The daily loss guard compares marked equity with the prior day's mark. Open
positions remain marked at the last close; there is no invented terminal exit.
This is paper backtesting; zero fees are an explicit assumption.

The API and supervised quantlab worker exchange data-only requests through the
existing private shared notebook volume under `.backtests`; no new listener or
Docker socket is exposed. The worker reloads/hash-checks the selected Parquet;
API verifies the reply identity. Each job runs in a child process with a 75-second
limit; API waits at most 90 seconds. Existing tenant-scoped immutable DB identity
and notebook publication are reused. SSHFS maps UID-1000 files to root:1000, so
worker output uses the approved `umask 0002`, without forbidden non-owner chmod.

## Deployment / rollback

Images: `algobots/evidence:alg3421`, `algobots/quantlab:alg3421`.
Apply `deploy/compose.openbb-backtest.yaml` after existing warehouse/evidence and
quantlab overlays, with the updated quantlab entrypoint. Recreate only `api` and
`marimo-quantlab`. Gateway, paper node, exporter and frontend are unchanged.
Rollback: omit the OpenBB overlay and use the previous quantlab compose overlay;
restore `algobots/evidence:alg3422` and `algobots/quantlab:alg3424`. Snapshot/result
files remain immutable and require no rollback.

Files `http-acceptance.json`, `engine-acceptance.json`, and `image-tests.log` record
the concrete outputs. These checks exercise HTTP and the real engine; no browser
screenshot is claimed.
