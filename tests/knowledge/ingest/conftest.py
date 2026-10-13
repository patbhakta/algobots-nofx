"""Shared fixtures for A14 ingest unit tests: fixture-vault builder.

Static fixture content lives under tests/packets/A14/fixtures/ (committed
artifacts); each test copies what it needs into a throwaway vault root, then
adds whatever is dynamic (symlinks, edits) locally.

A14-2 additions: a fixed tenant, a SearchService over the store, and a
`make_source` helper that registers a source, sets its permission class,
runs a full sync (ingest + incremental index) and returns the source.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from algobots.knowledge.ingest import Ingestor, JsonIngestStore, SearchService, SourceAcl

FIXTURES = Path(__file__).resolve().parents[2] / "packets" / "A14" / "fixtures"


@pytest.fixture()
def store(tmp_path: Path) -> JsonIngestStore:
    return JsonIngestStore(tmp_path / "store")


@pytest.fixture()
def make_vault(tmp_path: Path):
    """Copy named fixtures into a fresh vault root; returns (root, put)."""

    def _make(*names: str) -> tuple[Path, object]:
        root = tmp_path / "vault"
        root.mkdir(exist_ok=True)

        def put(name: str, dest: str | None = None) -> Path:
            src = FIXTURES / name
            target = root / (dest or Path(name).name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, target)
            return target

        for n in names:
            put(n)
        return root, put

    return _make


@pytest.fixture()
def ingest(store: JsonIngestStore) -> Ingestor:
    return Ingestor(store)


@pytest.fixture()
def tenant_id():
    return uuid4()


@pytest.fixture()
def service(store: JsonIngestStore) -> SearchService:
    return SearchService(store)


@pytest.fixture()
def make_source(store: JsonIngestStore, service: SearchService, tenant_id):
    """Register + classify + sync a source in one step (A14-2 lane)."""

    def _make(root: Path, *, permission_class: str = "authored_knowledge",
              acl_ref: str = "acl:test"):
        source = Ingestor.register_source(
            store, tenant_id=tenant_id, root=root, acl_ref=acl_ref
        )
        service.set_acl(SourceAcl(source_id=source.source_id, permission_class=permission_class))
        service.run_sync(source)
        return source

    return _make


def register(ingestor: Ingestor, store: JsonIngestStore, root: Path):
    """Register a vault root under a random tenant (tenancy is carried in the
    lineage records; auth enforcement is A03's layer, not this slice's)."""
    return Ingestor.register_source(
        store, tenant_id=uuid4(), root=root, acl_ref="acl:test-grant"
    )
