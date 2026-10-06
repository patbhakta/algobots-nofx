"""Tenant-scoped deployment routes: create/read/list, breakers, risk reports.

Follows the accounts-router discipline: every route filters by the
authenticated user; another tenant's rows are indistinguishable from missing
rows (404). Structured events are logged by the service (secret-free).
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from algobots.api.database import get_db
from algobots.api.dependencies import get_current_user
from algobots.api.deployments.schemas import (
    DailyLossReport,
    DailyLossReportOut,
    DeploymentCreate,
    DeploymentOut,
    DeploymentUpdate,
    FleetBreakerAction,
    FleetBreakerOut,
)
from algobots.api.deployments.service import (
    DeploymentError,
    create_deployment,
    deployment_out,
    effective_state,
    get_deployment,
    get_fleet_breaker,
    list_deployments,
    report_daily_loss,
    reset_deployment_breaker,
    set_fleet_breaker,
)
from algobots.api.models import User

logger = logging.getLogger("algobots.api.deployments.router")

router = APIRouter(prefix="/api/deployments", tags=["deployments"])


def _audit(response: Response, resource: str, resource_id: UUID | None) -> None:
    response.headers["X-Audit-Resource"] = resource
    if resource_id is not None:
        response.headers["X-Audit-Resource-Id"] = str(resource_id)


def _owned_or_404(db: Session, current_user: User, deployment_id: UUID):
    deployment = get_deployment(db, current_user, deployment_id)
    if deployment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deployment not found")
    return deployment


def _out(db: Session, current_user: User, deployment) -> DeploymentOut:
    return deployment_out(deployment, get_fleet_breaker(db, current_user))


@router.post("", response_model=DeploymentOut, status_code=status.HTTP_201_CREATED)
def create(
    payload: DeploymentCreate,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeploymentOut:
    """Deploy (strategy x symbol x account); spec + envelope frozen at create."""
    try:
        deployment = create_deployment(db, current_user, payload)
    except DeploymentError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    _audit(response, "deployments", deployment.id)
    return _out(db, current_user, deployment)


@router.get("", response_model=list[DeploymentOut])
def list_all(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[DeploymentOut]:
    return [_out(db, current_user, dep) for dep in list_deployments(db, current_user)]


@router.get("/{deployment_id}", response_model=DeploymentOut)
def read(
    deployment_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeploymentOut:
    return _out(db, current_user, _owned_or_404(db, current_user, deployment_id))


@router.patch("/{deployment_id}", response_model=DeploymentOut)
def update_status(
    deployment_id: UUID,
    payload: DeploymentUpdate,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeploymentOut:
    """Change user intent (running | paused | stopped); breakers are separate."""
    deployment = _owned_or_404(db, current_user, deployment_id)
    deployment.status = payload.status
    db.commit()
    _audit(response, "deployments", deployment.id)
    return _out(db, current_user, deployment)


@router.delete("/{deployment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    deployment_id: UUID,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    deployment = _owned_or_404(db, current_user, deployment_id)
    db.delete(deployment)
    db.commit()
    _audit(response, "deployments", deployment.id)


@router.post("/{deployment_id}/risk/daily-loss", response_model=DailyLossReportOut)
def daily_loss(
    deployment_id: UUID,
    payload: DailyLossReport,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailyLossReportOut:
    """Report signed daily P&L; a breach of the frozen cap trips the breaker."""
    deployment = _owned_or_404(db, current_user, deployment_id)
    fleet = get_fleet_breaker(db, current_user)
    deployment, tripped = report_daily_loss(db, deployment, payload.daily_pnl, fleet=fleet)
    _audit(response, "deployments", deployment.id)
    state, _halt_source = effective_state(deployment, fleet)
    return DailyLossReportOut(
        deployment_id=deployment.id,
        daily_pnl=payload.daily_pnl,
        max_daily_loss=deployment.max_daily_loss,
        tripped=tripped,
        breaker_state=deployment.breaker_state,
        effective_state=state,
    )


@router.post("/{deployment_id}/breaker/reset", response_model=DeploymentOut)
def breaker_reset(
    deployment_id: UUID,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeploymentOut:
    """Close this deployment's breaker (fleet breaker is untouched)."""
    deployment = _owned_or_404(db, current_user, deployment_id)
    reset_deployment_breaker(db, deployment)
    _audit(response, "deployments", deployment.id)
    return _out(db, current_user, deployment)


@router.get("/fleet/breaker", response_model=FleetBreakerOut)
def fleet_breaker_state(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> FleetBreakerOut:
    """The caller's fleet breaker (closed by default)."""
    return FleetBreakerOut.model_validate(get_fleet_breaker(db, current_user))


@router.post("/fleet/breaker", response_model=FleetBreakerOut)
def fleet_breaker_act(
    payload: FleetBreakerAction,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FleetBreakerOut:
    """Trip (halts every deployment in scope) or reset the fleet breaker."""
    fleet, _affected = set_fleet_breaker(db, current_user, payload.action, payload.reason)
    _audit(response, "deployments", None)
    return FleetBreakerOut.model_validate(fleet)
