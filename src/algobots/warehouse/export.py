"""One bounded recorder export cycle; suitable for a scheduled container job.

python -m algobots.warehouse.export --feed kalshi --source observations.jsonl
Uses immutable content-derived snapshot IDs, so unchanged cycles are idempotent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from algobots.warehouse import Warehouse, WarehouseError
from algobots.warehouse.recorders import (
    export_observer,
    export_observer_quotes,
    export_paper_stream,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", choices=["kalshi", "pmus", "nautilus-paper"], required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--instrument-id", required=True)
    parser.add_argument("--provider-release", required=True)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(
            os.environ.get("ALGOBOTS_WAREHOUSE_ROOT", "/mnt/funnytree/algobots/warehouse")
        ),
    )
    parser.add_argument("--catalog-root", type=Path)
    args = parser.parse_args()
    warehouse = Warehouse(args.root)
    if args.feed == "nautilus-paper":
        import redis

        client = redis.Redis.from_url(os.environ["REDIS_URL"])
        last = client.xrevrange("algobots:feed:nautilus-paper", count=1)
        if not last:
            raise WarehouseError("paper stream empty")
        end = last[0][0].decode()
        identity = end.replace("-", "_")
    else:
        if args.source is None:
            parser.error("--source required for observer export")
        identity = hashlib.sha256(args.source.read_bytes()).hexdigest()[:24]
    snapshot_id = f"{args.feed}-{identity}"
    try:
        manifest, _ = warehouse.load(snapshot_id)
    except WarehouseError:
        if args.feed == "nautilus-paper":
            manifest = export_paper_stream(
                warehouse,
                client,
                snapshot_id,
                instrument_id=args.instrument_id,
                provider_release=args.provider_release,
                retrieved_at=time.time(),
                end=end,
            )
        else:
            manifest = export_observer(
                warehouse,
                args.feed,
                args.source,
                snapshot_id,
                instrument_id=args.instrument_id,
                provider_release=args.provider_release,
                retrieved_at=time.time(),
            )
    if args.catalog_root and args.feed != "nautilus-paper":
        target = args.catalog_root / snapshot_id
        if not target.exists():
            export_observer_quotes(warehouse, snapshot_id, args.catalog_root)
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
