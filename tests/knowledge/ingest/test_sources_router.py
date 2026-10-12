"""A14-2 HTTP surface: /api/knowledge via register(app), ACLs per role.

The router rides A03's ``get_tenant_context``; tests override that
dependency with stub tenant contexts (the session/membership machinery is
A03's proven surface — here we prove the role matrix, class separation,
cross-tenant 404s, the screen, sync gating and authorized removal).
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from algobots.api.dependencies import TenantContext, get_tenant_context
from algobots.knowledge.ingest.router import register


def build_client(service, *, role, tenant_id):
    app = FastAPI()

    def _override() -> TenantContext:
        return TenantContext(
            user=SimpleNamespace(id=uuid4()),
            session=SimpleNamespace(),
            tenant_id=tenant_id,
            role=role,
        )

    app.dependency_overrides[get_tenant_context] = _override
    register(app, search=service)
    return TestClient(app)


@pytest.fixture()
def two_sources(service, make_source, tmp_path, tenant_id):
    authored = tmp_path / "authored-vault"
    engineering = tmp_path / "engineering-vault"
    for root in (authored, engineering):
        root.mkdir()
        (root / "note.md").write_text(
            "# Methods\n\nBootstrapping body text here.\n", encoding="utf-8"
        )
    a = make_source(authored, permission_class="authored_knowledge")
    e = make_source(engineering, permission_class="engineering_docs")
    return a, e


ROLES = ["owner", "member", "viewer"]


class TestSourcesScreen:
    @pytest.mark.parametrize("role", ROLES)
    def test_screen_lists_sync_state(self, service, two_sources, tenant_id, role):
        client = build_client(service, role=role, tenant_id=tenant_id)
        response = client.get("/api/knowledge/sources")
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 2
        for row in rows:
            sync = row["sync"]
            assert sync["status"] == "ok"
            assert sync["last_good"]["snapshot_id"]
            assert sync["last_good"]["docs"] >= 1
            assert "permission_class" in row and "failures" in row

    def test_screen_denies_unknown_role(self, service, two_sources, tenant_id):
        client = build_client(service, role="intern", tenant_id=tenant_id)
        assert client.get("/api/knowledge/sources").status_code == 403

    def test_screen_requires_authentication(self, service):
        app = FastAPI()
        register(app, search=service)
        client = TestClient(app)
        response = client.get("/api/knowledge/sources")
        assert response.status_code == 401

    def test_detail_includes_failures_and_quarantine(
        self, service, make_source, make_vault, tenant_id
    ):
        root, _ = make_vault("notes/simple-note.md", "malformed/bad-frontmatter.md")
        source = make_source(root)
        client = build_client(service, role="owner", tenant_id=tenant_id)
        detail = client.get(f"/api/knowledge/sources/{source.source_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["sync"]["status"] == "partial"
        assert body["failures"]
        assert body["quarantine"]
        assert body["documents"] >= 1

    def test_quarantine_endpoint_lists_visible_errors(
        self, service, make_source, make_vault, tenant_id
    ):
        root, _ = make_vault("malformed/bad-frontmatter.md")
        source = make_source(root)
        client = build_client(service, role="owner", tenant_id=tenant_id)
        body = client.get(f"/api/knowledge/sources/{source.source_id}/quarantine").json()
        assert body["records"]
        assert body["records"][0]["reason"] == "frontmatter"


class TestSyncGating:
    def test_viewer_cannot_sync(self, service, two_sources, tenant_id):
        client = build_client(service, role="viewer", tenant_id=tenant_id)
        response = client.post(f"/api/knowledge/sources/{two_sources[0].source_id}/sync")
        assert response.status_code == 403
        assert "may not" in response.json()["detail"]

    @pytest.mark.parametrize("role", ["member", "owner"])
    def test_member_and_owner_can_sync(self, service, two_sources, tenant_id, role):
        client = build_client(service, role=role, tenant_id=tenant_id)
        response = client.post(f"/api/knowledge/sources/{two_sources[0].source_id}/sync")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestAuthorizedRemoval:
    @pytest.mark.parametrize("role", ["member", "viewer"])
    def test_non_owner_delete_denied(self, service, two_sources, tenant_id, role):
        client = build_client(service, role=role, tenant_id=tenant_id)
        response = client.delete(f"/api/knowledge/sources/{two_sources[0].source_id}")
        assert response.status_code == 403
        assert service.active_tombstone(two_sources[0].source_id) is None

    def test_owner_delete_tombstones_and_stops_exposure(
        self, service, two_sources, tenant_id
    ):
        victim, survivor = two_sources
        client = build_client(service, role="owner", tenant_id=tenant_id)
        before = client.get("/api/knowledge/search", params={"q": "bootstrapping"}).json()
        assert {h["source_id"] for h in before["hits"]} == {victim.source_id, survivor.source_id}

        response = client.delete(
            f"/api/knowledge/sources/{victim.source_id}",
            params={"reason": "retired vault"},
        )
        assert response.status_code == 200
        body = response.json()
        tomb = body["tombstone"]
        assert body["removed"] is True
        assert tomb["propagated_at"] <= tomb["propagation_deadline"]

        after = client.get("/api/knowledge/search", params={"q": "bootstrapping"}).json()
        assert {h["source_id"] for h in after["hits"]} == {survivor.source_id}

        row = next(
            r
            for r in client.get("/api/knowledge/sources").json()
            if r["source_id"] == victim.source_id
        )
        assert row["tombstoned"] is True and row["readable"] is False

    def test_second_delete_of_same_source_is_404_free_but_tombstoned(
        self, service, two_sources, tenant_id
    ):
        victim = two_sources[0]
        client = build_client(service, role="owner", tenant_id=tenant_id)
        assert client.delete(f"/api/knowledge/sources/{victim.source_id}").status_code == 200
        # The source record still exists (lineage kept): a repeat removal is
        # allowed and idempotent at the exposure level.
        repeat = client.delete(f"/api/knowledge/sources/{victim.source_id}")
        assert repeat.status_code == 200


class TestSearchACLs:
    def test_viewer_denied_engineering_class(self, service, two_sources, tenant_id):
        viewer = build_client(service, role="viewer", tenant_id=tenant_id)
        member = build_client(service, role="member", tenant_id=tenant_id)
        v_hits = viewer.get("/api/knowledge/search", params={"q": "bootstrapping"}).json()["hits"]
        m_hits = member.get("/api/knowledge/search", params={"q": "bootstrapping"}).json()["hits"]
        assert {h["source_id"] for h in v_hits} < {h["source_id"] for h in m_hits}

    def test_failed_docs_follow_class_acl_over_http(
        self, service, make_source, tmp_path, tenant_id
    ):
        root = tmp_path / "eng-vault"
        root.mkdir()
        (root / "broken.md").write_text("---\nnot frontmatter\n---\n\n# Body\n", encoding="utf-8")
        make_source(root, permission_class="engineering_docs")
        viewer = build_client(service, role="viewer", tenant_id=tenant_id)
        owner = build_client(service, role="owner", tenant_id=tenant_id)
        v = viewer.get("/api/knowledge/search", params={"q": "broken"}).json()
        o = owner.get("/api/knowledge/search", params={"q": "broken"}).json()
        assert v["failures"] == []
        assert o["failures"]

    def test_search_requires_query(self, service, two_sources, tenant_id):
        client = build_client(service, role="owner", tenant_id=tenant_id)
        assert client.get("/api/knowledge/search").status_code == 422


class TestCrossTenant:
    def test_cross_tenant_source_is_404(self, service, two_sources, tenant_id):
        other = uuid4()
        client = build_client(service, role="owner", tenant_id=other)
        sid = two_sources[0].source_id
        assert client.get(f"/api/knowledge/sources/{sid}").status_code == 404
        assert client.post(f"/api/knowledge/sources/{sid}/sync").status_code == 404
        assert client.delete(f"/api/knowledge/sources/{sid}").status_code == 404

    def test_cross_tenant_search_exposes_nothing(self, service, two_sources, tenant_id):
        other = uuid4()
        client = build_client(service, role="owner", tenant_id=other)
        body = client.get("/api/knowledge/search", params={"q": "bootstrapping"}).json()
        assert body["hits"] == [] and body["failures"] == []
