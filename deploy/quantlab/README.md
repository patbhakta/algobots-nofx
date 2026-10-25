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

## Approved mount

The ops-managed `funnytree-quantlab.service` mounts the bounded alias at
`/mnt/funnytree-quantlab/algobots` with
`allow_other,default_permissions,reconnect`. The compose overlay uses this alias;
existing exporter and stock-vault mounts remain unchanged.

Files created through SSHFS appear as root:1000. The container entrypoint and
acceptance publisher set umask 0002 to preserve group write. Acceptance uses
ordinary open/write/read-back and append as UID/GID 1000, rather than `touch`,
whose utimes operation fails for non-owners on this mount. The bounded mount
script also requests SFTP server umask 0002: the server default 0022 otherwise
removes group-write even when the container requests it. Recreate quantlab after
restarting its alias so Docker binds the current mount. Private staging paths
use random UUID names with mode 0770 (subject to umask), since tempfile's 0700
would exclude UID 1000 from root:1000 directories on this SSHFS alias.

## Acceptance

    docker exec --user 1000:1000 marimo-quantlab python /home/quantlab/notebooks/quantlab_openbb.py --acceptance

The notebook retrieves a bounded SPY history range, constructs SPY.NYSE bars,
publishes a unique catalog snapshot, queries actual Bar objects, runs the engine,
and requires one processed iteration per bar before publishing a shared external
manifest. The manifest records provider/version/query, UTC daily availability
policy, precision, catalog path and engine event count. Weekends are explicit
irregular-event gaps. A failed catalog/engine check publishes no manifest.
Catalog directories orphaned before manifest publication remain undiscoverable.

Deploy only this service (the base compose supplies the gitignored token):

    QUANTLAB_BUILD_CONTEXT=/opt/algobots-alg3424 docker compose --project-directory /opt/algobots-stack -f /opt/algobots-stack/docker-compose.yml -f deploy/compose.quantlab.yaml up -d --no-deps --build marimo-quantlab

Acceptance rejects a root-context run and verifies write/read-back and group-write
before fetching data. After publication it reads the manifest and parquet back
through Warehouse.load as the same UID.
