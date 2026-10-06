"""Tenant, membership, invite and grant routes (A03 output contracts).

`GET /api/me`, `GET /api/tenants` and `/api/memberships`. Member management is
owner-only (`membership.manage`); every list is scoped to the active tenant
from the authenticated session.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from algobots.api.auth.audit import record_event
from algobots.api.auth.cursor import paginate
from algobots.api.auth.policy import Action
from algobots.api.database import get_db
from algobots.api.dependencies import AuthContext, TenantContext, get_auth_context, require
from algobots.api.memberships import service
from algobots.api.memberships.models import (
    AccountGrant,
    MembershipStatus,
    Tenant,
    TenantInvite,
    TenantMembership,
)
from algobots.api.memberships.schemas import (
    GrantCreate,
    GrantOut,
    InviteCreate,
    InviteRedeem,
    MembershipOut,
    MembershipUpdate,
    MeOut,
    TenantInviteCreated,
    TenantInviteOut,
    TenantOut,
)

me_router = APIRouter(prefix="/api", tags=["tenancy"])
router = APIRouter(prefix="/api/memberships", tags=["tenancy"])


def _audit(response: Response, resource: str, resource_id: UUID | None) -> None:
    response.headers["X-Audit-Resource"] = resource
    if resource_id is not None:
        response.headers["X-Audit-Resource-Id"] = str(resource_id)


def _tenants(db: Session, ctx: AuthContext) -> list[TenantOut]:
    rows = db.execute(
        select(Tenant, TenantMembership.role)
        .join(TenantMembership, TenantMembership.tenant_id == Tenant.id)
        .where(
            TenantMembership.user_id == ctx.user.id,
            TenantMembership.status == MembershipStatus.ACTIVE,
        )
        .order_by(TenantMembership.created_at, Tenant.id)
    ).all()
    return [
        TenantOut(
            id=tenant.id,
            name=tenant.name,
            role=role,
            personal=tenant.personal_owner_user_id == ctx.user.id,
            active=tenant.id == ctx.tenant_id,
        )
        for tenant, role in rows
    ]


# --- /me and tenants ---


@me_router.get("/me", response_model=MeOut)
def me(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> MeOut:
    grants: list[str] = []
    if ctx.tenant_id is not None:
        grants = [g.value for g in service.principal_for(db, ctx.user.id, ctx.tenant_id).grants]
    return MeOut(
        id=ctx.user.id,
        email=ctx.user.email,
        display_name=ctx.user.display_name,
        tenant_id=ctx.tenant_id,
        role=ctx.role,
        tenants=_tenants(db, ctx),
        grants=grants,
    )


@me_router.get("/tenants", response_model=list[TenantOut])
def list_tenants(
    ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)
) -> list[TenantOut]:
    return _tenants(db, ctx)


@me_router.post("/tenants/{tenant_id}/switch", response_model=TenantOut)
def switch_tenant(
    tenant_id: UUID,
    response: Response,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> TenantOut:
    """Make `tenant_id` the session's active tenant; requires an active membership."""
    membership = service.active_membership(db, tenant_id, ctx.user.id)
    if membership is None:
        # Indistinguishable from a tenant that doesn't exist.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    session = ctx.session
    session.tenant_id = tenant_id
    record_event(
        db,
        event="session.tenant_switched",
        actor_user_id=ctx.user.id,
        tenant_id=tenant_id,
        resource="auth_sessions",
        resource_id=session.id,
        from_tenant_id=ctx.tenant_id,
    )
    db.commit()
    _audit(response, "auth_sessions", session.id)
    tenant = db.get(Tenant, tenant_id)
    return TenantOut(
        id=tenant.id,
        name=tenant.name,
        role=membership.role,
        personal=tenant.personal_owner_user_id == ctx.user.id,
        active=True,
    )


# --- invites (declared before /{membership_id} routes) ---


@router.post("/invites", response_model=TenantInviteCreated, status_code=status.HTTP_201_CREATED)
def create_invite(
    payload: InviteCreate,
    response: Response,
    ctx: TenantContext = Depends(require(Action.MEMBERSHIP_MANAGE)),
    db: Session = Depends(get_db),
) -> TenantInviteCreated:
    invite, token = service.create_invite(
        db, tenant_id=ctx.tenant_id, inviter=ctx.user, email=payload.email, role=payload.role
    )
    db.commit()
    _audit(response, "tenant_invites", invite.id)
    return TenantInviteCreated(**TenantInviteOut.model_validate(invite).model_dump(), token=token)


