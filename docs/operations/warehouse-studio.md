# Studio warehouse snapshots

Studio reads published Parquet snapshots from
`ALGOBOTS_WAREHOUSE_ROOT` (default `/mnt/funnytree/algobots/warehouse`).
Catalog writers use `/mnt/funnytree/algobots/ntl_catalog`, the quantlab seam.
The API needs read access; recorder export jobs need write access.

Before this change, Backtest froze the growing Kalshi JSONL feed on each click.
Now `/api/studio/snapshots?instrument_id=KXBTC15M.KALSHI` and
`/api/studio/strategies/{draft_id}/snapshots` discover published snapshots.
POST the chosen `snapshot_id` to the draft's `/backtest` endpoint.
`dataset_id` remains an alias. Omitting both selects the snapshot with the latest
recorded event, never the live feed. The result records the snapshot ID and hash.

Publication validates ordering, duplicate keys, provenance and cadence. Recorder
ledgers explicitly declare irregular recorded events; gaps are preserved rather
than silently interpolated. Each immutable manifest lives under
`manifests/<namespace>/<dataset>/<snapshot_id>.json`; recorder Parquet files live
under `ledger/<feed>/v1/date=YYYY-MM-DD/part-<hash>.parquet`.
Snapshot IDs are unique across namespaces. Readers recheck hashes and row counts.

`warehouse.recorders.export_observer` exports Kalshi or pmus JSONL;
`export_paper_stream` reads a bounded Redis XRANGE and retains its stream cursor,
recorded timestamp and node timestamp. Exporters never update their sources.
Malformed input fails the export instead of silently dropping source rows.
`warehouse.catalog.publish_bars` writes supplied Nautilus instruments and Bar
objects through the catalog API, queries them back as Bar objects, and publishes
an isolated catalog directory. Reusing a catalog snapshot is refused. It never
invents OHLC from settlement outcomes. The five-bar regression test proves
Nautilus-side consumption, including nanosecond timestamps and the BarType.

The current strategy runner supports Kalshi momentum over settled recorder rows;
it recomputes each signal from rows strictly before the traded interval. Other
implementations still fail with an owning-field error. Catalog publication is a
separate recorder API; this change does not claim generic OHLC strategy replay.

One tenant-scoped database primary key is derived from artifact hash and snapshot
ID. Across drafts and concurrent requests, duplicate insertion returns the
existing result without updating it. The original draft attribution stays on the
result; additional drafts refer to it in their own backtest lists.

Verification: `pytest tests/warehouse tests/api/test_nofx_studio.py
 tests/strategies/test_backtest.py`; Ruff on changed Python files. Frontend lives
in the `algobots-nofx` repository on top of `feat/alg-3419-paper-loop`.
