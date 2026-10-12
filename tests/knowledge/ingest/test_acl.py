"""A14-2 ACLs: permission classes x A03 roles, default deny, revocation.

Authored knowledge and engineering documentation are separate permission
classes; the role matrix mirrors A03 tenancy (owner > member > viewer) and
unknown roles are denied outright.
"""

from __future__ import annotations

import pytest

from algobots.knowledge.ingest import (
    KNOWLEDGE_ROLE_MATRIX,
    PermissionClass,
    SourceAcl,
    allowed,
    can_read_class,
)


def test_role_matrix_rows():
    owner, member, viewer = (
        KNOWLEDGE_ROLE_MATRIX["owner"],
        KNOWLEDGE_ROLE_MATRIX["member"],
        KNOWLEDGE_ROLE_MATRIX["viewer"],
    )
    assert "knowledge.remove_source" in {a.value for a in owner}
    assert "knowledge.remove_source" not in {a.value for a in member}
    assert "knowledge.remove_source" not in {a.value for a in viewer}
    assert "knowledge.sync" in {a.value for a in member}
    assert "knowledge.sync" not in {a.value for a in viewer}
    assert "knowledge.read_engineering" not in {a.value for a in viewer}


@pytest.mark.parametrize(
    ("role", "action", "expect"),
    [
        ("owner", "knowledge.read_authored", True),
        ("owner", "knowledge.read_engineering", True),
        ("owner", "knowledge.sync", True),
        ("owner", "knowledge.remove_source", True),
        ("member", "knowledge.read_authored", True),
        ("member", "knowledge.read_engineering", True),
        ("member", "knowledge.sync", True),
        ("member", "knowledge.remove_source", False),
        ("viewer", "knowledge.read_authored", True),
        ("viewer", "knowledge.read_engineering", False),
        ("viewer", "knowledge.sync", False),
        ("viewer", "knowledge.remove_source", False),
        ("intern", "knowledge.read_authored", False),  # unknown role: deny
        (None, "knowledge.read_authored", False),  # no role: deny
    ],
)
def test_allowed_default_deny(role, action, expect):
    from algobots.knowledge.ingest.acl import KnowledgeAction

    assert allowed(role, KnowledgeAction(action)) is expect


def test_permission_classes_gate_reads():
    assert can_read_class("viewer", PermissionClass.AUTHORED_KNOWLEDGE)
    assert not can_read_class("viewer", PermissionClass.ENGINEERING_DOCS)
    assert can_read_class("member", PermissionClass.ENGINEERING_DOCS)
    assert can_read_class("owner", PermissionClass.ENGINEERING_DOCS)
    assert not can_read_class("consultant", PermissionClass.AUTHORED_KNOWLEDGE)


def test_default_acl_is_authored_and_live(service):
    acl = service.get_acl("src-doesnotexist")
    assert acl.permission_class == PermissionClass.AUTHORED_KNOWLEDGE.value
    assert acl.live


def test_visible_sources_per_role(service, make_source, tmp_path, tenant_id):
    authored_root = tmp_path / "authored-vault"
    engineering_root = tmp_path / "engineering-vault"
    for root in (authored_root, engineering_root):
        root.mkdir()
        (root / "note.md").write_text(
            "# Methods\n\nBootstrapping body text here.\n", encoding="utf-8"
        )
    make_source(authored_root, permission_class="authored_knowledge")
    make_source(engineering_root, permission_class="engineering_docs")

    visible_viewer = {s.source_id for s, _ in service.visible_sources("viewer", tenant_id)}
    visible_member = {s.source_id for s, _ in service.visible_sources("member", tenant_id)}
    assert visible_member - visible_viewer, "engineering class must hide from viewers"
    assert visible_viewer, "authored class must stay visible to viewers"

    hits_viewer = service.search("viewer", "bootstrapping", tenant_id=tenant_id)["hits"]
    hits_member = service.search("member", "bootstrapping", tenant_id=tenant_id)["hits"]
    assert {h["source_id"] for h in hits_viewer} < {h["source_id"] for h in hits_member}


def test_revoked_acl_denies_every_role_including_owner(
    service, make_source, make_vault, tenant_id
):
    root, _ = make_vault("notes/simple-note.md")
    source = make_source(root)
    assert service.search("owner", "bootstrapping", tenant_id=tenant_id)["hits"]

    acl = service.get_acl(source.source_id)
    acl.revoked_at = "2026-10-12T00:00:00+00:00"
    service.set_acl(acl)

    for role in ("owner", "member", "viewer"):
        assert service.search(role, "bootstrapping", tenant_id=tenant_id)["hits"] == []
        assert service.visible_sources(role, tenant_id) == []
    row = next(
        r for r in service.screen("owner", tenant_id) if r["source_id"] == source.source_id
    )
    assert row["acl_revoked_at"] is not None and row["readable"] is False


def test_cross_tenant_never_visible(service, make_source, make_vault, tenant_id):
    root, _ = make_vault("notes/simple-note.md")
    make_source(root)
    import uuid

    other = uuid.uuid4()
    assert service.visible_sources("owner", other) == []
    assert service.search("owner", "bootstrapping", tenant_id=other)["hits"] == []


def test_source_acl_serialization_roundtrip():
    acl = SourceAcl(
        source_id="s1", permission_class="engineering_docs", revoked_at=None
    )
    from algobots.knowledge.ingest.acl import acl_from_json

    restored = acl_from_json(acl.to_json())
    assert restored.permission_class == "engineering_docs"
    assert restored.live
    revoked = acl_from_json({**acl.to_json(), "revoked_at": "x"})
    assert not revoked.live
