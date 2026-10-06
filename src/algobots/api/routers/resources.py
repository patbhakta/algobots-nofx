"""Tenant-scoped CRUD routes for control-plane resources.

Every query filters by the active tenant from the authenticated session (A03);
rows owned by another tenant are indistinguishable from missing rows (404).
Reads need `tenant.read`, mutations and commands need `resource.write`, so a
viewer is refused (and the refusal audited) before any row is touched. Lists
accept `limit` + an opaque tenant-bound `cursor` (`X-Next-Cursor`). Referential
guards return 409 when dependent rows would be orphaned.
"""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from algobots.api.accounts.models import AccountCredential
from algobots.api.approvals.service import park_order, parks
from algobots.api.auth.cursor import paginate
from algobots.api.auth.policy import Action, is_allowed
from algobots.api.database import get_db
from algobots.api.dependencies import TenantContext, require
from algobots.api.deployments.models import Deployment
from algobots.api.models import (
    Account,
    AuditLog,
    ClampEvent,
    Decision,
    Order,
    Strategy,
)
from algobots.api.schemas import (
    AccountCreate,
    AccountOut,
    AccountUpdate,
    AuditLogOut,
    ClampEventCreate,
    ClampEventOut,
    DecisionCreate,
    DecisionOut,
    OrderCreate,
    OrderOut,
    OrderUpdate,
    StrategyCreate,
    StrategyOut,
    StrategyUpdate,
    params_to_json,
)

router = APIRouter(prefix="/api", tags=["resources"])


def _audit(response: Response, resource: str, resource_id: UUID | None) -> None:
    response.headers["X-Audit-Resource"] = resource
    if resource_id is not None:
        response.headers["X-Audit-Resource-Id"] = str(resource_id)


def _owned_or_404(db: Session, model, ctx: TenantContext, row_id: UUID):
    row = db.get(model, row_id)
    # Tables outside the A03 schema change (e.g. deployments) are still
    # user-scoped; tenant-owned tables match on the active tenant.
    owned = (
        row is not None
        and (
            row.tenant_id == ctx.tenant_id
            if hasattr(row, "tenant_id")
            else row.user_id == ctx.user.id
        )
    )
    if not owned:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return row


# --- accounts ---


@router.post("/accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreate,
    response: Response,
    ctx: TenantContext = Depends(require(Action.RESOURCE_WRITE)),
    db: Session = Depends(get_db),
) -> Account:
    account = Account(tenant_id=ctx.tenant_id,
        user_id=ctx.user.id, **payload.model_dump())
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        # UNIQUE(user_id, label) from migration 0002 — one registry label per user.
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Account label already in use for this user",
        ) from None
    _audit(response, "accounts", account.id)
    return account


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(
    response: Response,
    cursor: str | None = None,
    limit: int | None = None,
    ctx: TenantContext = Depends(require(Action.TENANT_READ)),
    db: Session = Depends(get_db),
) -> list[Account]:
    query = select(Account).where(Account.tenant_id == ctx.tenant_id)
    return paginate(
        db, query, Account, tenant_id=ctx.tenant_id, cursor=cursor, limit=limit,
        response=response,
    )


@router.get("/accounts/{account_id}", response_model=AccountOut)
def get_account(
    account_id: UUID,
    ctx: TenantContext = Depends(require(Action.TENANT_READ)),
    db: Session = Depends(get_db),
) -> Account:
    return _owned_or_404(db, Account, ctx, account_id)


@router.patch("/accounts/{account_id}", response_model=AccountOut)
def update_account(
    account_id: UUID,
    payload: AccountUpdate,
    response: Response,
    ctx: TenantContext = Depends(require(Action.RESOURCE_WRITE)),
    db: Session = Depends(get_db),
) -> Account:
    account = _owned_or_404(db, Account, ctx, account_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    db.commit()
    _audit(response, "accounts", account.id)
    return account


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: UUID,
    response: Response,
    ctx: TenantContext = Depends(require(Action.RESOURCE_WRITE)),
    db: Session = Depends(get_db),
) -> None:
    account = _owned_or_404(db, Account, ctx, account_id)
    has_dependents = (
        db.scalar(select(Deployment.id).where(Deployment.account_id == account.id).limit(1))
        is not None
        or db.scalar(select(Order.id).where(Order.account_id == account.id).limit(1)) is not None
        or db.scalar(select(ClampEvent.id).where(ClampEvent.account_id == account.id).limit(1))
        is not None
    )
    if has_dependents:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Account has deployments, orders, or clamp events; close them first",
        )
    # SQLite does not enforce FK cascades by default; drop credentials
    # explicitly so sealed secrets never outlive their account.
    credential = db.scalar(
        select(AccountCredential).where(AccountCredential.account_id == account.id)
    )
    if credential is not None:
        db.delete(credential)
    db.delete(account)
    db.commit()
    _audit(response, "accounts", account.id)


# --- strategies ---


