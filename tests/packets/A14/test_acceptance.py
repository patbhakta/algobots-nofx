"""A14 acceptance cases AC1-AC5 (ALG-3320) — executable end-to-end proofs.

Each case drives the packet's real surface the way the Kestra stage does
(``Ingestor.register_source`` -> ``SearchService.run_sync`` -> online search
/ removal), on synthetic fixture vaults only — never stock-vaults live data.
The acceptance harness (``tests/packets/A14/acceptance.py``) maps these to
the parent spec's AC1-AC5 and folds in the unit lanes as supporting tests.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from uuid import uuid4

import pytest

from algobots.knowledge.ingest import (
    DEFAULT_PROPAGATION_SECONDS,
    ApprovedProcessors,
    PathEscapeError,
    PermissionDenied,
    SearchService,
    SimpleProcessor,
    resolve_within_root,
    route_pending,
)
from algobots.knowledge.ingest.ingest import Ingestor
from algobots.knowledge.ingest.models import utcnow_iso
from algobots.knowledge.ingest.store import JsonIngestStore

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TENANT = uuid4()


def make_vault(tmp_path: Path, *names: str) -> Path:
    """Fresh vault root populated from the committed fixtures."""
    root = tmp_path / "vault"
    root.mkdir(parents=True)
    for name in names:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(FIXTURES / name, target)
    return root


def sync(tmp_path: Path, root: Path):
    """The exact sequence the pipeline stage runs: register + sync."""
    store = JsonIngestStore(tmp_path / "store")
    service = SearchService(store)
    source = Ingestor.register_source(store, tenant_id=TENANT, root=root, acl_ref="acceptance")
    return store, service, source, service.run_sync(source)


def only(hits: list[dict], term: str) -> dict:
    matching = [h for h in hits if term in h["text"]]
    assert matching, f"no hit contains {term!r}"
    return matching[0]


# ------------------------------------------------------------------ AC1 --

def test_ac1_unchanged_reimport_reembeds_zero_chunks(tmp_path: Path):
    root = make_vault(tmp_path, "notes/simple-note.md", "notes/nested-note.md")
    store, service, source, first = sync(tmp_path, root)

    assert first.status == "ok", first.errors
    assert first.docs == 2
    assert first.embeddings_new > 0, "first import must embed the chunks"

    second = service.run_sync(source)

    assert second.status == "ok"
    assert second.embeddings_new == 0, "unchanged reimport re-embedded chunks"
    assert second.chunks_indexed == first.chunks_indexed
    assert second.last_snapshot_id == first.last_snapshot_id
    # Zero work everywhere: no new documents, no new versions, no rewrites.
    report = Ingestor(store).run(source)
    assert report.documents_new == []
    assert report.versions_new == []
    assert report.unchanged == 2

    manifest = json.loads(
        next((store.root / "index" / "embeddings").glob("*/manifest.json")).read_text()
    )
    assert len(manifest["chunks"]) == first.chunks_indexed

    # Idempotency holds across CLI processes too: the stage re-run via
    # `python -m algobots.knowledge.ingest.sync` reports the same zero work.
    import os
    import subprocess
    import sys

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "algobots.knowledge.ingest.sync",
            "--root",
            str(root),
            "--store",
            str(store.root),
            "--tenant",
            str(TENANT),
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": "src"},
        cwd=Path(__file__).resolve().parents[3],
        check=True,
    )
    cli_status = json.loads(proc.stdout)
    assert cli_status["status"] == "ok"
    assert cli_status["embeddings_new"] == 0


# ------------------------------------------------------------------ AC2 --

def test_ac2_rename_keeps_identity_and_citations_edit_makes_new_version(tmp_path: Path):
    root = make_vault(tmp_path, "notes/simple-note.md")
    store, service, source, first = sync(tmp_path, root)
    doc = store.documents(source.source_id)[0]
    citation = only(service.search("owner", "bootstrapping", tenant_id=TENANT)["hits"], "Deeper")
    assert citation["doc_id"] == doc.doc_id

    # Rename: same bytes at a new path -> same identity, same citation.
    # Post-change reads go through a fresh service view: the running
    # service's 30s result cache is allowed to serve the pre-rename path
    # (TTL sits inside the 60s propagation window by design).
    (root / "notes" / "simple-note.md").rename(root / "notes" / "renamed-note.md")
    after_rename = service.run_sync(source)
    fresh = SearchService(store)

    renamed = store.get_document(doc.doc_id)
    assert renamed.current_path.endswith("renamed-note.md")
    assert renamed.doc_id == doc.doc_id
    assert renamed.current_version_id == doc.current_version_id, "rename must not version"
    assert len(renamed.path_history) == 2
    assert after_rename.embeddings_new == 0, "rename re-embedded chunks"

    hit = only(fresh.search("owner", "bootstrapping", tenant_id=TENANT)["hits"], "Deeper")
    assert hit["chunk_id"] == citation["chunk_id"], "citation chunk id changed on rename"
    assert hit["version_id"] == citation["version_id"]
    assert hit["path"].endswith("renamed-note.md")

    # Edit: new content -> new version on the same document, old version kept.
    note = root / "notes" / "renamed-note.md"
    note.write_text(note.read_text() + "\n## Fresh analysis\n\nEdited body content.\n")
    after_edit = service.run_sync(source)

    edited = store.get_document(doc.doc_id)
    assert edited.doc_id == doc.doc_id
    assert edited.current_version_id != doc.current_version_id
    assert doc.current_version_id in edited.version_history
    versions = store.versions(doc.doc_id)
    assert len(versions) == 2, "edit must chain exactly one new version"
    assert after_edit.embeddings_new > 0, "edited sections must be (re)embedded"
    assert after_edit.chunks_indexed > first.chunks_indexed

    new_hit = only(service.search("owner", "fresh analysis", tenant_id=TENANT)["hits"], "Edited")
    assert new_hit["doc_id"] == doc.doc_id
    assert new_hit["version_id"] == edited.current_version_id


# ------------------------------------------------------------------ AC3 --

def test_ac3_delete_and_acl_revoke_exposure_ceases_within_60s(tmp_path: Path):
    root = make_vault(tmp_path, "notes/simple-note.md")
    store, service, source, _ = sync(tmp_path, root)
    query = ("owner", "bootstrapping")
    assert service.search(query[0], query[1], tenant_id=TENANT)["hits"]
    service.search(query[0], query[1], tenant_id=TENANT)  # warm the cache

    # ACL revocation: reads stop for every role including owner.
    t0 = time.perf_counter()
    acl = service.get_acl(source.source_id)
    acl.revoked_at = utcnow_iso()
    service.set_acl(acl)
    while service.search(query[0], query[1], tenant_id=TENANT)["hits"]:
        assert time.perf_counter() - t0 < DEFAULT_PROPAGATION_SECONDS
        time.sleep(0.05)
    revoke_elapsed = time.perf_counter() - t0
    assert revoke_elapsed <= DEFAULT_PROPAGATION_SECONDS

    # Restore is explicit and auditable (revocation is not silently undone);
    # read through a fresh view — the negative cache entry an ACL-revoked
    # query may have written is bounded by the 30s TTL, not purgeable (it
    # names no source), so the durable-state check uses a cold reader.
    restored = service.get_acl(source.source_id)
    restored.revoked_at = None
    service.set_acl(restored)
    assert SearchService(store).search(query[0], query[1], tenant_id=TENANT)["hits"]

    # Source delete: tombstone + revocation + invalidation, owner-only.
    with pytest.raises(PermissionDenied):
        service.remove_source(source.source_id, reason="denied", actor_role="member")

    t1 = time.perf_counter()
    tombstone = service.remove_source(
        source.source_id, reason="acceptance AC3", revoked_by="user-1", actor_role="owner"
    )
    while (
        service.search(query[0], query[1], tenant_id=TENANT)["hits"]
        or service.search(query[0], query[1], tenant_id=TENANT)["failures"]
    ):
        assert time.perf_counter() - t1 < DEFAULT_PROPAGATION_SECONDS
        time.sleep(0.05)
    delete_elapsed = time.perf_counter() - t1

    assert delete_elapsed <= DEFAULT_PROPAGATION_SECONDS, (
        f"exposure survived source delete for {delete_elapsed:.3f}s"
    )
    assert tombstone.propagated_at is not None
    assert service.visible_sources("owner", TENANT) == []
    row = next(r for r in service.screen("owner", TENANT) if r["source_id"] == source.source_id)
    assert row["readable"] is False and row["tombstoned"] is True

    # Document-level delete: a vanished path drops out of the live index
    # immediately (fresh reader sees it gone); a warm result cache may serve
    # the old hit until its TTL expires — the TTL is asserted strictly below
    # the 60s window, so exposure ceases either way inside the window.
    root2 = make_vault(tmp_path / "second", "notes/nested-note.md")
    store2, service2, source2, _ = sync(tmp_path / "second", root2)
    before = service2.search("owner", "deep body", tenant_id=TENANT)["hits"]
    assert before
    doc_id = before[0]["doc_id"]
    (root2 / "notes" / "nested-note.md").unlink()
    service2.run_sync(source2)
    from algobots.knowledge.ingest import DEFAULT_CACHE_TTL_SECONDS

    assert DEFAULT_CACHE_TTL_SECONDS < DEFAULT_PROPAGATION_SECONDS
    after = SearchService(store2).search("owner", "deep body", tenant_id=TENANT)["hits"]
    assert all(h["doc_id"] != doc_id for h in after)
    missing = [d for d in store2.documents(source2.source_id) if d.missing]
    assert missing, "vanished path must be flagged missing, lineage kept"


# ------------------------------------------------------------------ AC4 --

def test_ac4_traversal_symlink_malformed_rejected_within_source_root(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret-note.md"
    secret.write_text("# Secret\n\nCONFIDENTIAL-MARKER-XYZ should never be ingested.\n")

    root = make_vault(
        tmp_path,
        "notes/simple-note.md",
        "malformed/bad-utf8.md",
        "malformed/bad-frontmatter.md",
        "malformed/unterminated-frontmatter.md",
    )
    (root / "notes" / "escape.md").symlink_to(secret)
    (root / "nested").mkdir()
    (root / "nested" / "loop").symlink_to(root / "nested", target_is_directory=True)

    store, service, source, status = sync(tmp_path, root)

    # Direct traversal attempts never resolve outside the root.
    with pytest.raises(PathEscapeError):
        resolve_within_root(root, "../escape.md")
    with pytest.raises(PathEscapeError):
        resolve_within_root(root, "nested/../../outside/secret-note.md")

    reasons = {q.reason for q in store.quarantine(source.source_id)}
    assert {"utf8_decode", "frontmatter", "symlink_escape"} <= reasons, reasons
    assert status.status == "partial", "malformed content must surface, not silently pass"

    # No byte outside the registered root was ever read or indexed.
    everything = json.dumps(
        [
            c["text"]
            for f in (store.root / "index" / "fts").glob("*.json")
            for c in json.loads(f.read_text())["chunk_meta"].values()
        ]
    )
    assert "CONFIDENTIAL-MARKER-XYZ" not in everything
    assert service.search("owner", "CONFIDENTIAL-MARKER-XYZ", tenant_id=TENANT)["hits"] == []
    for doc in store.documents(source.source_id):
        assert not doc.current_path.startswith("..")

    # Failures stay queryable-as-failed with visible reasons (never invented).
    failures = service.screen("owner", TENANT)[0]["failures"]
    quarantined_paths = {f["path"] for f in failures if f["kind"] == "quarantine"}
    assert any("bad-utf8" in p for p in quarantined_paths)
    assert all("placeholder" not in (f["message"] or "").lower() for f in failures)


# ------------------------------------------------------------------ AC5 --

def test_ac5_failed_extraction_reported_no_invented_text(tmp_path: Path):
    root = make_vault(tmp_path, "notes/simple-note.md", "assets/fake-scan.png", "assets/mystery.bin")
    store, service, source, status = sync(tmp_path, root)
    assert status.status == "ok"  # queued assets are not extraction failures yet

    pending = {e.path: e for e in store.pending_extractions(source.source_id)}
    assert pending, "assets must be queued, never silently dropped"

    # No approved processor: reported, visible, no text.
    routed = route_pending(store, source.source_id, ApprovedProcessors())
    no_processor = [e for e in routed if "no approved processor" in (e.error or "")]
    assert no_processor, "missing processor must be reported"
    assert all(e.extracted_text is None for e in routed)

    # Unknown types are never routed at all (no universal support claim).
    unknown = [e for e in pending.values() if e.capability == "unknown"]
    assert unknown and all(e.status == "unsupported" for e in unknown)

    # Failed extraction: the error is recorded, text is never substituted.
    def explodes(path: Path):
        raise RuntimeError("tesseract crashed")

    ocr = SimpleProcessor("broken-ocr", frozenset({"ocr"}), explodes)
    requeued = [
        e
        for e in store.pending_extractions(source.source_id)
        if e.status == "no_approved_processor" and e.capability == "ocr"
    ]
    assert requeued
    for entry in requeued:  # make it routable again for the failure run
        entry.status = "pending"
        store.save_pending_extraction(entry)
    routed = route_pending(store, source.source_id, ApprovedProcessors((ocr,)))

    failed = [e for e in routed if e.status == "failed"]
    assert failed and all(e.extracted_text is None for e in failed)
    assert all("tesseract crashed" in (e.error or "") for e in failed)

    quarantine_reasons = {q.reason for q in store.quarantine(source.source_id)}
    assert "extraction_failed" in quarantine_reasons

    # Nothing about the failed asset is searchable as content, and the
    # failure is visible on the sources screen — reported, never invented.
    hits = service.search("owner", "fake-scan", tenant_id=TENANT)["hits"]
    assert all(h["doc_id"] != failed[0].doc_id for h in hits)
    assert not service.search("owner", "invented", tenant_id=TENANT)["hits"]
    kinds = {f["kind"] for f in service.screen("owner", TENANT)[0]["failures"]}
    assert any(k.startswith("extraction:") for k in kinds)
