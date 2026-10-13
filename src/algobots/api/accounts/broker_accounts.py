"""A04 routes: broker-account onboarding, capability previews, secret grants.

- ``/api/broker-accounts`` — onboard against the mock provider or a candidate
  real provider (configuration-only), with duplicate external accounts
  rejected by a generic 409 that never names the owning tenant.
- ``/api/broker-accounts/capabilities`` and ``/preview`` — the
  per-(provider, environment) capability registry, default-deny.
- ``/api/account-grants`` — SecretResolver grants: assign the single
  execution identity that may resolve an account's secret, rotate in place,
  revoke with a reconciliation freeze.

Responses never contain credential material: grant views carry references,
states and versions only.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from algobots.api.accounts.models import BrokerConnection, ExternalAccountIdentity
from algobots.api.accounts.onboarding import (
    DuplicateExternalAccountError,
    OnboardingRejected,
    onboard_broker_account,
)
from algobots.api.accounts.providers import UnknownProviderError, capabilities_for
from algobots.api.accounts.schemas import CredentialSet
from algobots.api.auth.policy import Action
from algobots.api.database import get_db
from algobots.api.dependencies import TenantContext, get_current_user, require
from algobots.api.models import Account, User
from algobots.secrets.models import SecretGrant
from algobots.secrets.service import ResolutionDenied, SecretStore

router = APIRouter(prefix="/api", tags=["broker-accounts"])

_ENVIRONMENTS = ("development", "synthetic-paper", "paper", "live")


class OnboardRequest(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=32, pattern=r"^[a-z0-9][a-z0-9-]*$")
    environment: str
    external_account_id: str = Field(min_length=1, max_length=128)
    base_currency: str = Field(default="USD", pattern=r"^[A-Z0-9]{3,10}$")
    # A04 onboards paper-mode accounts only; live mode is a later, separately
    # authorized activation (the environment guard blocks live environments,
    # this keeps the account row itself paper).
    mode: str = Field(default="paper", pattern=r"^paper$")
    credentials: CredentialSet

    @field_validator("environment")
    @classmethod
    def _known_environment(cls, value: str) -> str:
        if value not in _ENVIRONMENTS:
            raise ValueError(f"environment must be one of {', '.join(_ENVIRONMENTS)}")
        return value


class BrokerConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: UUID
    provider: str
    environment: str
    session_state: str
    sandbox_fidelity: str
    capabilities_revision: int
    egress_allowlist: list[str]
    reconciliation_state: str
    reconciliation_reason: str


class BrokerAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    label: str
    broker: str
    mode: str
    status: str
    base_currency: str
    environment_label: str
    connection: BrokerConnectionOut
    external_identity: str


class CapabilitiesOut(BaseModel):
    provider: str
    environment: str
    revision: int
    sandbox_fidelity: str
    reconcile_methods: list[str]
    entries: list[dict]


class PreviewRequest(BaseModel):
    provider: str
    environment: str
    product: str
    order_type: str


class PreviewVerdict(BaseModel):
    decision: str  # "allowed" | "rejected"
    provider: str
    environment: str
    product: str
    order_type: str
    support: str | None = None
    reason: str | None = None


class GrantCreate(BaseModel):
    account_id: UUID
    assigned_principal_id: str = Field(min_length=1, max_length=128)
    allowed_environments: list[str] = Field(min_length=1)
    egress_allowlist: list[str] = Field(default_factory=list)
    rotation_policy: str = "manual"

    @field_validator("allowed_environments")
    @classmethod
    def _environments_known(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - set(_ENVIRONMENTS))
        if unknown:
            raise ValueError(f"unknown environments: {', '.join(unknown)}")
        if "live" in value:
            raise ValueError("A04 grants cannot include the live environment")
        return value

    @field_validator("rotation_policy")
    @classmethod
    def _policy_known(cls, value: str) -> str:
        if value not in ("manual", "scheduled", "on-refresh"):
            raise ValueError("rotation_policy must be manual, scheduled or on-refresh")
        return value


class GrantRotate(BaseModel):
    credentials: CredentialSet


class GrantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    secret_ref: str
    account_id: UUID
    tenant_id: UUID
    assigned_principal_id: str
    allowed_environments: list[str]
    egress_allowlist: list[str]
    rotation_policy: str
    state: str
    secret_version: int
    created_at: object
    rotated_at: object | None = None
    revoked_at: object | None = None
    last_denial_reason: str


def _audit(response: Response, resource: str, resource_id: UUID | None) -> None:
    response.headers["X-Audit-Resource"] = resource
    if resource_id is not None:
        response.headers["X-Audit-Resource-Id"] = str(resource_id)


def _grant_out(grant: SecretGrant) -> GrantOut:
    return GrantOut(
        id=grant.id,
        secret_ref=grant.secret_ref,
        account_id=grant.account_id,
        tenant_id=grant.tenant_id,
        assigned_principal_id=grant.assigned_principal_id,
        allowed_environments=grant.allowed_environments.split(","),
        egress_allowlist=[h for h in grant.egress_allowlist.splitlines() if h],
        rotation_policy=grant.rotation_policy,
        state=grant.state,
        secret_version=grant.secret_version,
        created_at=grant.created_at,
        rotated_at=grant.rotated_at,
        revoked_at=grant.revoked_at,
        last_denial_reason=grant.last_denial_reason,
    )


def _broker_account_out(
    account: Account, connection: BrokerConnection, identity: ExternalAccountIdentity
) -> BrokerAccountOut:
    return BrokerAccountOut(
        id=account.id,
        tenant_id=account.tenant_id,
        label=account.label,
        broker=account.broker,
        mode=account.mode,
        status=account.status,
        base_currency=account.base_currency,
        environment_label=f"{connection.provider}:{connection.environment}",
        connection=BrokerConnectionOut(
            account_id=connection.account_id,
            provider=connection.provider,
            environment=connection.environment,
            session_state=connection.session_state,
            sandbox_fidelity=connection.sandbox_fidelity,
            capabilities_revision=connection.capabilities_revision,
            egress_allowlist=list(connection.egress_hosts),
            reconciliation_state=connection.reconciliation_state,
            reconciliation_reason=connection.reconciliation_reason,
        ),
        external_identity=identity.masked_external_id,
    )


def _tenant_triple(
    db: Session, ctx: TenantContext, account_id: UUID
) -> tuple[Account, BrokerConnection, ExternalAccountIdentity]:
    account = db.get(Account, account_id)
    if account is None or account.tenant_id != ctx.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    connection = db.scalar(
        select(BrokerConnection).where(
            BrokerConnection.tenant_id == ctx.tenant_id,
            BrokerConnection.account_id == account_id,
        )
    )
    identity = db.scalar(
        select(ExternalAccountIdentity).where(
            ExternalAccountIdentity.tenant_id == ctx.tenant_id,
            ExternalAccountIdentity.account_id == account_id,
        )
    )
    if connection is None or identity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No A04 registry rows for this account")
    return account, connection, identity


# --- onboarding + registry views ------------------------------------------------


@router.post(
    "/broker-accounts", response_model=BrokerAccountOut, status_code=status.HTTP_201_CREATED
)
def onboard_account(
    payload: OnboardRequest,
    response: Response,
    ctx: TenantContext = Depends(require(Action.RESOURCE_WRITE)),
    db: Session = Depends(get_db),
) -> BrokerAccountOut:
    """Onboard one broker account: registry rows + sealed credentials + session."""
    try:
        account, connection, identity = onboard_broker_account(
            db,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user.id,
            label=payload.label,
            provider=payload.provider,
            environment=payload.environment,
            external_account_id=payload.external_account_id,
            credentials=payload.credentials,
            base_currency=payload.base_currency,
            mode=payload.mode,
        )
    except DuplicateExternalAccountError as exc:
        # Generic conflict: the owner of the existing connection is never revealed.
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except OnboardingRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    db.commit()
    _audit(response, "broker_connections", connection.id)
    return _broker_account_out(account, connection, identity)


@router.get("/broker-accounts", response_model=list[BrokerAccountOut])
def list_broker_accounts(
    ctx: TenantContext = Depends(require(Action.TENANT_READ)),
    db: Session = Depends(get_db),
) -> list[BrokerAccountOut]:
    connections = list(
        db.scalars(
            select(BrokerConnection)
            .where(BrokerConnection.tenant_id == ctx.tenant_id)
            .order_by(BrokerConnection.created_at)
        )
    )
    out: list[BrokerAccountOut] = []
    for connection in connections:
        triple = _tenant_triple(db, ctx, connection.account_id)
        out.append(_broker_account_out(*triple))
    return out


@router.get("/broker-accounts/capabilities", response_model=CapabilitiesOut)
def provider_capabilities(
    provider: str,
    environment: str,
    _user: User = Depends(get_current_user),
) -> CapabilitiesOut:
    """The registered capability statement for one (provider, environment)."""
    try:
        statement = capabilities_for(provider, environment)
    except UnknownProviderError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return CapabilitiesOut(
        provider=statement.provider,
        environment=str(statement.environment.value),
        revision=statement.revision,
        sandbox_fidelity=statement.sandbox_fidelity,
        reconcile_methods=list(statement.reconcile_methods),
        entries=[entry.model_dump(mode="json") for entry in statement.entries],
    )


@router.post("/broker-accounts/preview", response_model=PreviewVerdict)
def preview_order(
    payload: PreviewRequest,
    _user: User = Depends(get_current_user),
) -> PreviewVerdict:
    """Deployment preview: reject unsupported product/order-type pairs pre-submission."""
    try:
        statement = capabilities_for(payload.provider, payload.environment)
    except UnknownProviderError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"provider/environment is not registered: {exc}",
        ) from exc
    try:
        from algobots.contracts.enums import OrderType, ProductClass

        product = ProductClass(payload.product)
        order_type = OrderType(payload.order_type)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown product or order type: {exc}"
        ) from exc
    support = statement.support_for(product, order_type)
    if support == "unsupported":
        return PreviewVerdict(
            decision="rejected",
            provider=statement.provider,
            environment=str(statement.environment.value),
            product=payload.product,
            order_type=payload.order_type,
            support=support,
            reason=(
                f"{statement.provider}/{statement.environment.value} has no registered "
                f"capability for product={payload.product} order_type={payload.order_type}; "
                "unknown features are disabled"
            ),
        )
    return PreviewVerdict(
        decision="allowed",
        provider=statement.provider,
        environment=str(statement.environment.value),
        product=payload.product,
        order_type=payload.order_type,
        support=support,
    )


# --- secret grants ---------------------------------------------------------------


def _owned_grant_or_404(db: Session, ctx: TenantContext, grant_id: UUID) -> SecretGrant:
    grant = db.get(SecretGrant, grant_id)
    if grant is None or grant.tenant_id != ctx.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grant not found")
    return grant


@router.post("/account-grants", response_model=GrantOut, status_code=status.HTTP_201_CREATED)
def create_grant(
    payload: GrantCreate,
    response: Response,
    ctx: TenantContext = Depends(require(Action.RESOURCE_WRITE)),
    db: Session = Depends(get_db),
) -> GrantOut:
    """Bind one account's secret to one execution identity (SecretResolver grant)."""
    account = db.get(Account, payload.account_id)
    if account is None or account.tenant_id != ctx.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    store = SecretStore()
    try:
        grant = store.assign_grant(
            db,
            account=account,
            assigned_principal_id=payload.assigned_principal_id,
            granted_by_user_id=ctx.user.id,
            allowed_environments=tuple(payload.allowed_environments),
            egress_allowlist=tuple(payload.egress_allowlist),
            rotation_policy=payload.rotation_policy,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    db.commit()
    _audit(response, "secret_grants", grant.id)
    return _grant_out(grant)


@router.get("/account-grants", response_model=list[GrantOut])
def list_grants(
    ctx: TenantContext = Depends(require(Action.TENANT_READ)),
    db: Session = Depends(get_db),
) -> list[GrantOut]:
    grants = list(
        db.scalars(
            select(SecretGrant)
            .where(SecretGrant.tenant_id == ctx.tenant_id)
            .order_by(SecretGrant.created_at)
        )
    )
    return [_grant_out(grant) for grant in grants]


@router.post("/account-grants/{grant_id}/rotate", response_model=GrantOut)
def rotate_grant(
    grant_id: UUID,
    payload: GrantRotate,
    response: Response,
    ctx: TenantContext = Depends(require(Action.RESOURCE_WRITE)),
    db: Session = Depends(get_db),
) -> GrantOut:
    """Rotate credentials in place: version bump, same ownership records."""
    grant = _owned_grant_or_404(db, ctx, grant_id)
    store = SecretStore()
    try:
        grant = store.rotate(
            db, grant=grant, secrets=payload.credentials.model_dump(mode="json")
        )
    except ResolutionDenied as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    _audit(response, "secret_grants", grant.id)
    return _grant_out(grant)


@router.post("/account-grants/{grant_id}/revoke", response_model=GrantOut)
def revoke_grant(
    grant_id: UUID,
    response: Response,
    ctx: TenantContext = Depends(require(Action.RESOURCE_WRITE)),
    db: Session = Depends(get_db),
) -> GrantOut:
    """Revoke resolution and freeze the account; exposure flags reconciliation."""
    grant = _owned_grant_or_404(db, ctx, grant_id)
    grant = SecretStore().revoke(db, grant=grant)
    _audit(response, "secret_grants", grant.id)
    return _grant_out(grant)
