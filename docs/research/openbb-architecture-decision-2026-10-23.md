# OpenBB architecture decision brief — 2026-10-23

Assignment: [ALG-3416](/ALG/issues/ALG-3416). Standing constraints also recorded on [ALG-3352](/ALG/issues/ALG-3352). Findings only; Pat owns adopt/reject. No build or deployment authorized.

## Standing architecture

Historical/backtest warehouse and data analysis: OpenBB → marimo → NoFX surfaces. Real-time market data and execution/fill truth: Nautilus, including Kalshi/Polymarket. All adopted services run in Docker on .243. Zero Jupyter anywhere. Prefer upstream releases and an official REST image; do not maintain Pat's fork. This supersedes older wording that limited OpenBB to an optional adapter or preferred embedding it.

The warehouse role requires durable snapshots as well as retrieval. OpenBB supplies provider access and analysis interfaces; the proposed warehouse includes persisted Parquet datasets, a manifest/catalog and retention/backup ownership. An HTTP response alone is not an archived backtest dataset. Execution must remain independent of this research service.

## Candidate comparison

| Candidate | Benefits | Cost and evidence gap | Recommendation |
| --- | --- | --- | --- |
| (a) Selected OpenBB Python packages inside algobots-api-1 | Direct results and fewer services | Shares dependency resolver, process resources and release cycle with the API. Repository Dockerfile uses Python 3.12; compatibility is unproven until exact dependency resolution. | Fallback only if Pat explicitly selects it. |
| (b) Upstream REST service in Compose on .243 | Isolates research dependencies and failures; marimo uses HTTP; upstream upgrades need no fork | Official docs describe a Dockerfile build, not a verified published registry image. No official image name/digest or clean final-image package inventory established. | Preferred architecture, conditional on provenance, required datasets and zero-Jupyter proof. |

[REST documentation](https://docs.openbb.co/odp/python/quickstart/rest_api) confirms an ordinary FastAPI/ASGI app. The [Docker instructions](https://docs.openbb.co/odp/v4/python/installation) document building an image locally. They do not establish an official published image. If no suitable official image exists, Pat must separately choose whether a minimal container assembled from pinned upstream packages is acceptable; that is packaging, not an OpenBB source fork.

## Market coverage: version choice changes the answer

The [V4 crypto reference](https://docs.openbb.co/odp/v4/python/reference/crypto/price/historical) documents BTC historical prices via FMP, Tiingo and Yahoo Finance. The [V4 equity reference](https://docs.openbb.co/odp/v4/python/reference/equity/price/historical) documents OHLCV via Cboe and other providers. These establish historical interfaces, not subscription entitlements, complete history, point-in-time correctness or successful live retrieval.

Crucially, [V5 migration documentation](https://docs.openbb.co/odp/python/migration-from-v4) removes fifteen providers, including all three listed V4 crypto sources, and changes command namespaces. V4 BTC examples cannot establish current V5 BTC spot coverage. V5 retains Deribit, but derivatives data is not evidence of an equivalent spot history dataset. V5 retains Cboe equity history under its provider namespace; required symbols, adjustment policy and depth still need validation. Do not repeat the wake's “70+ providers” as a current verified coverage claim.

Pat's choice therefore needs a release/provider matrix: BTC spot versus perpetual/derivative, interval and required dates; equities, universe and corporate-action adjustment; provider access, rate limits, retention and permitted downstream use. Current upstream cannot yet be recommended as a proven replacement for existing BTC history retrieval. No provider requests or paid calls were made.

## Parquet and marimo

Proposed path: fetch selected dataset → normalize schema → persist immutable Parquet plus manifest → marimo reads the snapshot → NoFX exposes authorized research results. Python OBBject offers `to_df()` in inspected source; a DataFrame can write Parquet with an explicitly selected engine. REST returns JSON results which the ingestion consumer can normalize before writing. These are design paths, not tested exports. The Parquet engine and full dependency closure must be selected and inventoried.

Manifest requirements: dataset ID, provider and terms/version, query and symbols, interval, timezone, event and retrieval timestamps, adjustments, schema/version, row count, date range, checksum and source release. Validate missing/duplicate bars and numeric precision. Make notebook refresh explicit so reactive execution cannot silently change backtest inputs or repeatedly call providers. Keep credentials server-side and isolate research failure from order/fill processing.

## Zero Jupyter and license findings

Core can run without a notebook server, but that is weaker than zero Jupyter dependencies. At read-only cached upstream revision `cbf37e1f98a61d4e17ff1df43441fd4004774cac`, umbrella `openbb` 5.0.0 requires `openbb-devtools`; devtools 2.0.1 requires `ipykernel>=6.30.1`. Reject the default umbrella installation for this constraint. [V5 installation](https://docs.openbb.co/odp/python/installation) supports selected runtime/provider packages, but a complete resolved dependency graph and final image inspection are still required. Existing marimo image must also pass inventory. No installation, dependency resolution or image build was performed.

The wake's AGPL statement is release-specific: [official migration guidance](https://docs.openbb.co/odp/python/migration-from-v4) says V4 was AGPL-3.0-only and V5 packages are Apache-2.0; the [current upstream license](https://raw.githubusercontent.com/OpenBB-finance/OpenBB/develop/LICENSE) and umbrella manifest agree. For V5, preserve applicable license/NOTICE materials and modification notices and audit exact dependencies. For V4, review the actual pinned license, corresponding-source duties for distribution and any modified network-served version; an existing NoFX source link is not evidence that all OpenBB obligations are satisfied. Provider data rights and commercial Workspace terms are separate from software licensing. This is engineering screening; exact-artifact legal clearance remains open.

## Decision requested and verification boundary

Recommendation: retain Pat's preferred separate REST service architecture, but do not approve implementation on the present evidence. Pat can accept conditional adoption pending proof of official image provenance, exact release/provider coverage, zero-Jupyter closure and artifact-specific licensing, or reject OpenBB. A custom package-built REST image and a V4 coverage fallback require explicit selection rather than an automatic substitution.

After Pat's yes, the bounded implementation gate is: pin release/image digest and required providers; resolve/inventory packages; prove BTC/equity coverage with authorized bounded fixtures/requests; round-trip a snapshot into marimo; validate internal-only Compose configuration, authentication, persistence, resources and research-service outage isolation. Create implementation work only after the decision. No services, Compose files, packages or .243 state changed in this research.

Verification: inspected repository deployment/dependency declarations, prior research and cached upstream manifests/OBBject; checked official live REST, installation, V4 market reference, V5 migration and license pages on 2026-10-23. No runtime integration success is claimed.

## Handoff availability

Paperclip GET heartbeat-context failed with connection refused during this run. Board document publication, decision interaction and final status require API availability. Platform/control-plane owner must restore the injected Paperclip API endpoint; R&D can then publish this brief, create a human decision interaction for Pat and set in_review. Until that interaction exists, the appropriate fallback disposition is blocked, not a claimed review path. The runtime is the sanctioned recovery channel if the status write also fails.
