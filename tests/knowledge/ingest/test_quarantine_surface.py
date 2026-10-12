"""A14-2 quarantine surfacing: invalid documents stay queryable-as-failed.

Failed extraction is reported with visible errors — never silently dropped,
never substituted with invented text.
"""

from __future__ import annotations


def test_failed_doc_is_queryable_with_visible_error(
    service, make_source, make_vault, tenant_id
):
    root, _ = make_vault("notes/simple-note.md", "malformed/bad-frontmatter.md")
    source = make_source(root)

    result = service.search("owner", "bad-frontmatter", tenant_id=tenant_id)
    assert len(result["failures"]) == 1
    failed = result["failures"][0]
    assert failed["source_id"] == source.source_id
    assert failed["status"] == "failed"
    assert failed["reason"] == "frontmatter"
    assert failed["message"], "error text must be visible"
    assert "bad-frontmatter" in failed["path"]

    # The good note is still searchable alongside the failed one.
    good = service.search("owner", "bootstrapping", tenant_id=tenant_id)
    assert good["hits"] and not good["failures"]


def test_quarantine_visible_on_screen_and_detail(service, make_source, make_vault, tenant_id):
    root, _ = make_vault("malformed/bad-frontmatter.md")
    source = make_source(root)

    row = next(
        r for r in service.screen("owner", tenant_id) if r["source_id"] == source.source_id
    )
    assert row["sync"]["status"] == "partial"
    assert row["failures"], "screen must list the failure"
    assert row["failures"][0]["kind"] == "quarantine"
    assert row["sync"]["quarantined"] >= 1

    records = service.quarantine(source.source_id)
    assert records and records[0].reason == "frontmatter"
    assert "no chunks generated" in records[0].message


def test_unsupported_asset_surfaces_as_failure(service, make_source, make_vault, tenant_id):
    root, _ = make_vault("notes/simple-note.md", "assets/mystery.bin")
    source = make_source(root)

    row = next(
        r for r in service.screen("owner", tenant_id) if r["source_id"] == source.source_id
    )
    kinds = {f["kind"] for f in row["failures"]}
    assert "extraction:unsupported" in kinds, "unsupported assets stay visible"


def test_failed_docs_hidden_from_roles_without_class_access(
    service, make_source, tmp_path, tenant_id
):
    root = tmp_path / "eng-vault"
    root.mkdir()
    (root / "bad.md").write_text("---\nno colon here\n---\n\n# Body\n", encoding="utf-8")
    make_source(root, permission_class="engineering_docs")

    owner = service.search("owner", "bad", tenant_id=tenant_id)
    viewer = service.search("viewer", "bad", tenant_id=tenant_id)
    assert owner["failures"], "owner sees the failed engineering doc"
    assert viewer["failures"] == [], "viewer must not learn of engineering docs"