@router.post("/strategies", response_model=StrategyOut, status_code=status.HTTP_201_CREATED)
def create_strategy(
    payload: StrategyCreate,
    response: Response,
    ctx: TenantContext = Depends(require(Action.RESOURCE_WRITE)),
    db: Session = Depends(get_db),
) -> Strategy:
    strategy = Strategy(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user.id,
        name=payload.name,
        kind=payload.kind,
        params_json=params_to_json(payload.params),
        is_active=payload.is_active,
    )
    db.add(strategy)
    db.commit()
    _audit(response, "strategies", strategy.id)
    return strategy


@router.get("/strategies", response_model=list[StrategyOut])
def list_strategies(
    response: Response,
    cursor: str | None = None,
    limit: int | None = None,
    ctx: TenantContext = Depends(require(Action.TENANT_READ)),
    db: Session = Depends(get_db),
) -> list[Strategy]:
    query = select(Strategy).where(Strategy.tenant_id == ctx.tenant_id)
    return paginate(
        db, query, Strategy, tenant_id=ctx.tenant_id, cursor=cursor, limit=limit,
        response=response,
    )


@router.get("/strategies/{strategy_id}", response_model=StrategyOut)
def get_strategy(
    strategy_id: UUID,
    ctx: TenantContext = Depends(require(Action.TENANT_READ)),
    db: Session = Depends(get_db),
) -> Strategy:
    return _owned_or_404(db, Strategy, ctx, strategy_id)


@router.patch("/strategies/{strategy_id}", response_model=StrategyOut)
def update_strategy(
    strategy_id: UUID,
    payload: StrategyUpdate,
    response: Response,
    ctx: TenantContext = Depends(require(Action.RESOURCE_WRITE)),
    db: Session = Depends(get_db),
) -> Strategy:
    strategy = _owned_or_404(db, Strategy, ctx, strategy_id)
    data = payload.model_dump(exclude_unset=True)
    if "params" in data:
        strategy.params_json = params_to_json(data.pop("params"))
    for field, value in data.items():
        setattr(strategy, field, value)
    db.commit()
    _audit(response, "strategies", strategy.id)
    return strategy


@router.delete("/strategies/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_strategy(
    strategy_id: UUID,
    response: Response,
    ctx: TenantContext = Depends(require(Action.RESOURCE_WRITE)),
    db: Session = Depends(get_db),
) -> None:
    strategy = _owned_or_404(db, Strategy, ctx, strategy_id)
    has_dependents = (
        db.scalar(select(Deployment.id).where(Deployment.strategy_id == strategy.id).limit(1))
        is not None
        or db.scalar(select(Decision.id).where(Decision.strategy_id == strategy.id).limit(1))
        is not None
    )
    if has_dependents:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Strategy has deployments or decisions; remove them first",
        )
    db.delete(strategy)
    db.commit()
    _audit(response, "strategies", strategy.id)


# --- orders ---


@router.post("/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    response: Response,
    ctx: TenantContext = Depends(require(Action.RESOURCE_WRITE)),
    db: Session = Depends(get_db),
) -> Order:
    """Record an order; semi_auto accounts park it for human approval (S4.3).

    Parking is the paper-only standing law: a live-bound order on a
    `semi_auto` account never dispatches — it waits in the approval queue,
    and the parked request id is surfaced via the X-Approval-Request-Id
    response header.
    """
    account = _owned_or_404(db, Account, ctx, payload.account_id)
    if payload.deployment_id is not None:
        _owned_or_404(db, Deployment, ctx, payload.deployment_id)
    order = Order(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user.id,
        account_id=payload.account_id,
        deployment_id=payload.deployment_id,
        symbol=payload.symbol.upper(),
        side=payload.side.value,
        order_type=payload.order_type,
        qty=payload.qty,
        limit_price=payload.limit_price,
        status="parked" if parks(account) else "pending",
    )
    db.add(order)
    db.commit()
    if parks(account):
        request = park_order(db, order)
        response.headers["X-Approval-Request-Id"] = str(request.id)
    _audit(response, "orders", order.id)
    return order


@router.get("/orders", response_model=list[OrderOut])
def list_orders(
    response: Response,
    cursor: str | None = None,
    limit: int | None = None,
    ctx: TenantContext = Depends(require(Action.TENANT_READ)),
    db: Session = Depends(get_db),
) -> list[Order]:
    query = select(Order).where(Order.tenant_id == ctx.tenant_id)
    return paginate(
        db, query, Order, tenant_id=ctx.tenant_id, cursor=cursor, limit=limit,
        response=response,
    )


@router.get("/orders/{order_id}", response_model=OrderOut)
def get_order(
    order_id: UUID,
    ctx: TenantContext = Depends(require(Action.TENANT_READ)),
    db: Session = Depends(get_db),
) -> Order:
    return _owned_or_404(db, Order, ctx, order_id)


@router.patch("/orders/{order_id}", response_model=OrderOut)
def update_order(
    order_id: UUID,
    payload: OrderUpdate,
    response: Response,
    ctx: TenantContext = Depends(require(Action.RESOURCE_WRITE)),
    db: Session = Depends(get_db),
) -> Order:
    order = _owned_or_404(db, Order, ctx, order_id)
    order.status = payload.status
    db.commit()
    _audit(response, "orders", order.id)
    return order


