"""Deployment service: freeze-at-deploy, duplicate guard, breakers (S4.2).

Freeze contract: at deploy time the strategy's name/kind/DSL spec and its
artifact hash (sha256 of the canonical spec) are copied into the deployment
row. Strategy edits afterwards never propagate — a running deployment reads
only its frozen snapshot (A11 case 2).

Duplicate guard: at most one ACTIVE deployment per (strategy x symbol x
account); a conflicting create returns 409 (A11 case 4). Stopped deployments
free the tuple.

Breakers: a daily-loss breach against the FROZEN envelope opens that
deployment's breaker only. The fleet breaker (one row per tenant x user,
ALG-3186) halts every deployment in that (tenant, user) scope; resetting it
resumes exactly the fleet-halted ones in the SAME tenant — a reset under
tenant A never resumes tenant B.

Logging discipline: structured, secret-free events (`deployment_created`,
`deployment_breaker_tripped`, ...) — ids, symbols, hashes, and money caps
only. Deployments never copy account credentials or secrets.
"""

import hashlib
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from algobots.api.deployments.evidence import EvidenceRequired, studio_evidence
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
    try:
        evidence = studio_evidence(db, strategy)
    except EvidenceRequired as exc:
        raise DeploymentError(422, str(exc)) from None
    # ARTIFACT_KIND mirrors algobots.api.routers.studio.ARTIFACT_KIND (kept
    # local so the service never imports a router).
    artifact_kind = "studio-artifact"
    if strategy.kind == SPEC_KIND:
        try:
            spec = validate_spec(json.loads(strategy.params_json or "{}"))
        except (json.JSONDecodeError, SpecError) as exc:
            raise DeploymentError(422, f"Strategy spec invalid: {exc}") from None
        frozen = {
            "name": strategy.name,
            "kind": strategy.kind,
            "spec": spec.model_dump(mode="json"),
        }
        digest = artifact_hash(spec)
    elif strategy.kind == artifact_kind:
        # ALG-3423: NoFX-authored demo artifacts (kalshi_momentum.v1) deploy
        # ONLY behind the evidence gate — studio_evidence resolved above, so a
        # None here means the draft had no published evidence to resolve.
        if evidence is None:
            raise DeploymentError(
                422, "Studio artifacts deploy only with published marimo evidence"
            )
        params = json.loads(strategy.params_json or "{}")
        frozen = {"name": strategy.name, "kind": strategy.kind, "artifact": params}
        digest = params.get("artifact_hash") or hashlib.sha256(
            json.dumps(params, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    else:
        raise DeploymentError(
            422,
            f"Strategy kind must be '{SPEC_KIND}' or '{artifact_kind}' to deploy "
            f"(got '{strategy.kind}')",
        )

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

    if evidence is not None:
        frozen["studio_evidence"] = evidence
    deployment = Deployment(
        user_id=user.id,
        strategy_id=strategy.id,
        account_id=account.id,
        symbol=symbol,
        status=DeploymentStatus.RUNNING.value,
        frozen_spec_json=json.dumps(frozen, sort_keys=True, separators=(",", ":")),
        artifact_hash=digest,
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


def get_fleet_breaker(db: Session, user: User, tenant_id) -> FleetBreaker:
    """The caller's fleet breaker row in the ACTIVE tenant (never None;
    default closed, untrip state). One row per (tenant, user) (ALG-3186)."""
    row = db.scalar(
        select(FleetBreaker).where(
            FleetBreaker.tenant_id == tenant_id,
            FleetBreaker.user_id == user.id,
        )
    )
    if row is None:
        row = FleetBreaker(tenant_id=tenant_id, user_id=user.id)
        db.add(row)
        db.commit()
    return row


def fleet_breaker_for_deployment(db: Session, deployment: Deployment) -> FleetBreaker | None:
    """The breaker row that GOVERNS this deployment: its account's tenant and
    the deployment's user — never the caller's active tenant, so a halt in
    tenant A stays visible (and real) from any session."""
    account = db.get(Account, deployment.account_id)
    if account is None:
        return None
    return db.scalar(
        select(FleetBreaker).where(
            FleetBreaker.tenant_id == account.tenant_id,
            FleetBreaker.user_id == deployment.user_id,
        )
    )


def _deployments_in_tenant(db: Session, user: User, tenant_id) -> list[Deployment]:
    """The user's deployments whose account belongs to this tenant."""
    return list(
        db.scalars(
            select(Deployment)
            .join(Account, Account.id == Deployment.account_id)
            .where(Deployment.user_id == user.id, Account.tenant_id == tenant_id)
        )
    )


def set_fleet_breaker(
    db: Session, user: User, tenant_id, action: str, reason: str = ""
) -> tuple[FleetBreaker, list[Deployment]]:
    """Trip or reset the caller's fleet breaker in the ACTIVE tenant; returns
    the affected deployments — the user's deployments in THAT tenant only, so
    a reset under tenant A never resumes tenant B."""
    fleet = get_fleet_breaker(db, user, tenant_id)
    if action == "trip":
        fleet.state = BreakerState.OPEN.value
        fleet.reason = reason or "manual fleet breaker trip"
        fleet.tripped_at = datetime.now(UTC)
        db.commit()
        halted = _deployments_in_tenant(db, user, tenant_id)
        logger.info(
            "fleet_breaker_tripped tenant_id=%s user_id=%s halted_deployments=%d reason=%s",
            tenant_id,
            user.id,
            len(halted),
            fleet.reason,
        )
        return fleet, halted

    fleet.state = BreakerState.CLOSED.value
    fleet.reason = ""
    fleet.tripped_at = None
    db.commit()
    resumed = [
        dep
        for dep in _deployments_in_tenant(db, user, tenant_id)
        if dep.breaker_state == BreakerState.CLOSED.value
        and dep.status != DeploymentStatus.STOPPED.value
    ]
    logger.info(
        "fleet_breaker_reset tenant_id=%s user_id=%s resumed_deployments=%d",
        tenant_id,
        user.id,
        len(resumed),
    )
    return fleet, resumed
