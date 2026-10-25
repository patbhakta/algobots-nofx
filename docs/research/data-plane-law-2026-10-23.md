# Data plane law and OpenBB evaluation — 2026-10-23

Assignment: [ALG-3417](/ALG/issues/ALG-3417), supporting [ALG-3403](/ALG/issues/ALG-3403). Findings only; Pat decides before any build. This role definition supersedes the older OpenBB-as-warehouse wording in the prior research and handoff.

## Authoritative roles

- Recorder: Nautilus ParquetDataCatalog plus feed ledger persisted to Parquet. The supplied assignment reports Nautilus 1.231.0 and catalog availability verified on .243; this heartbeat did not inspect that host.
- Feeder: OpenBB pulls external historical breadth into the same warehouse. It does not replace live push ingestion or the feed ledger.
- Visibility: marimo is the data inspection and charting surface, reported running at :8202. No Jupyter.
- Seam: one Parquet warehouse is the source of truth. Backtests replay frozen datasets from it; NoFX surfaces evidence tied to those datasets.

Why OpenBB is not the logger: its documented command/REST interface retrieves provider results on request. Routing an existing live observer through it would require an additional custom ingestion adapter without supplying the recorder's durability and replay semantics. This is an architecture assessment, not proof that upstream has no streaming-related code anywhere.

## Scoped evaluation

| Question | Finding | Decision implication |
| --- | --- | --- |
| Official REST image | Upstream documents an ASGI REST service and a Docker build recipe. A published official registry artifact and immutable digest remain unverified. | Prefer Pat's official-image option, but do not invent an image or substitute a custom build. |
| Library in a container | Selected runtime/provider packages are supported. Embedding in the existing API couples dependency resolution and failures; an isolated package-built REST container avoids that coupling but is a separate packaging choice. | Fallback requires Pat's explicit selection; no fork maintenance. |
| Market coverage | V5 lists Cboe and Nasdaq, and macro sources such as FRED, BLS and IMF. Fifteen V4 providers were removed, including Yahoo Finance, FMP and Tiingo. Provider presence does not prove required symbols, dates, intervals, access or data rights. | Do not use “70+ providers” or V4 BTC examples as current V5 coverage evidence. Require an exact release/provider/dataset matrix. Kalshi/Polymarket history is not established. |
| Parquet export | REST returns result rows; Python offers DataFrame conversion. A consumer can normalize and write Parquet, but no warehouse round trip was executed. | OpenBB supplies retrieval; the warehouse writer must own schema, atomic publication and provenance. |
| AGPL | Official migration guidance identifies V4 as AGPL-3.0-only and V5 as Apache-2.0. | Audit the selected artifact and dependencies; preserve applicable notices. Provider data rights remain separate. This is engineering screening, not legal clearance. |
| Zero Jupyter | Selected packages are supported; prior cached-source inspection found umbrella → devtools → ipykernel. Full resolved inventory is absent. | Reject the default bundle for the stated constraint; require final-image inventory for any selected candidate and existing marimo image. |

## Warehouse contract for a later approved implementation

Use one warehouse root with schema-owned namespaces; shared storage does not mean arbitrary provider tables can be written directly into Nautilus catalog internals. Convert replayable records to supported Nautilus schemas and publish other datasets under explicit versioned schemas. Marimo reads published snapshots, rather than silently refreshing provider queries on reactive execution.

Each snapshot needs dataset/provider/release identity, query, instrument mapping, event and retrieval times, timezone, units and precision, adjustment policy, schema version, row count, range and content hash. Validate gaps, duplicates and ordering. Stage writes and publish only validated immutable snapshots; preserve the feed ledger and recorder ownership. Backtest evidence must retain dataset and strategy identities. These are proposed acceptance requirements, not implemented guarantees.

## Recommendation and gate

Keep the role law. Prefer the separate upstream REST service only after official artifact provenance, necessary historical coverage, clean dependency inventory and exact licensing are established. If no qualifying official image exists, return the packaging choice to Pat; do not silently build one. No services, packages, Compose configuration, provider calls or .243 state changed.

Pat's pending decision: authorize a bounded feasibility proof for that preferred candidate, or revise/reject it. Acceptance would authorize only the stated proof, not deployment. A custom package-built image or V4 fallback needs its own explicit choice. No implementation subtasks were created.

Verification: reviewed existing local research and rechecked official REST, installation and migration pages on 2026-10-23. No integration test, dependency resolution, export or runtime inventory is claimed.

Sources: [REST](https://docs.openbb.co/odp/python/quickstart/rest_api), [V5 installation and package list](https://docs.openbb.co/odp/python/installation), [V4 Docker instructions](https://docs.openbb.co/odp/v4/python/installation), [V5 migration and license changes](https://docs.openbb.co/odp/python/migration-from-v4). Earlier cached-source details are in [the architecture brief](openbb-architecture-decision-2026-10-23.md).

## Publication

Paperclip API outage (13:45–14:13Z) prevented publication in the authoring runs. Republished 2026-10-23 by the AlgoBots Tech Lead: committed to git, posted as the ALG-3417 issue document, and put to Pat as a request_confirmation decision. No build is authorized until Pat accepts.
