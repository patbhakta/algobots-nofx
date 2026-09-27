"""Tenant-scoped approval queue routes: list/read, decide, expiry, ledger.

Follows the deployments-router discipline: every route filters by the
authenticated user; another tenant's rows are indistinguishable from missing
rows (404). The decide endpoint is the ONLY way a parked order leaves the
queue. Structured events are logged by the service (secret-free).
"""

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from algobots.api.approvals.schemas import (
    ApprovalDecide,
    ApprovalOut,
    BroadcastOut,
    BroadcastReport,
    ExpirySweepOut,
    LedgerOut,
)
from algobots.api.approvals.service import (
    ApprovalError,
    broadcast_for,
    decide_request,
    expire_overdue,
    get_request,
    list_ledger,
    list_requests,
    report_broadcast,
)
from algobots.api.database import get_db
from algobots.api.dependencies import get_current_user
from algobots.api.models import User

logger = logging.getLogger("algobots.api.approvals.router")

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


def _audit(response: Response, resource: str, resource_id: UUID | None) -> None:
    response.headers["X-Audit-Resource"] = resource
    if resource_id is not None:
        response.headers["X-Audit-Resource-Id"] = str(resource_id)


def _owned_or_404(db: Session, current_user: User, request_id: UUID):
    request = get_request(db, current_user, request_id)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval request not found")
    return request


def _out(db: Session, request) -> ApprovalOut:
    out = ApprovalOut.model_validate(request)
    broadcast = broadcast_for(db, request)
    out.broadcast = BroadcastOut.model_validate(broadcast) if broadcast else None
    return out


@router.get("", response_model=list[ApprovalOut])
def list_all(
    status_filter: str | None = Query(default=None, alias="status"),
    order_id: UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ApprovalOut]:
    """The caller's approval requests (optional status / order filters)."""
    return [
        _out(db, request)
        for request in list_requests(db, current_user, status_filter, order_id)
    ]


@router.get("/ledger", response_model=list[LedgerOut])
def ledger(
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LedgerOut]:
    """The caller's append-only action ledger tail (actor, reason, latency)."""
    rows = list_ledger(db, current_user, limit)
    out: list[LedgerOut] = []
    for row in rows:
        data = {column.name: getattr(row, column.name) for column in row.__table__.columns}
        data["detail_json"] = json.loads(row.detail_json or "{}")
        out.append(LedgerOut(**data))
    return out


@router.get("/{request_id}", response_model=ApprovalOut)
def read(
    request_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApprovalOut:
    return _out(db, _owned_or_404(db, current_user, request_id))


@router.post("/{request_id}/decide", response_model=ApprovalOut)
def decide(
    request_id: UUID,
    payload: ApprovalDecide,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApprovalOut:
    """Record the human verdict on a parked request (reason required on reject).

    Persists actor, reason, and park -> decision latency on the request and
    in the append-only action ledger. Illegal transitions are rejected 409.
    """
    request = _owned_or_404(db, current_user, request_id)
    try:
        request = decide_request(
            db, current_user, request, payload.verdict, payload.reason
        )
    except ApprovalError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.message) from None
    _audit(response, "approvals", request.id)
    return _out(db, request)


@router.post("/sweep-expiry", response_model=ExpirySweepOut)
def sweep_expiry(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExpirySweepOut:
    """Expire the caller's overdue parked requests (park -> expired path)."""
    expired = expire_overdue(db, current_user)
    _audit(response, "approvals", None)
    return ExpirySweepOut(expired=len(expired))


@router.post("/{request_id}/broadcast", response_model=BroadcastOut)
def broadcast(
    request_id: UUID,
    payload: BroadcastReport,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BroadcastOut:
    """Report the venue outcome of an approved dispatch (part-sent/part-queued)."""
    request = _owned_or_404(db, current_user, request_id)
    try:
        outcome = report_broadcast(
            db,
            current_user,
            request,
            payload.sent_qty,
            payload.queued_qty,
            payload.reason,
        )
    except ApprovalError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.message) from None
    _audit(response, "approvals", request.id)
    return BroadcastOut.model_validate(outcome)
