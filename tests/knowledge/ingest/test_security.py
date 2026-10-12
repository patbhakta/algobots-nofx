"""AC5 — security: path confinement, symlink escapes, quarantine (A14-1).

Acceptance (unit level):
- `..` traversal and absolute paths rejected without reading outside the root
- symlink escaping the root rejected, and the outside file's bytes NEVER
  appear anywhere in the store (snapshots, chunks, reports)
- malformed attachments -> quarantine row with a visible error, never a
  silent drop, never invented text
"""

from __future__ import annotations

from pathlib import Path

import pytest

from algobots.knowledge.ingest import PathEscapeError, resolve_within_root
from conftest import register


# ---------------------------------------------------------- path resolution --
def test_dotdot_traversal_rejected(tmp_path: Path):
    root = tmp_path / "vault"
    root.mkdir()
    with pytest.raises(PathEscapeError) as ei:
        resolve_within_root(root, "../outside.md")
    assert ei.value.reason == "dotdot_traversal"


def test_nested_traversal_net_rejected(tmp_path: Path):
    root = tmp_path / "vault"
    (root / "sub").mkdir(parents=True)
    with pytest.raises(PathEscapeError):
        resolve_within_root(root, "sub/../../outside.md")


def test_absolute_path_rejected(tmp_path: Path):
    root = tmp_path / "vault"
    root.mkdir()
    with pytest.raises(PathEscapeError) as ei:
        resolve_within_root(root, "/etc/passwd")
    assert ei.value.reason == "absolute_path"


def test_in_root_relative_resolution_succeeds(tmp_path: Path):
    root = tmp_path / "vault"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "note.md").write_text("x")
    resolved = resolve_within_root(root, "sub/note.md")
    assert resolved == (root / "sub" / "note.md").resolve()


def test_even_self_cancelling_dotdot_is_rejected(tmp_path: Path):
    """Strict policy: any `..` component is traversal syntax — vault-relative
    paths never need it, and rejecting outright leaves no grey zone."""
    root = tmp_path / "vault"
    (root / "sub").mkdir(parents=True)
    with pytest.raises(PathEscapeError) as ei:
        resolve_within_root(root, "sub/../sub/note.md")
    assert ei.value.reason == "dotdot_traversal"


def test_symlink_escape_rejected_at_resolution(tmp_path: Path):
    root = tmp_path / "vault"
    root.mkdir()
    outside = tmp_path / "outside" / "secret.md"
    outside.parent.mkdir()
    outside.write_text("SECRET")
    (root / "link.md").symlink_to(outside)
    with pytest.raises(PathEscapeError) as ei:
        resolve_within_root(root, "link.md")
    assert ei.value.reason == "symlink_escape"


# ------------------------------------------------------------- ingest level --
def test_symlink_escape_rejected_and_outside_bytes_never_read(make_vault, store, ingest, tmp_path):
    root, put = make_vault("notes/simple-note.md")
    outside = tmp_path / "outside" / "secret-target.md"
    outside.parent.mkdir()
    outside.write_text("SECRET-CONTENT-8f3a", encoding="utf-8")
    (root / "escape.md").symlink_to(outside)  # escaping symlink fixture

    source = register(ingest, store, root)
    report = ingest.run(source)

    # rejected with a visible, classified quarantine record
    reasons = {q.path: q.reason for q in store.quarantine(source.source_id)}
    assert reasons.get("escape.md") == "symlink_escape"
    assert report.quarantined
    assert any("escape" in e for e in report.errors)

    # the escaped path never became a document
    doc_paths = {d.current_path for d in store.documents(source.source_id)}
    assert "escape.md" not in doc_paths
    assert "simple-note.md" in doc_paths

    # and the outside bytes appear NOWHERE in the store — proof nothing
    # outside the root was read
    sentinel = b"SECRET-CONTENT-8f3a"
    for p in store.root.rglob("*"):
        if p.is_file():
            assert sentinel not in p.read_bytes(), f"outside bytes leaked into {p}"


