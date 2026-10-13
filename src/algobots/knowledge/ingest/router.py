"""HTTP surface for knowledge sources (A14-2): router module + ``register``.

Lives INSIDE the ingest package per the frozen A14 write scope; the app mount
is a two-line integration done by the TL in ``algobots.api.main``::

    from algobots.knowledge.ingest.router import register as register_knowledge
    register_knowledge(app)   # or register_knowledge(app, store=..., search=...)

Authorization rides A03 tenancy: every route depends on
``algobots.api.dependencies.get_tenant_context`` (live session -> active
membership -> role), then applies the knowledge role matrix in
``algobots.knowledge.ingest.acl``. Cross-tenant source ids are 404s, never
403s — existence is not leaked across tenants. The ingest core modules stay
stdlib-only; this router is the only file in the package that imports the
API stack, and it is deliberately NOT re-exported from the package
``__init__`` so core imports stay framework-free.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from algobots.api.dependencies import TenantContext, get_tenant_context
from algobots.knowledge.ingest.acl import (
    KnowledgeAction,
    allowed,
)
from algobots.knowledge.ingest.search import PermissionDenied, SearchService
from algobots.knowledge.ingest.store import JsonIngestStore

DEFAULT_STORE_ENV = "ALGOBOTS_KNOWLEDGE_STORE"
DEFAULT_STORE_PATH = Path("var/knowledge-ingest")


def _require(action: KnowledgeAction):
    """Dependency factory: the active membership's role must allow `action`."""

    def check(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        if not allowed(ctx.role, action):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role '{ctx.role}' may not perform {action.value}",
            )
        return ctx

    return check


def _require_reader(ctx: TenantContext) -> None:
    if not (
        allowed(ctx.role, KnowledgeAction.READ_AUTHORED)
        or allowed(ctx.role, KnowledgeAction.READ_ENGINEERING)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No knowledge read permission")


def make_router(service: SearchService) -> APIRouter:
    router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

    def _source_or_404(source_id: str, tenant_id: UUID):
        source = service.store.get_source(source_id)
        if source is None or source.tenant_id != tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
        return source

    # ------------------------------------------------------------- screen --
    @router.get("/sources")
    def list_sources(
        ctx: TenantContext = Depends(get_tenant_context),
    ) -> list[dict[str, Any]]:
        """Knowledge-source screen: sync status, last successful version,
        failures, permission class, tombstone state — tenant-scoped."""
        _require_reader(ctx)
        return service.screen(ctx.role, ctx.tenant_id)

    @router.get("/sources/{source_id}")
    def source_detail(
        source_id: str,
        ctx: TenantContext = Depends(get_tenant_context),
    ) -> dict[str, Any]:
        _require_reader(ctx)
        _source_or_404(source_id, ctx.tenant_id)
        rows = [r for r in service.screen(ctx.role, ctx.tenant_id) if r["source_id"] == source_id]
        detail = rows[0] if rows else {}
        detail["quarantine"] = [
            {
                "path": q.path,
                "reason": q.reason,
                "message": q.message,
                "occurred_at": q.occurred_at,
            }
            for q in service.quarantine(source_id)
        ]
        detail["pending_extractions"] = [
            {
                "entry_id": e.entry_id,
                "path": e.path,
                "capability": e.capability,
                "status": e.status,
                "error": e.error,
            }
            for e in service.pending(source_id)
        ]
        detail["documents"] = len(service.store.documents(source_id))
        return detail

    @router.get("/sources/{source_id}/quarantine")
    def source_quarantine(
        source_id: str,
        ctx: TenantContext = Depends(get_tenant_context),
    ) -> dict[str, Any]:
        """Quarantine surfacing: invalid documents stay queryable-as-failed
        with visible errors, never silently dropped."""
        _require_reader(ctx)
        _source_or_404(source_id, ctx.tenant_id)
        return {
            "source_id": source_id,
            "records": [
                {
                    "record_id": q.record_id,
                    "path": q.path,
                    "reason": q.reason,
                    "message": q.message,
                    "occurred_at": q.occurred_at,
                    "content_hash": q.content_hash,
                }
                for q in service.quarantine(source_id)
            ],
        }

    # --------------------------------------------------------------- sync --
    @router.post("/sources/{source_id}/sync")
    def sync_source(
        source_id: str,
        ctx: TenantContext = Depends(_require(KnowledgeAction.SYNC)),
    ) -> dict[str, Any]:
        """Re-run ingest + incremental indexing for one source (member+)."""
        source = _source_or_404(source_id, ctx.tenant_id)
        try:
            result = service.run_sync(source)
        except Exception as exc:  # noqa: BLE001 — surfaced as 503 with cause
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, f"Sync failed: {exc}"
            ) from exc
        return result.to_json()

    # ------------------------------------------------------------- removal --
    @router.delete("/sources/{source_id}")
    def remove_source(
        source_id: str,
        ctx: TenantContext = Depends(_require(KnowledgeAction.REMOVE_SOURCE)),
        reason: str = Query(default="owner-removal", min_length=1, max_length=500),
    ) -> dict[str, Any]:
        """Authorized removal (owner-only): tombstone + ACL revocation +
        cache/index invalidation. The response carries the declared
        propagation window and its proven completion timestamp."""
        source = _source_or_404(source_id, ctx.tenant_id)
        try:
            tombstone = service.remove_source(
                source.source_id,
                reason=reason,
                revoked_by=str(ctx.user.id),
                actor_role=ctx.role,
            )
        except PermissionDenied as exc:
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
        return {
            "source_id": source.source_id,
            "removed": True,
            "tombstone": tombstone.to_json(),
        }

    # ------------------------------------------------------------- search --
    @router.get("/search")
    def search(
        q: str = Query(min_length=1, max_length=500),
        limit: int = Query(default=10, ge=1, le=50),
        ctx: TenantContext = Depends(get_tenant_context),
    ) -> dict[str, Any]:
        """Online search gated by ACLs + tombstones. Results include failed
        documents (visible errors) for sources the role may read."""
        _require_reader(ctx)
        return service.search(ctx.role, q, tenant_id=ctx.tenant_id, limit=limit)

    return router


def build_service(
    store: JsonIngestStore | None = None, search: SearchService | None = None
) -> SearchService:
    """Resolve the service: explicit instance wins, else a store, else the
    ``ALGOBOTS_KNOWLEDGE_STORE`` env path (default ``var/knowledge-ingest``)."""
    if search is not None:
        return search
    if store is None:
        root = os.environ.get(DEFAULT_STORE_ENV) or DEFAULT_STORE_PATH
        store = JsonIngestStore(Path(root))
    return SearchService(store)


def register(
    app: Any,
    *,
    store: JsonIngestStore | None = None,
    search: SearchService | None = None,
) -> None:
    """Mount the knowledge surface on a FastAPI app (the TL's 2-line hook)."""
    service = build_service(store=store, search=search)
    app.include_router(make_router(service))
