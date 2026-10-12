"""A14-2 tombstones: removal propagation proven with a real timed test.

The declared window is 60s (DEFAULT_PROPAGATION_SECONDS). The test removes a
live, searchable source with a warm result cache and measures wall-clock time
until online search exposes nothing from it. The cache TTL bound is asserted
to sit strictly inside the window as defense in depth.
"""

from __future__ import annotations

import time

import pytest

from algobots.knowledge.ingest import (
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_PROPAGATION_SECONDS,
    PermissionDenied,
)
from algobots.knowledge.ingest.tombstones import parse_iso


def _exposure(service, tenant_id):
    result = service.search("owner", "bootstrapping", tenant_id=tenant_id)
    return result


def test_removal_propagation_window_real_timed(service, make_source, make_vault, tenant_id):
    root, _ = make_vault("notes/simple-note.md", "notes/nested-note.md")
    source = make_source(root)

    first = _exposure(service, tenant_id)
    assert first["hits"], "source must be exposed before removal"
    assert all(h["source_id"] == source.source_id for h in first["hits"])
    # Warm the cache with a second query (TTL 30s default) so the purge hook
    # has a real entry to invalidate, not an empty cache.
    warm = _exposure(service, tenant_id)
    assert warm["hits"]

    t0 = time.perf_counter()
    tombstone = service.remove_source(
        source.source_id, reason="gdpr-style removal", revoked_by="user-1", actor_role="owner"
    )
    removal_ms = (time.perf_counter() - t0) * 1000

    # Poll online search until exposure ceases; hard stop at the window.
    deadline = t0 + DEFAULT_PROPAGATION_SECONDS
    result = None
    while time.perf_counter() < deadline:
        result = _exposure(service, tenant_id)
        if not result["hits"] and not result["failures"]:
            break
        time.sleep(0.05)
    elapsed = time.perf_counter() - t0

    assert result is not None
    assert result["hits"] == [], f"exposure survived removal: {result['hits']}"
    assert result["failures"] == []
    assert elapsed <= DEFAULT_PROPAGATION_SECONDS, (
        f"propagation took {elapsed:.3f}s, window is {DEFAULT_PROPAGATION_SECONDS}s"
    )
    assert removal_ms < 2_000, "synchronous invalidation hook should be fast"
    assert tombstone.propagated_at is not None
    assert parse_iso(tombstone.propagated_at) <= parse_iso(tombstone.propagation_deadline)

    # Durable state after the window: tombstone + revoked ACL on record.
    stored = service.active_tombstone(source.source_id)
    assert stored.reason == "gdpr-style removal"
    assert stored.propagated_at
    assert service.get_acl(source.source_id).revoked_at is not None

    row = next(
        r for r in service.screen("owner", tenant_id) if r["source_id"] == source.source_id
    )
    assert row["tombstoned"] is True
    assert row["acl_revoked_at"] is not None
    assert row["readable"] is False


def test_removed_source_stays_hidden_from_cache_after_invalidation(
    service, make_source, make_vault, tenant_id
):
    root, _ = make_vault("notes/simple-note.md")
    source = make_source(root)
    assert service.search("owner", "methods", tenant_id=tenant_id)["hits"]
    # Same query again is served from cache pre-removal.
    assert service.search("owner", "methods", tenant_id=tenant_id)["hits"]
    service.remove_source(source.source_id, reason="test", actor_role="owner")
    cached = service.search("owner", "methods", tenant_id=tenant_id)
    assert cached["hits"] == [] and cached["failures"] == []


def test_cache_ttl_sits_inside_propagation_window():
    assert DEFAULT_CACHE_TTL_SECONDS < DEFAULT_PROPAGATION_SECONDS


@pytest.mark.parametrize("role", ["member", "viewer", "intern", None])
def test_removal_requires_owner_role(service, make_source, make_vault, role):
    root, _ = make_vault("notes/simple-note.md")
    source = make_source(root)
    with pytest.raises(PermissionDenied):
        service.remove_source(source.source_id, reason="nope", actor_role=role)
    assert service.active_tombstone(source.source_id) is None
    assert service.get_acl(source.source_id).live


def test_removal_of_unknown_source_raises(service):
    with pytest.raises(KeyError):
        service.remove_source("src-missing", reason="x", actor_role="owner")


def test_tombstones_are_queryable_history(service, make_source, make_vault, tenant_id):
    root, _ = make_vault("notes/simple-note.md")
    source = make_source(root)
    service.remove_source(source.source_id, reason="audit-test", actor_role="owner")
    history = service.tombstones(source.source_id)
    assert len(history) == 1
    assert history[0].reason == "audit-test"
    assert history[0].propagation_seconds == DEFAULT_PROPAGATION_SECONDS
    # lineage is never deleted: documents and versions survive removal
    assert service.store.documents(source.source_id)