@router.delete("/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(
    order_id: UUID,
    response: Response,
    ctx: TenantContext = Depends(require(Action.RESOURCE_WRITE)),
    db: Session = Depends(get_db),
) -> None:
    order = _owned_or_404(db, Order, ctx, order_id)
    if order.status not in {"pending", "cancelled", "rejected"}:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Cannot delete order in status '{order.status}'"
        )
    db.delete(order)
    db.commit()
    _audit(response, "orders", order.id)


# --- decisions ---


@router.post("/decisions", response_model=DecisionOut, status_code=status.HTTP_201_CREATED)
def create_decision(
    payload: DecisionCreate,
    response: Response,
    ctx: TenantContext = Depends(require(Action.RESOURCE_WRITE)),
    db: Session = Depends(get_db),
) -> Decision:
    _owned_or_404(db, Strategy, ctx, payload.strategy_id)
    if payload.deployment_id is not None:
        _owned_or_404(db, Deployment, ctx, payload.deployment_id)
    decision = Decision(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user.id,
        strategy_id=payload.strategy_id,
        deployment_id=payload.deployment_id,
        symbol=payload.symbol.upper(),
        action=payload.action,
        confidence=payload.confidence,
        rationale=payload.rationale,
    )
    db.add(decision)
    db.commit()
    _audit(response, "decisions", decision.id)
    return decision


@router.get("/decisions", response_model=list[DecisionOut])
def list_decisions(
    response: Response,
    cursor: str | None = None,
    limit: int | None = None,
    ctx: TenantContext = Depends(require(Action.TENANT_READ)),
    db: Session = Depends(get_db),
) -> list[Decision]:
    query = select(Decision).where(Decision.tenant_id == ctx.tenant_id)
    return paginate(
        db, query, Decision, tenant_id=ctx.tenant_id, cursor=cursor, limit=limit,
        response=response,
    )


# --- clamp events ---


@router.post("/clamp-events", response_model=ClampEventOut, status_code=status.HTTP_201_CREATED)
def create_clamp_event(
    payload: ClampEventCreate,
    response: Response,
    ctx: TenantContext = Depends(require(Action.RESOURCE_WRITE)),
    db: Session = Depends(get_db),
) -> ClampEvent:
    if payload.deployment_id is not None:
        _owned_or_404(db, Deployment, ctx, payload.deployment_id)
    if payload.account_id is not None:
        _owned_or_404(db, Account, ctx, payload.account_id)
    event = ClampEvent(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user.id,
        deployment_id=payload.deployment_id,
        account_id=payload.account_id,
        clamp_kind=payload.clamp_kind,
        old_value=payload.old_value,
        new_value=payload.new_value,
        reason=payload.reason,
    )
    db.add(event)
    db.commit()
    _audit(response, "clamp_events", event.id)
    return event


@router.get("/clamp-events", response_model=list[ClampEventOut])
def list_clamp_events(
    response: Response,
    cursor: str | None = None,
    limit: int | None = None,
    ctx: TenantContext = Depends(require(Action.TENANT_READ)),
    db: Session = Depends(get_db),
) -> list[ClampEvent]:
    query = select(ClampEvent).where(ClampEvent.tenant_id == ctx.tenant_id)
    return paginate(
        db, query, ClampEvent, tenant_id=ctx.tenant_id, cursor=cursor, limit=limit,
        response=response,
    )


# --- export ---


@router.get("/export")
def export_tenant(
    response: Response,
    ctx: TenantContext = Depends(require(Action.TENANT_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """Snapshot of the active tenant's rows. Credentials are never exported."""

    def rows(model, schema) -> list[dict]:
        found = db.scalars(
            select(model).where(model.tenant_id == ctx.tenant_id).order_by(model.created_at)
        )
        return [schema.model_validate(row).model_dump(mode="json") for row in found]

    response.headers["Cache-Control"] = "no-store"
    return {
        "tenant_id": str(ctx.tenant_id),
        "accounts": rows(Account, AccountOut),
        "strategies": rows(Strategy, StrategyOut),
        "orders": rows(Order, OrderOut),
        "decisions": rows(Decision, DecisionOut),
        "clamp_events": rows(ClampEvent, ClampEventOut),
    }


# --- audit ---


@router.get("/audit", response_model=list[AuditLogOut])
def list_audit(
    limit: int = 200,
    ctx: TenantContext = Depends(require(Action.TENANT_READ)),
    db: Session = Depends(get_db),
) -> list[AuditLogOut]:
    query = select(AuditLog).where(AuditLog.tenant_id == ctx.tenant_id)
    if not is_allowed(ctx.role, Action.AUDIT_READ_ALL):
        query = query.where(AuditLog.user_id == ctx.user.id)
    rows = list(
        db.scalars(
            query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(min(limit, 1000))
        )
    )
    out: list[AuditLogOut] = []
    for row in rows:
        data = {column.name: getattr(row, column.name) for column in row.__table__.columns}
        data["detail_json"] = json.loads(row.detail_json or "{}")
        out.append(AuditLogOut(**data))
    return out
