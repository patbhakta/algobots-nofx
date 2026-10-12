"""Shared fixtures for A14-1 ingest unit tests: fixture-vault builder.

Static fixture content lives under tests/packets/A14/fixtures/ (committed
artifacts); each test copies what it needs into a throwaway vault root, then
adds whatever is dynamic (symlinks, edits) locally.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from algobots.knowledge.ingest import Ingestor, JsonIngestStore

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


def register(ingestor: Ingestor, store: JsonIngestStore, root: Path):
    """Register a vault root under a random tenant (tenancy is carried in the
    lineage records; auth enforcement is A03's layer, not this slice's)."""
    return Ingestor.register_source(
        store, tenant_id=uuid4(), root=root, acl_ref="acl:test-grant"
    )
