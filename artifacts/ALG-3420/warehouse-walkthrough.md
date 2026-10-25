# Warehouse Studio before/after evidence — 2026-10-25

Issue: [ALG-3420](/ALG/issues/ALG-3420).

## Before

- Studio froze the live Kalshi JSONL feed on each Backtest click.
- Snapshot discovery through :8201 returned HTTP 404 before deployment.
- Backtest deduplication only searched the current draft's references.

## After

- Deployed at http://100.82.57.72:8201 with the warehouse snapshot selector.
- Discovery through :8201 returns HTTP 401 without a session: the route exists
  and retains authentication. Authenticated discovery, selection, result reuse,
  and mutation refusal are exercised by the API regression tests.
- API and frontend containers are healthy. The exporter runs every 900 seconds;
  its first cycles logged exit 0 for Kalshi, pmus, and nautilus-paper.
- Published manifests and ledgers live in
  `/mnt/funnytree/algobots/openbb_store`, shared with marimo-quantlab. Catalogs
  live in `/mnt/funnytree/algobots/ntl_catalog`, also shared with quantlab. The API
  mounts both read-only; the recorder export service writes them.
- Kalshi: 276 source/ledger rows, 272 real recorded quotes queried from Nautilus.
  Four rows without recorded books remain in the ledger and do not invent quotes.
- pmus: 180 source/ledger rows and 180 Nautilus quotes.
- Paper stream: a bounded export with 3,610 ledger rows and 3,610 Nautilus quotes.
  The stream continues growing; each cycle publishes a new immutable cursor ID.

## Real replay

The operator replay ran the deployed image against the shared read-only mounts:

- Snapshot: `kalshi-4de59a237db7a511ab406e29`.
- Parquet SHA-256:
  `ee3ca71b5fa414cb309a2852113dc08f665a4c59ae1f686a53e9f04eff26071d`.
- Artifact hash:
  `a150faa7ac16bfae16a34fdaa0123f43a59a0fa4b8ede03d5c0d6012dcb00a86`.
- Executor: NautilusTrader 1.231.0 BacktestEngine.
- 275 settled intervals; 47 paper fills; P&L -$78.62 including $8.28 fees.
- Pending interval excluded. Signals use prior settled closes; overlapping or
  unordered warehouse intervals are refused.

Machine-readable results: [warehouse-walkthrough.json](warehouse-walkthrough.json).
This is an operator engine invocation, not an invited-session browser recording.
It does not create a result row in a funder's tenant or place live orders.

## Verification and review

- Required warehouse/NoFX Studio/backtest suites: 42 tests pass on the final code.
- Broader local suite: 1,403 pass, 31 skip; exit 0. The final required suites were
  rerun after the last event-order validation change.
- Repository-wide Ruff: pass. Dependency lock refreshed with existing versions.
- Deployed runtime image: 14 warehouse/catalog tests pass.
- Frontend: three Backtest panel tests pass; TypeScript/Vite build passes.
- Concurrency test: two requests from separate drafts return one immutable row,
  with HTTP 201 and 200. Generic PATCH/DELETE of evidence returns HTTP 409.
- Backend source: `1c512e9`; frontend: `4153e92`.
- Backend PR: https://github.com/patbhakta/algobots/pull/19.
- Frontend PR: https://github.com/patbhakta/algobots-nofx/pull/4, based on the
  shipped L0 branch to preserve its live-view changes.

GitHub reports backend PR #19 as UNSTABLE. The available deployment identity is
forbidden (HTTP 403) from reading Actions/check-run details, so no merge was
attempted. [ALG-3425](/ALG/issues/ALG-3425) is assigned to Product Manager to
restore narrow CI read access or provide the actual failed-check logs. R&D then
resolves that failure and completes merge/closure verification. Frontend PR #4
reports CLEAN. The delivery is deployed; issue closure remains blocked on this
explicit verification path.

## Deployment and rollback

The API/exporter use the existing `algobots` Compose project plus
`/opt/algobots-stack/compose.warehouse.yaml`. The frontend uses the existing
`algobots-stack` project plus `compose.warehouse-frontend.yaml`. Existing gateway,
node, and quantlab services were left running. Prior API image `algobots-api` and
frontend `algobots/nofx-frontend:alg3419-paper-loop` remain available for rollback.
Reapply the original Compose files to revert the respective services, and stop
`warehouse-exporter` using the warehouse overlay. Published snapshots remain.
