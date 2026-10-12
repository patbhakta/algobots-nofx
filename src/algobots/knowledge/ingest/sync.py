"""Deterministic CLI stage for the algobots ingest flow (A14-2).

Usage (the pipeline stage calls exactly this)::

    python -m algobots.knowledge.ingest.sync \
        --root /path/to/vault --store var/knowledge-ingest \
        --tenant <uuid> --class authored_knowledge

Register (idempotent, content-addressed source id) -> ingest -> incremental
index -> print the sync status. Gate semantics: status ``failed`` or an
unhandled error exits nonzero — slop never advances down the flow. stdlib
only, zero external API spend.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

from algobots.knowledge.ingest.acl import PermissionClass, SourceAcl
from algobots.knowledge.ingest.ingest import Ingestor
from algobots.knowledge.ingest.search import SearchService
from algobots.knowledge.ingest.store import JsonIngestStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="algobots-knowledge-sync")
    parser.add_argument("--root", required=True, type=Path, help="vault root directory")
    parser.add_argument("--store", required=True, type=Path, help="ingest store directory")
    parser.add_argument("--tenant", required=True, type=UUID, help="owning tenant id")
    parser.add_argument(
        "--class",
        dest="permission_class",
        default=PermissionClass.AUTHORED_KNOWLEDGE.value,
        choices=[c.value for c in PermissionClass],
        help="permission class for the source ACL",
    )
    parser.add_argument("--acl-ref", default="cli", help="opaque ACL/grant reference")
    args = parser.parse_args(argv)

    store = JsonIngestStore(args.store)
    service = SearchService(store)
    source = Ingestor.register_source(
        store, tenant_id=args.tenant, root=args.root, acl_ref=args.acl_ref
    )
    acl = service.get_acl(source.source_id)
    if acl.permission_class != args.permission_class or not acl.live:
        service.set_acl(
            SourceAcl(
                source_id=source.source_id,
                permission_class=args.permission_class,
                revoked_at=None,
            )
        )
    status = service.run_sync(source)
    print(json.dumps(status.to_json(), indent=1, sort_keys=True))
    if status.status == "failed":
        print("sync gate: FAILED", file=sys.stderr)
        return 3
    if status.status == "partial":
        print("sync gate: PARTIAL (failures visible on the screen)", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
