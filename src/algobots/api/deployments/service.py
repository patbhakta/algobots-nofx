"""Deployment service: freeze-at-deploy, duplicate guard, breakers (S4.2).

Freeze contract: at deploy time the strategy's name/kind/DSL spec and its
artifact hash (sha256 of the canonical spec) are copied into the deployment
row. Strategy edits afterwards never propagate — a running deployment reads
only its frozen snapshot (A11 case 2).

Duplicate guard: at most one ACTIVE deployment per (strategy x symbol x
account); a conflicting create returns 409 (A11 case 4). Stopped deployments
free the tuple.

Breakers: a daily-loss breach against the FROZEN envelope opens that
deployment's breaker only. The fleet breaker (one per user) halts every
deployment in the caller's scope; resetting it resumes exactly the
fleet-halted ones.

Logging discipline: structured, secret-free events (`deployment_created`,
`deployment_breaker_tripped`, ...) — ids, symbols, hashes, and money caps
only. Deployments never copy account credentials or secrets.
"""

import json
import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from algobots.api.deployments.models import (
    BreakerState,
    Deployment,
    DeploymentStatus,
    FleetBreaker,
)
from algobots.api.deployments.schemas import DeploymentCreate, DeploymentOut
from algobots.api.models import Account, Strategy, User
from algobots.risk.envelopes import RiskEnvelope
from algobots.strategies.dsl import (
    SPEC_KIND,
    SpecError,
    StrategySpec,
    artifact_hash,
    canonical_json,
    validate_spec,
)

logger = logging.getLogger("algobots.api.deployments.service")

HALTED = "halted"


# --- effective state -----------------------------------------------------------


def effective_state(deployment: Deployment, fleet: FleetBreaker | None) -> tuple[str, str | None]:
    """Fold status + deployment breaker + fleet breaker -> (state, halt_source)."""
    if deployment.breaker_state == BreakerState.OPEN.value:
        return HALTED, "deployment_breaker"
    if fleet is not None and fleet.state == BreakerState.OPEN.value:
        return HALTED, "fleet_breaker"
    return deployment.status, None


def deployment_out(deployment: Deployment, fleet: FleetBreaker | None) -> DeploymentOut:
    """Serialize one deployment with its effective state."""
    state, halt_source = effective_state(deployment, fleet)
    return DeploymentOut(
        id=deployment.id,
        strategy_id=deployment.strategy_id,
        account_id=deployment.account_id,
        symbol=deployment.symbol,
        status=deployment.status,
        frozen_spec=json.loads(deployment.frozen_spec_json or "{}"),
        artifact_hash=deployment.artifact_hash,
        max_order_value=Decimal(deployment.max_order_value),
        max_daily_loss=Decimal(deployment.max_daily_loss),
        breaker_state=deployment.breaker_state,
        breaker_reason=deployment.breaker_reason or "",
        tripped_at=deployment.tripped_at,
        effective_state=state,
        halt_source=halt_source,
        created_at=deployment.created_at,
        updated_at=deployment.updated_at,
    )


# --- create / read / list --------------------------------------------------------


class DeploymentError(Exception):
    """Domain failure with an HTTP status and a clear, user-facing message."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def create_deployment(db: Session, user: User, payload: DeploymentCreate) -> Deployment:
    """Validate + freeze + dedupe-guard one deployment create."""
    strategy = db.get(Strategy, payload.strategy_id)
    if strategy is None or strategy.user_id != user.id:
        raise DeploymentError(404, "Strategy not found")
    account = db.get(Account, payload.account_id)
    if account is None or account.user_id != user.id:
        raise DeploymentError(404, "Account not found")
    if strategy.kind != SPEC_KIND:
        raise DeploymentError(
            422, f"Strategy kind must be '{SPEC_KIND}' to deploy (got '{strategy.kind}')"
        )
    try:
        spec = validate_spec(json.loads(strategy.params_json or "{}"))
    except (json.JSONDecodeError, SpecError) as exc:
        raise DeploymentError(422, f"Strategy spec invalid: {exc}") from None

    symbol = payload.symbol.upper()
    conflict = db.scalar(
        select(Deployment.id).where(
            Deployment.strategy_id == strategy.id,
            Deployment.symbol == symbol,
            Deployment.account_id == account.id,
            Deployment.status != DeploymentStatus.STOPPED.value,
        )
    )
    if conflict is not None:
        raise DeploymentError(
            409,
            "Deployment already exists for this strategy, symbol, and account "
            f"({strategy.name} x {symbol}); stop it before deploying again",
        )

    frozen = {
        "name": strategy.name,
        "kind": strategy.kind,
        "spec": spec.model_dump(mode="json"),
    }
    deployment = Deployment(
        user_id=user.id,
        strategy_id=strategy.id,
        account_id=account.id,
        symbol=symbol,
        status=DeploymentStatus.RUNNING.value,
        frozen_spec_json=json.dumps(frozen, sort_keys=True, separators=(",", ":")),
        artifact_hash=artifact_hash(spec),
        max_order_value=str(payload.max_order_value),
        max_daily_loss=str(payload.max_daily_loss),
    )
    db.add(deployment)
    db.commit()
    logger.info(
        "deployment_created deployment_id=%s strategy_id=%s account_id=%s symbol=%s "
        "artifact_hash=%s max_order_value=%s max_daily_loss=%s",
        deployment.id,
        strategy.id,
        account.id,
        symbol,
        deployment.artifact_hash,
        deployment.max_order_value,
        deployment.max_daily_loss,
    )
    return deployment


def get_deployment(db: Session, user: User, deployment_id) -> Deployment | None:
    """Fetch one deployment owned by the user, else None."""
    from uuid import UUID

    if not isinstance(deployment_id, UUID):
        return None
    deployment = db.get(Deployment, deployment_id)
    if deployment is None or deployment.user_id != user.id:
        return None
    return deployment


def list_deployments(db: Session, user: User) -> list[Deployment]:
    """All the caller's deployments, newest first."""
    return list(
        db.scalars(
            select(Deployment)
            .where(Deployment.user_id == user.id)
            .order_by(Deployment.created_at.desc())
        )
    )


