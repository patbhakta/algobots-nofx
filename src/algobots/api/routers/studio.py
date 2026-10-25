"""Studio draft/compile routes (ALG-3408; docs/design/strategy-studio-nautilus-bridge.md).

`/api/studio/strategies` is the gateway draft contract the Studio saves
through. Drafts are tenant-scoped and editable with an optimistic revision
check; compiling appends an immutable artifact row (never updated), and a
`condition_dsl.v1` artifact is a regular `condition_dsl` strategy, so the
existing frozen `/api/deployments` resource deploys it unchanged.

Backtests (ALG-3418, slice 2): `POST .../{id}/backtest` runs the draft's
latest compiled artifact on a published warehouse snapshot and
stores one immutable `studio-backtest` row keyed by (artifact hash, dataset
snapshot id); the tenant-scoped primary key makes the pair unique across drafts.

Storage reuses the `strategies` table: a draft row has kind `studio-draft`
with `{"draft", "revision", "artifacts"}` params; each compile adds one row of
kind `condition_dsl` (spec as params) or `studio-artifact` (artifact as params).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from algobots.api.config import get_settings
from algobots.api.database import get_db
from algobots.api.dependencies import AuthContext, get_auth_context
from algobots.api.models import Strategy
from algobots.strategies import backtest as bt
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
BACKTEST_KIND = "studio-backtest"


class DraftPatch(BaseModel):
    revision: int = Field(ge=1)
    draft: dict[str, Any]


class BacktestRequest(BaseModel):
    # Explicit warehouse snapshot; dataset_id remains a compatibility alias.
    dataset_id: str | None = Field(default=None, max_length=128)
    snapshot_id: str | None = Field(default=None, max_length=128)


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
        "evidence": p.get("evidence", []),
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


# --- backtests (slice 2) ---


def backtest_out(row: Strategy) -> dict:
    from algobots.strategies.evidence import evidence_record

    settings = get_settings()
    published = (Path(settings.evidence_notebook_root) / "evidence" / f"{row.id}.py").is_file()
    return {
        "id": str(row.id),
        **row.params,
        "evidence": evidence_record(str(row.id), row.params, settings.evidence_base_url)
        if published
        else None,
    }


def _attach_backtest(row: Strategy, result: Strategy, artifact_hash: str, digest: str) -> None:
    from algobots.strategies.evidence import publish_notebook

    settings = get_settings()
    try:
        evidence = publish_notebook(
            Path(settings.evidence_notebook_root),
            str(result.id),
            result.params,
            settings.evidence_base_url,
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "Evidence publication failed; retry backtest") from exc
    params = row.params
    refs = params.get("backtests", [])
    if not any(ref["id"] == str(result.id) for ref in refs):
        params["backtests"] = [
            *refs,
            {
                "id": str(result.id),
                "artifact_hash": artifact_hash,
                "dataset_sha256": digest,
            },
        ]
    params["evidence"] = [
        *[e for e in params.get("evidence", []) if e["backtest_row_id"] != str(result.id)],
        evidence,
    ]
    row.params_json = json.dumps(params)


@router.get("/snapshots")
def list_snapshots(instrument_id: str, ctx: AuthContext = Depends(get_auth_context)):
    """Discover published snapshot ids for an exact instrument, behind Studio auth."""
    from algobots.warehouse import Warehouse, WarehouseError

    _tenant(ctx)
    try:
        return {
            "snapshots": Warehouse(Path(get_settings().warehouse_root)).list_snapshots(
                instrument_id
            )
        }
    except WarehouseError as exc:
        raise _invalid(StudioError("snapshot_id", str(exc))) from exc


@router.get("/strategies/{draft_id}/snapshots")
def draft_snapshots(
    draft_id: str, ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)
):
    row = _draft_or_404(db, _tenant(ctx), draft_id)
    artifact = compile_studio_strategy(parse_draft(row.params["draft"]))
    instruments = artifact.nautilus["instrument_ids"]
    return {
        "snapshots": [
            snapshot
            for instrument in instruments
            for snapshot in list_snapshots(instrument, ctx)["snapshots"]
        ]
    }


def run_draft_backtest(
    db: Session, ctx: AuthContext, row: Strategy, dataset_id: str | None
) -> tuple[Strategy, bool]:
    """Backtest the draft's latest artifact; returns (result row, created)."""
    p = row.params
    # The artifact for the current revision: compiling is pure, so a draft
    # edited back to an earlier config maps onto that config's existing row.
    current = compile_studio_strategy(parse_draft(p["draft"])).artifact_hash
    rec = next((a for a in p.get("artifacts", []) if a["artifact_hash"] == current), None)
    if rec is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Draft revision {p['revision']} has no compiled artifact; compile before a backtest",
        )
    s = get_settings()
    if rec.get("implementation") != "condition_dsl.v1":
        bt._check_artifact(rec)
    instruments = rec["nautilus"]["instrument_ids"]
    if len(instruments) != 1:
        raise StudioError("universe.symbols", "choose exactly one snapshot instrument")
    dataset = bt.load_warehouse(dataset_id, Path(s.warehouse_root), instruments[0])
    # The DB primary key enforces this identity across drafts AND racing requests.
    # Tenant identity prevents evidence from leaking across tenant boundaries.
    result_id = uuid5(
        NAMESPACE_URL,
        json.dumps([str(row.tenant_id), rec["artifact_hash"], dataset.id], separators=(",", ":")),
    )
    existing = db.get(Strategy, result_id)
    if existing is not None:
        _attach_backtest(row, existing, rec["artifact_hash"], dataset.sha256)
        return existing, False
    result = bt.run_backtest(rec, dataset)
    out = Strategy(
        id=result_id,
        tenant_id=row.tenant_id,
        user_id=ctx.user.id,
        name=row.name,
        kind=BACKTEST_KIND,
        is_active=False,
        params_json=json.dumps(
            {
                "draft_id": str(row.id),
                "draft_revision": p["revision"],
                "artifact": {
                    "artifact_hash": rec["artifact_hash"],
                    "implementation": rec["implementation"],
                    "compiler_version": rec["compiler_version"],
                    "strategy_id": rec["strategy_id"],
                },
                "dataset": dataset.describe(),
                **result,
                "created_at": datetime.now(UTC).isoformat(),
            }
        ),
    )
    try:
        with db.begin_nested():
            db.add(out)
            db.flush()
    except IntegrityError:
        existing = db.get(Strategy, result_id)
        if existing is None:
            raise
        _attach_backtest(row, existing, rec["artifact_hash"], dataset.sha256)
        return existing, False
    _attach_backtest(row, out, rec["artifact_hash"], dataset.sha256)
    log.info(
        "studio_backtest tenant=%s draft=%s artifact_hash=%s dataset=%s sha256=%s pnl=%s",
        row.tenant_id,
        row.id,
        rec["artifact_hash"],
        dataset.id,
        dataset.sha256,
        result["metrics"]["pnl"],
    )
    return out, True


@router.post("/strategies/{draft_id}/backtest")
def backtest_route(
    draft_id: str,
    response: Response,
    payload: BacktestRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    row = _draft_or_404(db, _tenant(ctx), draft_id)
    try:
        out, created = run_draft_backtest(
            db, ctx, row, (payload.snapshot_id or payload.dataset_id) if payload else None
        )
    except StudioError as exc:
        raise _invalid(exc) from None
    db.commit()
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return backtest_out(out)


@router.get("/strategies/{draft_id}/backtests")
def list_backtests(
    draft_id: str, ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)
):
    """Newest first: the Studio renders the first one."""
    row = _draft_or_404(db, _tenant(ctx), draft_id)
    out = []
    for ref in reversed(row.params.get("backtests", [])):
        r = db.get(Strategy, UUID(ref["id"]))
        if r is not None and r.tenant_id == row.tenant_id and r.kind == BACKTEST_KIND:
            out.append(backtest_out(r))
    return {"backtests": out}