def test_inside_root_symlink_skipped_visibly(make_vault, store, ingest):
    root, _ = make_vault("notes/simple-note.md", "notes/nested-note.md")
    (root / "alias.md").symlink_to(root / "simple-note.md")  # inside-root link

    source = register(ingest, store, root)
    ingest.run(source)

    reasons = {q.path: q.reason for q in store.quarantine(source.source_id)}
    assert reasons.get("alias.md") == "symlink_skipped"
    doc_paths = {d.current_path for d in store.documents(source.source_id)}
    assert "alias.md" not in doc_paths  # no identity doubling through links


def test_symlinked_directory_escape_rejected(make_vault, store, ingest, tmp_path):
    root, put = make_vault("notes/simple-note.md")
    outside_dir = tmp_path / "outside-dir"
    outside_dir.mkdir()
    (outside_dir / "leaked.md").write_text("LEAK-7c1d", encoding="utf-8")
    (root / "linked-dir").symlink_to(outside_dir)

    source = register(ingest, store, root)
    ingest.run(source)

    reasons = {q.path: q.reason for q in store.quarantine(source.source_id)}
    assert reasons.get("linked-dir") == "symlink_escape"
    doc_paths = {d.current_path for d in store.documents(source.source_id)}
    assert not any(p.startswith("linked-dir") for p in doc_paths)
    for p in store.root.rglob("*"):
        if p.is_file():
            assert b"LEAK-7c1d" not in p.read_bytes()


def test_malformed_utf8_note_quarantined_no_placeholder(make_vault, store, ingest):
    root, _ = make_vault("notes/simple-note.md", "malformed/bad-utf8.md")
    source = register(ingest, store, root)
    ingest.run(source)

    q = [r for r in store.quarantine(source.source_id) if r.path == "bad-utf8.md"]
    assert len(q) == 1
    assert q[0].reason == "utf8_decode"
    assert q[0].content_hash  # content is still hashed and snapshotted

    doc = next(d for d in store.documents(source.source_id) if d.current_path == "bad-utf8.md")
    version = store.get_version(doc.current_version_id)
    assert version is not None
    assert version.chunk_count == 0  # failed parse -> NO chunks
    assert store.chunks_for(version.version_id) == []
    all_chunk_text = " ".join(
        c.text
        for d in store.documents(source.source_id)
        for c in store.chunks_for(d.current_version_id or "")
    )
    assert "binary junk" not in all_chunk_text  # nothing invented, nothing leaked


def test_unterminated_frontmatter_quarantined(make_vault, store, ingest):
    root, _ = make_vault("malformed/unterminated-frontmatter.md")
    source = register(ingest, store, root)
    ingest.run(source)

    q = [r for r in store.quarantine(source.source_id)]
    assert len(q) == 1
    assert q[0].reason == "frontmatter"
    doc = store.documents(source.source_id)[0]
    assert store.get_version(doc.current_version_id).chunk_count == 0


def test_bad_frontmatter_line_quarantined(make_vault, store, ingest):
    root, _ = make_vault("malformed/bad-frontmatter.md")
    source = register(ingest, store, root)
    ingest.run(source)

    q = store.quarantine(source.source_id)
    assert len(q) == 1
    assert q[0].reason == "frontmatter"
    assert "no colon" in q[0].message


def test_snapshot_store_is_immutable_and_pre_parse(make_vault, store, ingest):
    """Snapshots are taken BEFORE parsing: later edits to the live vault never
    mutate an existing snapshot, and parsing reads only snapshot copies."""
    root, _ = make_vault("notes/simple-note.md")
    source = register(ingest, store, root)
    r1 = ingest.run(source)
    snap_dir = store.snapshot_dir(source.source_id, r1.snapshot_id)
    snap_copy = snap_dir / "simple-note.md"
    snap_bytes = snap_copy.read_bytes()
    assert snap_bytes == (root / "simple-note.md").read_bytes()

    (root / "simple-note.md").write_text("# Live edit after snapshot\n", encoding="utf-8")
    assert snap_copy.read_bytes() == snap_bytes  # snapshot untouched
    r2 = ingest.run(source)
    assert r2.snapshot_id != r1.snapshot_id  # new content -> NEW snapshot
    assert (snap_dir / "simple-note.md").read_bytes() == snap_bytes
