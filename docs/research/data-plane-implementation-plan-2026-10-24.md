# Data plane implementation plan — 2026-10-24

Assignment: [ALG-3417](/ALG/issues/ALG-3417). Supersedes the adopt/reject gate in
[the evaluation](data-plane-law-2026-10-23.md).

## Pat's rulings this plan follows (2026-10-24)

1. **OpenBB is adopted.** "Once we get the data and feeds we need to be able to use
   it for different strategies." This replaces the bounded feasibility proof (the
   expired confirmation `fd50e46b`) with an implementation plan.
2. **Demo first.** Building starts only after the NoFX demo is green: hop 1 plus the
   verifier. The verifier is already green (`tests/demo/full_loop.py`, PASS 5/5 on
   .243 at `667bd85`, 2026-10-24 17:26Z). The one remaining gate is
   [ALG-3352](/ALG/issues/ALG-3352): Pat's invited-login Studio walkthrough on
   :8201, then acceptance. Until ALG-3352 is `done`, nothing is built or deployed.
3. **No spend is authorized.** The plan uses only free or keyless providers. Each
   paid provider key, or any paid inference, needs its own ruling from Pat.

## Roles (unchanged law)

| Role | Owner | Writes to the warehouse |
| --- | --- | --- |
| Recorder | Nautilus `ParquetDataCatalog`, plus the feed ledger exported to Parquet | `nautilus/`, `ledger/` |
| Feeder | OpenBB, official upstream image, a separate REST service on .243 | `external/` (through the warehouse writer only) |
| Visibility | marimo (:8202), read-only against published snapshots | nothing |
| Seam | One Parquet warehouse, the single source of truth | — |

## Warehouse layout

The root is `${WAREHOUSE_ROOT:-/mnt/funnytree/algobots/warehouse}`. It sits on
FunnyTree per the STORAGE law and is mounted into the existing `nautilus` (marimo)
container next to the `nautilus_catalog` volume.

```
warehouse/
  nautilus/                    # ParquetDataCatalog root; written only by the recorder
  ledger/<feed>/v<schema>/date=YYYY-MM-DD/part-*.parquet   # kalshi, pmus, nautilus-paper
  external/<provider>/<dataset>/v<schema>/snapshot=<id>/part-*.parquet
  manifests/<namespace>/<dataset>/<snapshot_id>.json        # immutable once published
  _staging/                    # writers stage here; publish = atomic rename + manifest
```

Each manifest records: dataset, provider, provider release or image digest, query,
instrument mapping, event-time and retrieval-time ranges, timezone, units and
precision, adjustment policy, schema version, row count and content hash. A
snapshot is published only after it passes gap, duplicate and ordering checks.
Nothing overwrites a published snapshot. A correction is a new snapshot id.

## Phases (each becomes one child card once the build gate opens)

**P0 — Artifact gate (read-only, about 1 heartbeat).** Identify the official
upstream OpenBB V5 REST image and pin its digest. Record its license (V5 is
Apache-2.0, per the migration guide) and a resolved package inventory that proves
it ships no jupyter or ipykernel. Build a coverage matrix for the first datasets
below, using only providers that are free or keyless.
*Exit:* a pinned digest plus the inventory, committed. If upstream publishes no
image, stop and take it back to Pat. No custom build and no fork.

**P1 — Warehouse writer.** Add `src/algobots/warehouse/` with the following:
manifest schema, staging, validate (gaps, duplicates, ordering), atomic publish,
and a read API (`list_snapshots`, `load(snapshot_id)`). It has unit tests and a
repository-map owner.
*Exit:* `pytest tests/warehouse` passes, and a fixture snapshot completes the round
trip.

**P2 — Recorder into the seam.** Export the feed ledgers to `ledger/` on a
schedule: Kalshi `observations.jsonl`, the pmus observer, and the
`algobots:feed:nautilus-paper` stream. Write replayable quote and bar data into
`nautilus/` through `ParquetDataCatalog` using Nautilus schemas. The live
observers stay unchanged, and the export only reads their output.
*Exit:* a manifest exists for each feed and matches its source row counts. A
Nautilus catalog query returns the recorded quotes.

**P3 — Feeder.** Run the OpenBB REST service in `deploy/compose.openbb.yaml` at the
pinned digest. It binds to the tailnet only, with provider keys in `.env` and never
in git. Add a feeder job, `algobots.warehouse.feed_openbb`, that reads a committed
dataset spec, calls REST, and publishes through the P1 writer. The first datasets
come from the P0 matrix and are free providers only: FRED macro series (rates, CPI,
unemployment), plus daily index and equity history from whichever free V5
provider P0 verifies.
*Exit:* two external datasets are published with manifests, and a re-run produces
an identical content hash or a new snapshot id. Nothing is ever mutated in place.

**P4 — Visibility.** Add marimo notebooks under `notebooks/`:
`warehouse_catalog.py`, which browses manifests, coverage, gaps and freshness, and
`dataset_inspect.py`, which charts any snapshot by id. They read published
snapshots only and never call providers on reactive execution.
*Exit:* both notebooks render on :8202 with data from P2 and P3, and a screenshot
is attached as evidence.

**P5 — Strategy-testing workflow.** Run backtests from warehouse snapshot ids. Use
a Nautilus `BacktestNode` over the `nautilus/` catalog for recorded feeds, with the
`external/` datasets joined as features (for example, a macro-regime filter). Each
run's evidence records the strategy config id and every input snapshot id. NoFX
Studio's Backtest tab and the marimo evidence notebook show those ids.
*Exit:* one existing strategy is backtested on recorded and external data, and the
evidence links back to the snapshot manifests.

The phases run in order: P0 and P1 can run in parallel, then P2, P3, P4 and P5. P2
and P3 depend on P1, and P4 and P5 need data from both.

## Out of scope

OpenBB as a live logger, an OpenBB fork, a custom OpenBB image, Jupyter, paid
providers, and any change to the live observers or the paper node.

## Next step

Pat confirms this plan. When ALG-3352 is `done`, the Tech Lead opens the P0–P5
child cards under ALG-3417 and starts with P0 and P1.
