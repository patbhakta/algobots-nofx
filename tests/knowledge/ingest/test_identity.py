"""AC1/AC2 — identity and lineage: registration, rename, edit, revert (A14-1).

Acceptance (unit level):
- rename -> SAME document id, new path recorded
- edit -> NEW version on the same document
- a revert re-links the existing version instead of forging a duplicate
- vanished path -> `missing` flag, lineage never destructively deleted
"""

from __future__ import annotations

from algobots.knowledge.ingest import Ingestor, JsonIngestStore
from conftest import register


def _single_doc(store: JsonIngestStore, source) -> object:
    docs = store.documents(source.source_id)
    assert len(docs) == 1
    return docs[0]


def test_register_source_is_idempotent_and_records_tenancy(make_vault, store, ingest):
    from uuid import uuid4

    root, _ = make_vault("notes/simple-note.md")
    tenant = uuid4()
    s1 = Ingestor.register_source(store, tenant_id=tenant, root=root, acl_ref="grant-A")
    s2 = Ingestor.register_source(store, tenant_id=tenant, root=root, acl_ref="grant-A")
    assert s1.source_id == s2.source_id  # content-addressed default id
    assert s1.tenant_id == tenant
    assert s1.acl_ref == "grant-A"
    assert store.get_source(s1.source_id) is not None


def test_register_rejects_missing_root(store, ingest):
    import pytest

    with pytest.raises(ValueError, match="not a directory"):
        Ingestor.register_source(
            store, tenant_id=None, root="/nonexistent/vault", acl_ref="x"  # type: ignore[arg-type]
        )


def test_rename_keeps_document_identity(make_vault, store, ingest):
    root, _ = make_vault("notes/simple-note.md")
    source = register(ingest, store, root)

    r1 = ingest.run(source)
    doc = _single_doc(store, source)
    doc_id, first_version = doc.doc_id, doc.current_version_id
    assert len(r1.renames) == 0

    (root / "simple-note.md").rename(root / "renamed-note.md")
    r2 = ingest.run(source)

    doc = _single_doc(store, source)
    assert doc.doc_id == doc_id  # citations survive the rename
    assert doc.current_path == "renamed-note.md"
    assert [e.path for e in doc.path_history] == ["simple-note.md", "renamed-note.md"]
    assert doc.current_version_id == first_version  # content unchanged: no new version
    assert r2.renames == [(doc_id, "simple-note.md", "renamed-note.md")]
    assert r2.versions_new == []
    assert not doc.missing


def test_edit_creates_new_version_same_document(make_vault, store, ingest):
    root, _ = make_vault("notes/simple-note.md")
    source = register(ingest, store, root)
    ingest.run(source)

    doc = _single_doc(store, source)
    v1 = doc.current_version_id
    (root / "simple-note.md").write_text(
        "# Edited\n\nThe content changed materially.\n", encoding="utf-8"
    )
    r2 = ingest.run(source)

    doc = _single_doc(store, source)
    assert doc.doc_id  # same identity
    assert len(doc.version_history) == 2
    assert doc.current_version_id != v1
    assert len(r2.versions_new) == 1
    v_old, v_new = (store.get_version(vid) for vid in doc.version_history)
    assert v_old.content_hash != v_new.content_hash
    assert v_old.path == v_new.path == "simple-note.md"


def test_revert_relinks_existing_version_zero_new_work(make_vault, store, ingest):
    root, _ = make_vault("notes/simple-note.md")
    source = register(ingest, store, root)
    original = (root / "simple-note.md").read_bytes()

    ingest.run(source)
    (root / "simple-note.md").write_text("# Edited\n\nchanged\n", encoding="utf-8")
    ingest.run(source)
    (root / "simple-note.md").write_bytes(original)  # revert to first content
    r3 = ingest.run(source)

    doc = _single_doc(store, source)
    assert r3.versions_new == []  # version is content-addressed: reused, not forged
    assert r3.chunks_new == []  # chunks are content-addressed: reused
    assert doc.current_version_id == doc.version_history[0]
    assert len(doc.version_history) == 3  # history records the revert hop
    assert doc.version_history[0] == doc.version_history[-1]


def test_vanished_path_is_flagged_missing_lineage_kept(make_vault, store, ingest):
    root, _ = make_vault("notes/simple-note.md")
    source = register(ingest, store, root)
    ingest.run(source)
    doc = _single_doc(store, source)
    doc_id, version_id = doc.doc_id, doc.current_version_id

    (root / "simple-note.md").unlink()
    r2 = ingest.run(source)

    doc = _single_doc(store, source)
    assert doc.doc_id == doc_id
    assert doc.missing is True
    assert r2.missing == [doc_id]
    assert store.get_version(version_id) is not None  # lineage survives
    assert store.chunks_for(version_id)  # evidence survives


def test_missing_doc_returns_when_path_reappears(make_vault, store, ingest):
    root, _ = make_vault("notes/simple-note.md")
    source = register(ingest, store, root)
    ingest.run(source)
    content = (root / "simple-note.md").read_bytes()
    (root / "simple-note.md").unlink()
    ingest.run(source)
    assert _single_doc(store, source).missing is True

    (root / "simple-note.md").write_bytes(content)
    r3 = ingest.run(source)
    doc = _single_doc(store, source)
    assert doc.missing is False
    assert r3.reclaimed == [doc.doc_id]


def test_rename_and_edit_combined_is_a_new_document(make_vault, store, ingest):
    """Hash-keyed rename detection is deterministic: content that moved AND
    changed has no hash successor, so it becomes a new document and the old
    one is flagged missing (documented limitation, never a guess)."""
    root, _ = make_vault("notes/simple-note.md")
    source = register(ingest, store, root)
    ingest.run(source)
    old_doc = _single_doc(store, source)

    (root / "simple-note.md").unlink()
    (root / "renamed.md").write_text("# Moved and edited\n\nnew body\n", encoding="utf-8")
    r2 = ingest.run(source)

    assert r2.renames == []
    assert r2.missing == [old_doc.doc_id]
    assert len(r2.documents_new) == 1
