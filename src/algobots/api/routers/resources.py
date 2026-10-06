"""Tenant-scoped CRUD routes for control-plane resources.

Every query filters by the authenticated user's id; rows owned by another
tenant are indistinguishable from missing rows (404). Referential guards
return 409 when dependent rows would be orphaned.
"""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from algobots.api.accounts.models import AccountCredential
from algobots.api.approvals.service import park_order, parks
from algobots.api.database import get_db
from algobots.api.dependencies import get_current_user
from algobots.api.deployments.models import Deployment
from algobots.api.models import (
    Account,
    AuditLog,
    ClampEvent,
    Decision,
    Order,
    Strategy,
    User,
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


def _owned_or_404(db: Session, model, current_user: User, row_id: UUID):
    row = db.get(model, row_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return row


# --- accounts ---


@router.post("/accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreate,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Account:
    account = Account(user_id=current_user.id, **payload.model_dump())
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
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Account]:
    return list(
        db.scalars(
            select(Account)
            .where(Account.user_id == current_user.id)
            .order_by(Account.created_at.desc())
        )
    )


@router.get("/accounts/{account_id}", response_model=AccountOut)
def get_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Account:
    return _owned_or_404(db, Account, current_user, account_id)


@router.patch("/accounts/{account_id}", response_model=AccountOut)
def update_account(
    account_id: UUID,
    payload: AccountUpdate,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Account:
    account = _owned_or_404(db, Account, current_user, account_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    db.commit()
    _audit(response, "accounts", account.id)
    return account


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: UUID,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    account = _owned_or_404(db, Account, current_user, account_id)
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Strategy:
    strategy = Strategy(
        user_id=current_user.id,
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
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Strategy]:
    return list(
        db.scalars(
            select(Strategy)
            .where(Strategy.user_id == current_user.id)
            .order_by(Strategy.created_at.desc())
        )
    )


@router.get("/strategies/{strategy_id}", response_model=StrategyOut)
def get_strategy(
    strategy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Strategy:
    return _owned_or_404(db, Strategy, current_user, strategy_id)


@router.patch("/strategies/{strategy_id}", response_model=StrategyOut)
def update_strategy(
    strategy_id: UUID,
    payload: StrategyUpdate,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Strategy:
    strategy = _owned_or_404(db, Strategy, current_user, strategy_id)
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    strategy = _owned_or_404(db, Strategy, current_user, strategy_id)
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Order:
    """Record an order; semi_auto accounts park it for human approval (S4.3).

    Parking is the paper-only standing law: a live-bound order on a
    `semi_auto` account never dispatches — it waits in the approval queue,
    and the parked request id is surfaced via the X-Approval-Request-Id
    response header.
    """
    account = _owned_or_404(db, Account, current_user, payload.account_id)
    if payload.deployment_id is not None:
        _owned_or_404(db, Deployment, current_user, payload.deployment_id)
    order = Order(
        user_id=current_user.id,
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
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Order]:
    return list(
        db.scalars(
            select(Order).where(Order.user_id == current_user.id).order_by(Order.created_at.desc())
        )
    )


@router.get("/orders/{order_id}", response_model=OrderOut)
def get_order(
    order_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Order:
    return _owned_or_404(db, Order, current_user, order_id)


@router.patch("/orders/{order_id}", response_model=OrderOut)
def update_order(
    order_id: UUID,
    payload: OrderUpdate,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Order:
    order = _owned_or_404(db, Order, current_user, order_id)
    order.status = payload.status
    db.commit()
    _audit(response, "orders", order.id)
    return order


@router.delete("/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(
    order_id: UUID,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    order = _owned_or_404(db, Order, current_user, order_id)
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Decision:
    _owned_or_404(db, Strategy, current_user, payload.strategy_id)
    if payload.deployment_id is not None:
        _owned_or_404(db, Deployment, current_user, payload.deployment_id)
    decision = Decision(
        user_id=current_user.id,
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
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Decision]:
    return list(
        db.scalars(
            select(Decision)
            .where(Decision.user_id == current_user.id)
            .order_by(Decision.created_at.desc())
        )
    )


# --- clamp events ---


@router.post("/clamp-events", response_model=ClampEventOut, status_code=status.HTTP_201_CREATED)
def create_clamp_event(
    payload: ClampEventCreate,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClampEvent:
    if payload.deployment_id is not None:
        _owned_or_404(db, Deployment, current_user, payload.deployment_id)
    if payload.account_id is not None:
        _owned_or_404(db, Account, current_user, payload.account_id)
    event = ClampEvent(
        user_id=current_user.id,
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
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ClampEvent]:
    return list(
        db.scalars(
            select(ClampEvent)
            .where(ClampEvent.user_id == current_user.id)
            .order_by(ClampEvent.created_at.desc())
        )
    )


# --- audit ---


@router.get("/audit", response_model=list[AuditLogOut])
def list_audit(
    limit: int = 200,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AuditLogOut]:
    rows = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.user_id == current_user.id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(min(limit, 1000))
        )
    )
    out: list[AuditLogOut] = []
    for row in rows:
        data = {column.name: getattr(row, column.name) for column in row.__table__.columns}
        data["detail_json"] = json.loads(row.detail_json or "{}")
        out.append(AuditLogOut(**data))
    return out
