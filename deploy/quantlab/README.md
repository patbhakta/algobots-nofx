# Quantlab

This service owns OpenBB historical snapshot publication and lifecycle evidence.
The existing :8202 nautilus-marimo retains its 298 general research notebooks;
quantlab :8205 owns the lifecycle notebooks used by ALG-3422. ALG-3421 should
consume these shared manifests rather than deploy another OpenBB fetch owner.
Only the free yfinance provider is queried by the acceptance notebook.

Python 3.12 is required: PyPI metadata for nautilus_trader 2.0.0rc6 declares
`>=3.12,<3.15` and publishes zero cp311 wheels. The rc6 pin is unchanged.
`uv.lock` pins all 117 resolved packages. Build from the repository root:

    docker build -f deploy/quantlab/Dockerfile -t algobots/quantlab:alg3424 .

The compose overlay uses UID/GID 1000, authenticated marimo and tailnet :8205.
All notebook and data writes use FunnyTree. Before starting it, copy notebooks
from /opt/quantlab/notebooks into /mnt/funnytree/algobots/quantlab/notebooks,
including notebooks/quantlab_openbb.py. Preserve the existing notebooks.
Publication directories need group 1000 write/search permissions; existing
warehouse data files are never rewritten. Snapshot catalog writes use the
ParquetDataCatalog API and the same immutable adapter as the warehouse exporter.
The adapter supports both its existing Cython runtime and the rc6 Rust API.

## Deployment hold: FUSE access

The existing SSHFS mount is root-only (no allow_other). UID 1000 cannot even
stat its mounted home, despite correct 1000:1000 directory ownership. Do not
deploy the overlay until non-root FunnyTree access is approved and verified.
Automatic approval review rejected adding an allow_other mount because it
changes the local-user security boundary. No mount changes were applied.

Proposed bounded resolution for approval: a separate SSHFS mount of
root@100.79.207.5:/mnt/vault-data/algobots at
/mnt/funnytree-quantlab/algobots with allow_other,default_permissions,reconnect.
Only quantlab would use this alias; the exporter mount stays untouched.
Unix ownership/modes still apply, but other local users gain traversal/read
access wherever the underlying modes permit it. A persistent mount unit and
compose source-path update would follow approval. Alternatively the operator
can provide an approved non-root-capable mount of the same directory.

## Acceptance

    docker exec --user 1000:1000 marimo-quantlab python /home/quantlab/notebooks/quantlab_openbb.py --acceptance

The notebook retrieves a bounded SPY history range, constructs SPY.NYSE bars,
publishes a unique catalog snapshot, queries actual Bar objects, runs the engine,
and requires one processed iteration per bar before publishing a shared external
manifest. The manifest records provider/version/query, UTC daily availability
policy, precision, catalog path and engine event count. Weekends are explicit
irregular-event gaps. A failed catalog/engine check publishes no manifest.
Catalog directories orphaned before manifest publication remain undiscoverable.

Do not claim the non-root deployment acceptance from a root smoke run. The new
image has not replaced the existing running service while mount access is held.
