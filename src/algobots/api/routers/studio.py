"""Studio draft/compile routes (ALG-3408; docs/design/strategy-studio-nautilus-bridge.md).

`/api/studio/strategies` is the gateway draft contract the Studio saves
through. Drafts are tenant-scoped and editable with an optimistic revision
check; compiling appends an immutable artifact row (never updated), and a
`condition_dsl.v1` artifact is a regular `condition_dsl` strategy, so the
existing frozen `/api/deployments` resource deploys it unchanged. Backtests
(slice 2) are not served here yet.

Storage reuses the `strategies` table: a draft row has kind `studio-draft`
with `{"draft", "revision", "artifacts"}` params; each compile adds one row of
kind `condition_dsl` (spec as params) or `studio-artifact` (artifact as params).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from algobots.api.database import get_db
from algobots.api.dependencies import AuthContext, get_auth_context
from algobots.api.models import Strategy
from algobots.strategies.dsl import SPEC_KIND
from algobots.strategies.studio import (
    StudioError,
    compile_studio_strategy,
    parse_draft,
)

router = APIRouter(prefix="/api/studio", tags=["studio"])

log = logging.getLogger("algobots.studio")

DRAFT_KIND = "studio-draft"
ARTIFACT_KIND = "studio-artifact"


class DraftPatch(BaseModel):
    revision: int = Field(ge=1)
    draft: dict[str, Any]


def _tenant(ctx: AuthContext) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No active tenant membership")
    return ctx.tenant_id


def _invalid(exc: StudioError) -> HTTPException:
    return HTTPException(422, exc.to_dict())


def _draft_or_404(db: Session, tenant_id: UUID, draft_id: str | UUID) -> Strategy:
    try:
        sid = UUID(str(draft_id))
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Studio draft not found") from None
    row = db.get(Strategy, sid)
    if row is None or row.tenant_id != tenant_id or row.kind != DRAFT_KIND:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Studio draft not found")
    return row


def draft_out(row: Strategy) -> dict:
    p = row.params
    return {
        "id": str(row.id),
        "name": row.name,
        "revision": p["revision"],
        "draft": p["draft"],
        "artifacts": p.get("artifacts", []),
        "created_at": row.created_at.isoformat(),
        "updated_at": (row.updated_at or row.created_at).isoformat(),
    }


# --- service (also used by the NoFX Studio save path) ---


def save_draft(db: Session, ctx: AuthContext, payload: dict[str, Any]) -> Strategy:
    """Validate and insert a new draft at revision 1 (caller commits)."""
    draft = parse_draft(payload)
    row = Strategy(
        tenant_id=_tenant(ctx),
        user_id=ctx.user.id,
        name=draft.name,
        kind=DRAFT_KIND,
        params_json=json.dumps(
            {"draft": draft.model_dump(mode="json"), "revision": 1, "artifacts": []}
        ),
    )
    db.add(row)
    db.flush()
    return row


def revise_draft(row: Strategy, revision: int, payload: dict[str, Any]) -> None:
    """Save a new revision; 409 unless `revision` is the current one."""
    p = row.params
    if revision != p["revision"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Draft is at revision {p['revision']}, not {revision}; reload and retry",
        )
    draft = parse_draft(payload)
    row.name = draft.name
    p.update(draft=draft.model_dump(mode="json"), revision=p["revision"] + 1)
    row.params_json = json.dumps(p)


def compile_draft(db: Session, ctx: AuthContext, row: Strategy) -> tuple[dict, bool]:
    """Compile the current revision; returns (artifact record, created)."""
    p = row.params
    artifact = compile_studio_strategy(parse_draft(p["draft"]))
    for rec in p.get("artifacts", []):
        if rec["artifact_hash"] == artifact.artifact_hash:
            return rec, False
    compiled = Strategy(
        tenant_id=row.tenant_id,
        user_id=ctx.user.id,
        name=row.name,
        kind=SPEC_KIND if artifact.spec is not None else ARTIFACT_KIND,
        params_json=json.dumps(
            artifact.spec if artifact.spec is not None else artifact.model_dump(mode="json")
        ),
    )
    db.add(compiled)
    db.flush()
    rec = {
        **artifact.model_dump(mode="json"),
        "strategy_id": str(compiled.id),
        "deployable": artifact.spec is not None,
        "draft_revision": p["revision"],
        "compiled_at": datetime.now(UTC).isoformat(),
    }
    p["artifacts"] = [*p.get("artifacts", []), rec]
    row.params_json = json.dumps(p)
    log.info(
        "studio_compiled tenant=%s draft=%s revision=%s artifact_hash=%s implementation=%s",
        row.tenant_id,
        row.id,
        p["revision"],
        artifact.artifact_hash,
        artifact.implementation,
    )
    return rec, True


# --- routes ---


@router.get("/strategies")
def list_drafts(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Strategy)
        .where(Strategy.tenant_id == _tenant(ctx), Strategy.kind == DRAFT_KIND)
        .order_by(Strategy.created_at)
    )
    return {"strategies": [draft_out(r) for r in rows]}


@router.post("/strategies", status_code=status.HTTP_201_CREATED)
def create_draft(
    payload: dict[str, Any],
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    try:
        row = save_draft(db, ctx, payload)
    except StudioError as exc:
        raise _invalid(exc) from None
    db.commit()
    return draft_out(row)


@router.get("/strategies/{draft_id}")
def get_draft(
    draft_id: str, ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)
):
    return draft_out(_draft_or_404(db, _tenant(ctx), draft_id))


@router.patch("/strategies/{draft_id}")
def patch_draft(
    draft_id: str,
    payload: DraftPatch,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    row = _draft_or_404(db, _tenant(ctx), draft_id)
    try:
        revise_draft(row, payload.revision, payload.draft)
    except StudioError as exc:
        raise _invalid(exc) from None
    db.commit()
    return draft_out(row)


@router.post("/strategies/{draft_id}/compile")
def compile_route(
    draft_id: str,
    response: Response,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    row = _draft_or_404(db, _tenant(ctx), draft_id)
    try:
        rec, created = compile_draft(db, ctx, row)
    except StudioError as exc:
        raise _invalid(exc) from None
    db.commit()
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return rec
