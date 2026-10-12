"""AC6 — idempotency: unchanged re-import produces ZERO new work (A14-1).

Hash-keyed change detection end to end: same source content -> same snapshot
id (no new snapshot tree), no new documents, no new versions, no new chunks
(embedding work list empty), no duplicate quarantine rows, no duplicate
pending-extraction entries. An edit flips exactly the work it must.
"""

from __future__ import annotations

from algobots.knowledge.ingest import Ingestor
from conftest import register


def _counts(report) -> tuple[int, int, int]:
    return len(report.documents_new), len(report.versions_new), len(report.chunks_new)


def test_unchanged_reimport_is_zero_work_everywhere(make_vault, store, ingest):
    root, _ = make_vault(
        "notes/simple-note.md",
        "notes/nested-note.md",
        "assets/sample-table.csv",
        "assets/fake-scan.png",
    )
    source = register(ingest, store, root)
    r1 = ingest.run(source)
    assert r1.snapshot_created is True
    assert _counts(r1) == (4, 4, 11)  # 2 markdown docs (4+7 chunks) + 2 asset docs
    assert len(r1.assets_queued) == 2

    r2 = ingest.run(source)
    assert r2.snapshot_created is False  # same content -> same snapshot id
    assert r2.snapshot_id == r1.snapshot_id
    assert _counts(r2) == (0, 0, 0)
    assert r2.assets_queued == []
    assert r2.unchanged == 4
    assert r2.renames == []
    assert r2.missing == []
    assert r2.quarantined == []

    # store contents did not grow: file-count stable across a re-import
    files_before = {p for p in store.root.rglob("*") if p.is_file()}
    ingest.run(source)
    files_after = {p for p in store.root.rglob("*") if p.is_file()}
    assert files_before == files_after


def test_chunk_ids_content_addressed_across_duplicate_documents(make_vault, store, ingest):
    """Two files with identical content are two documents but ONE set of
    chunk ids — duplicate evidence never duplicates embedding work."""
    root, put = make_vault("notes/simple-note.md")
    put("notes/simple-note.md", dest="sub/copy.md")
    source = register(ingest, store, root)
    report = ingest.run(source)

    assert len(report.documents_new) == 2
    assert len(report.chunks_new) == 4  # 4 distinct chunk ids, not 8
    docs = store.documents(source.source_id)
    ids = [c.chunk_id for d in docs for c in store.chunks_for(d.current_version_id)]
    assert len(ids) == 8  # two documents each hold the 4 chunks...
    assert len(set(ids)) == 4  # ...but the ids (embedding keys) are identical


def test_edit_flip_only_the_edited_document(make_vault, store, ingest):
    root, put = make_vault("notes/simple-note.md", "notes/nested-note.md")
    source = register(ingest, store, root)
    ingest.run(source)

    put("notes/nested-note.md")  # overwrite with IDENTICAL bytes -> no-op
    (root / "simple-note.md").write_text("# Rewritten\n\nbrand new\n", encoding="utf-8")
    r2 = ingest.run(source)

    assert r2.unchanged == 1  # nested-note.md untouched
    assert len(r2.versions_new) == 1
    assert len(r2.chunks_new) == 1  # rewritten note: heading starts line 1, one section
    assert r2.documents_new == []


def test_reregister_same_root_same_source_id(make_vault, store, ingest):
    root, _ = make_vault("notes/simple-note.md")
    source = register(ingest, store, root)
    ingest.run(source)
    again = Ingestor.register_source(
        store, tenant_id=source.tenant_id, root=root, acl_ref=source.acl_ref
    )
    assert again.source_id == source.source_id
    r2 = ingest.run(again)
    assert _counts(r2) == (0, 0, 0)


def test_quarantine_security_findings_not_duplicated_on_reimport(
    make_vault, store, ingest, tmp_path
):
    root, _ = make_vault("notes/simple-note.md")
    outside = tmp_path / "out.md"
    outside.write_text("out")
    (root / "esc.md").symlink_to(outside)
    source = register(ingest, store, root)
    r1 = ingest.run(source)
    assert r1.quarantined

    r2 = ingest.run(source)
    assert r2.quarantined == []  # recurring finding deduped by record id
    rows = [q for q in store.quarantine(source.source_id) if q.path == "esc.md"]
    assert len(rows) == 1


def test_asset_reimport_after_edit_makes_new_queue_entry_only_for_new_content(
    make_vault, store, ingest
):
    root, _ = make_vault("assets/sample-table.csv")
    source = register(ingest, store, root)
    r1 = ingest.run(source)
    entry1 = r1.assets_queued[0]

    r2 = ingest.run(source)
    assert r2.assets_queued == []

    (root / "sample-table.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    r3 = ingest.run(source)
    assert len(r3.assets_queued) == 1
    assert r3.assets_queued[0] != entry1  # new content -> new queue entry
    assert len(store.pending_extractions(source.source_id)) == 2