@router.get("/invites", response_model=list[TenantInviteOut])
def list_invites(
    response: Response,
    cursor: str | None = None,
    limit: int | None = None,
    ctx: TenantContext = Depends(require(Action.MEMBERSHIP_MANAGE)),
    db: Session = Depends(get_db),
) -> list[TenantInvite]:
    query = select(TenantInvite).where(TenantInvite.tenant_id == ctx.tenant_id)
    return paginate(
        db,
        query,
        TenantInvite,
        tenant_id=ctx.tenant_id,
        cursor=cursor,
        limit=limit,
        response=response,
    )


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite(
    invite_id: UUID,
    response: Response,
    ctx: TenantContext = Depends(require(Action.MEMBERSHIP_MANAGE)),
    db: Session = Depends(get_db),
) -> None:
    service.revoke_invite(db, tenant_id=ctx.tenant_id, actor=ctx.user, invite_id=invite_id)
    db.commit()
    _audit(response, "tenant_invites", invite_id)


@router.post("/invites/redeem", response_model=MembershipOut, status_code=status.HTTP_201_CREATED)
def redeem_invite(
    payload: InviteRedeem,
    response: Response,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> TenantMembership:
    """An existing user accepts an invite addressed to their email."""
    invite = service.find_redeemable_invite(db, payload.token, ctx.user.email)
    membership = service.redeem_invite(db, invite, ctx.user)
    db.commit()
    _audit(response, "tenant_memberships", membership.id)
    return membership


# --- memberships ---


@router.get("", response_model=list[MembershipOut])
def list_memberships(
    response: Response,
    cursor: str | None = None,
    limit: int | None = None,
    ctx: TenantContext = Depends(require(Action.TENANT_READ)),
    db: Session = Depends(get_db),
) -> list[TenantMembership]:
    query = select(TenantMembership).where(TenantMembership.tenant_id == ctx.tenant_id)
    return paginate(
        db,
        query,
        TenantMembership,
        tenant_id=ctx.tenant_id,
        cursor=cursor,
        limit=limit,
        response=response,
    )


@router.patch("/{membership_id}", response_model=MembershipOut)
def update_membership(
    membership_id: UUID,
    payload: MembershipUpdate,
    response: Response,
    ctx: TenantContext = Depends(require(Action.MEMBERSHIP_MANAGE)),
    db: Session = Depends(get_db),
) -> TenantMembership:
    membership = service.tenant_membership_or_404(db, ctx.tenant_id, membership_id)
    service.change_role(db, actor=ctx.user, membership=membership, role=payload.role)
    db.commit()
    _audit(response, "tenant_memberships", membership.id)
    return membership


@router.delete("/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_membership(
    membership_id: UUID,
    response: Response,
    ctx: TenantContext = Depends(require(Action.MEMBERSHIP_MANAGE)),
    db: Session = Depends(get_db),
) -> None:
    membership = service.tenant_membership_or_404(db, ctx.tenant_id, membership_id)
    service.revoke_membership(db, actor=ctx.user, membership=membership)
    db.commit()
    _audit(response, "tenant_memberships", membership.id)


# --- account trading grants ---


@router.get("/{membership_id}/grants", response_model=list[GrantOut])
def list_grants(
    membership_id: UUID,
    ctx: TenantContext = Depends(require(Action.TENANT_READ)),
    db: Session = Depends(get_db),
) -> list[AccountGrant]:
    membership = service.tenant_membership_or_404(db, ctx.tenant_id, membership_id)
    return list(
        db.scalars(
            select(AccountGrant)
            .where(
                AccountGrant.tenant_id == ctx.tenant_id,
                AccountGrant.user_id == membership.user_id,
            )
            .order_by(AccountGrant.created_at)
        )
    )


@router.post(
    "/{membership_id}/grants", response_model=GrantOut, status_code=status.HTTP_201_CREATED
)
def add_grant(
    membership_id: UUID,
    payload: GrantCreate,
    response: Response,
    ctx: TenantContext = Depends(require(Action.MEMBERSHIP_MANAGE)),
    db: Session = Depends(get_db),
) -> AccountGrant:
    membership = service.tenant_membership_or_404(db, ctx.tenant_id, membership_id)
    row = service.add_grant(
        db,
        actor=ctx.user,
        membership=membership,
        account_id=payload.account_id,
        grant=payload.grant,
    )
    db.commit()
    _audit(response, "account_grants", row.id)
    return row


@router.delete("/grants/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_grant(
    grant_id: UUID,
    response: Response,
    ctx: TenantContext = Depends(require(Action.MEMBERSHIP_MANAGE)),
    db: Session = Depends(get_db),
) -> None:
    service.remove_grant(db, actor=ctx.user, tenant_id=ctx.tenant_id, grant_id=grant_id)
    db.commit()
    _audit(response, "account_grants", grant_id)