def frozen_strategy_spec(deployment: Deployment) -> StrategySpec:
    """Re-validate the frozen snapshot (deployments evaluate only this copy)."""
    return validate_spec(deployment.frozen_spec["spec"])


def frozen_canonical_spec(deployment: Deployment) -> str:
    """Canonical JSON of the frozen DSL spec (hash input, for drift checks)."""
    return canonical_json(frozen_strategy_spec(deployment))


# --- per-deployment breaker ------------------------------------------------------


def report_daily_loss(
    db: Session, deployment: Deployment, daily_pnl: Decimal, *, fleet: FleetBreaker | None = None
) -> tuple[Deployment, bool]:
    """Check signed P&L against the FROZEN envelope; trip the breaker on breach.

    Loss >= cap trips deterministically (conservative on money rails); exits
    are never blocked by this module — that law lives in the risk package.
    """
    envelope = RiskEnvelope(
        max_order_value=Decimal(deployment.max_order_value),
        max_daily_loss=Decimal(deployment.max_daily_loss),
    )
    check = envelope.check_daily_loss(daily_pnl)
    if check.tripped and deployment.breaker_state != BreakerState.OPEN.value:
        deployment.breaker_state = BreakerState.OPEN.value
        deployment.breaker_reason = (
            f"daily loss {check.daily_pnl} reached frozen cap {check.max_daily_loss}"
        )
        deployment.tripped_at = datetime.now(UTC)
        db.commit()
        logger.info(
            "deployment_breaker_tripped deployment_id=%s daily_pnl=%s max_daily_loss=%s",
            deployment.id,
            check.daily_pnl,
            check.max_daily_loss,
        )
    return deployment, check.tripped


def reset_deployment_breaker(db: Session, deployment: Deployment) -> Deployment:
    """Close one deployment's breaker (fleet state is untouched)."""
    deployment.breaker_state = BreakerState.CLOSED.value
    deployment.breaker_reason = ""
    deployment.tripped_at = None
    db.commit()
    logger.info("deployment_breaker_reset deployment_id=%s", deployment.id)
    return deployment


# --- fleet breaker ----------------------------------------------------------------


def get_fleet_breaker(db: Session, user: User) -> FleetBreaker:
    """The caller's fleet breaker row (never None; default closed, untrip state)."""
    row = db.scalar(select(FleetBreaker).where(FleetBreaker.user_id == user.id))
    if row is None:
        row = FleetBreaker(user_id=user.id)
        db.add(row)
        db.commit()
    return row


def set_fleet_breaker(
    db: Session, user: User, action: str, reason: str = ""
) -> tuple[FleetBreaker, list[Deployment]]:
    """Trip or reset the caller's fleet breaker; returns affected deployments."""
    fleet = get_fleet_breaker(db, user)
    if action == "trip":
        fleet.state = BreakerState.OPEN.value
        fleet.reason = reason or "manual fleet breaker trip"
        fleet.tripped_at = datetime.now(UTC)
        db.commit()
        halted = list_deployments(db, user)
        logger.info(
            "fleet_breaker_tripped user_id=%s halted_deployments=%d reason=%s",
            user.id,
            len(halted),
            fleet.reason,
        )
        return fleet, halted

    fleet.state = BreakerState.CLOSED.value
    fleet.reason = ""
    fleet.tripped_at = None
    db.commit()
    resumed = list(
        db.scalars(
            select(Deployment).where(
                Deployment.user_id == user.id,
                Deployment.breaker_state == BreakerState.CLOSED.value,
                Deployment.status != DeploymentStatus.STOPPED.value,
            )
        )
    )
    logger.info(
        "fleet_breaker_reset user_id=%s resumed_deployments=%d",
        user.id,
        len(resumed),
    )
    return fleet, resumed
