"""Membership, invite, session and grant operations (A03 checklist 2, 4, 5).

Every privileged change writes an audit event in the same transaction.
Invariants enforced here:

- invite tokens are 256-bit random values stored only as SHA-256;
- redemption is a single guarded UPDATE (`redeemed_at IS NULL AND revoked_at IS
  NULL AND expires_at > now`), so of N concurrent redeemers exactly one wins,
  and the `(tenant_id, user_id)` unique key backs it up;
- the redeemer's email must equal the invite's intended recipient;
- a tenant always keeps at least one active owner;
- revoking a member revokes their sessions in that tenant and their grants;
- membership never implies a trading grant: `principal_for` lists only
  explicit `account_grants` rows.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from algobots.api.auth.audit import record_event
from algobots.api.auth.models import AuthSession
from algobots.api.auth.policy import INVITABLE_ROLES, TenantRole
from algobots.api.config import get_settings
from algobots.api.memberships.models import (
    AccountGrant,
    MembershipStatus,
    Tenant,
    TenantInvite,
    TenantMembership,
)
from algobots.api.models import Account, User
from algobots.contracts.identity import ALLOWED_GRANTS, Grant, IdentityKind, Principal

# Viewers may be allowed to see an account, never to act on it.
VIEWER_GRANTS = frozenset({Grant.ACCOUNT_READ})


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- tenants & sessions ---


def create_personal_tenant(db: Session, user: User) -> Tenant:
    tenant = Tenant(
        name=f"{user.display_name} (personal)"[:120],
        personal_owner_user_id=user.id,
        created_by_user_id=user.id,
    )
    db.add(tenant)
    db.flush()
    db.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, role=TenantRole.OWNER.value))
    db.flush()
    record_event(
        db,
        event="tenant.created",
        actor_user_id=user.id,
        tenant_id=tenant.id,
        resource="tenants",
        resource_id=tenant.id,
        personal=True,
    )
    return tenant


def active_membership(db: Session, tenant_id: UUID, user_id: UUID) -> TenantMembership | None:
    return db.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user_id,
            TenantMembership.status == MembershipStatus.ACTIVE,
        )
    )


def default_tenant_id(db: Session, user_id: UUID) -> UUID | None:
    """Personal tenant if still a member of it, else the oldest active membership."""
    rows = db.execute(
        select(TenantMembership.tenant_id, Tenant.personal_owner_user_id)
        .join(Tenant, Tenant.id == TenantMembership.tenant_id)
        .where(
            TenantMembership.user_id == user_id,
            TenantMembership.status == MembershipStatus.ACTIVE,
        )
        .order_by(TenantMembership.created_at, TenantMembership.id)
    ).all()
    for tenant_id, personal_owner in rows:
        if personal_owner == user_id:
            return tenant_id
    return rows[0][0] if rows else None


def start_session(db: Session, user: User, tenant_id: UUID | None = None) -> AuthSession:
    settings = get_settings()
    session = AuthSession(
        user_id=user.id,
        tenant_id=tenant_id if tenant_id is not None else default_tenant_id(db, user.id),
        expires_at=_now() + timedelta(minutes=settings.access_token_expire_minutes),
    )
    db.add(session)
    db.flush()
    return session


def revoke_sessions(db: Session, user_id: UUID, tenant_id: UUID | None = None) -> int:
    query = update(AuthSession).where(
        AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)
    )
    if tenant_id is not None:
        query = query.where(AuthSession.tenant_id == tenant_id)
    return db.execute(query.values(revoked_at=_now())).rowcount or 0


# --- invites ---


def create_invite(
    db: Session, *, tenant_id: UUID, inviter: User, email: str, role: str
) -> tuple[TenantInvite, str]:
    """Mint an invite; returns the row and the plaintext token (shown once)."""
    if role not in {r.value for r in INVITABLE_ROLES}:
        raise HTTPException(422, f"Role '{role}' is not invitable")
    email = email.lower()
    existing = db.scalar(
        select(TenantMembership.id)
        .join(User, User.id == TenantMembership.user_id)
        .where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.status == MembershipStatus.ACTIVE,
            User.email == email,
        )
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already an active member")
    token = f"tinv_{secrets.token_urlsafe(32)}"
    invite = TenantInvite(
        tenant_id=tenant_id,
        email=email,
        role=role,
        token_hash=hash_invite_token(token),
        invited_by_user_id=inviter.id,
        expires_at=_now() + timedelta(days=get_settings().invite_expire_days),
    )
    db.add(invite)
    db.flush()
    record_event(
        db,
        event="invite.created",
        actor_user_id=inviter.id,
        tenant_id=tenant_id,
        resource="tenant_invites",
        resource_id=invite.id,
        role=role,
    )
    return invite, token


def find_redeemable_invite(db: Session, token: str, email: str) -> TenantInvite:
    """Validate an invite for `email` without consuming it (409 on any failure)."""
    invite = db.scalar(
        select(TenantInvite).where(TenantInvite.token_hash == hash_invite_token(token))
    )
    if invite is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Invalid invite")
    if invite.revoked_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Invite revoked")
    if invite.redeemed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Invite already used")
    if _aware(invite.expires_at) <= _now():
        raise HTTPException(status.HTTP_409_CONFLICT, "Invite expired")
    if invite.email != email.lower():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invite issued to a different recipient")
    return invite


def redeem_invite(db: Session, invite: TenantInvite, user: User) -> TenantMembership:
    """Consume the invite atomically and create (or reactivate) the membership."""
    now = _now()
    claimed = db.execute(
        update(TenantInvite)
        .where(
            TenantInvite.id == invite.id,
            TenantInvite.redeemed_at.is_(None),
            TenantInvite.revoked_at.is_(None),
            TenantInvite.expires_at > now,
        )
        .values(redeemed_at=now, redeemed_by_user_id=user.id)
        .execution_options(synchronize_session=False)
    ).rowcount
    if claimed != 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Invite already used")

    membership = db.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == invite.tenant_id,
            TenantMembership.user_id == user.id,
        )
    )
    if membership is not None and membership.status == MembershipStatus.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already an active member")
    if membership is None:
        membership = TenantMembership(
            tenant_id=invite.tenant_id,
            user_id=user.id,
            role=invite.role,
            invited_by_user_id=invite.invited_by_user_id,
        )
        db.add(membership)
    else:
        membership.role = invite.role
        membership.status = MembershipStatus.ACTIVE
        membership.revoked_at = None
        membership.invited_by_user_id = invite.invited_by_user_id
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Already an active member") from None
    record_event(
        db,
        event="membership.created",
        actor_user_id=user.id,
        tenant_id=invite.tenant_id,
        resource="tenant_memberships",
        resource_id=membership.id,
        role=membership.role,
        invite_id=invite.id,
    )
    return membership


def revoke_invite(db: Session, *, tenant_id: UUID, actor: User, invite_id: UUID) -> TenantInvite:
    invite = db.get(TenantInvite, invite_id)
    if invite is None or invite.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found")
    if invite.redeemed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Invite already used")
    if invite.revoked_at is None:
        invite.revoked_at = _now()
        record_event(
            db,
            event="invite.revoked",
            actor_user_id=actor.id,
            tenant_id=tenant_id,
            resource="tenant_invites",
            resource_id=invite.id,
        )
    return invite


# --- membership management ---


def tenant_membership_or_404(db: Session, tenant_id: UUID, membership_id: UUID) -> TenantMembership:
    membership = db.get(TenantMembership, membership_id)
    if membership is None or membership.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membership not found")
    return membership


def _active_owner_count(db: Session, tenant_id: UUID) -> int:
    return db.scalar(
        select(func.count())
        .select_from(TenantMembership)
        .where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.role == TenantRole.OWNER.value,
            TenantMembership.status == MembershipStatus.ACTIVE,
        )
    )


def _guard_last_owner(db: Session, membership: TenantMembership) -> None:
    if (
        membership.role == TenantRole.OWNER.value
        and membership.status == MembershipStatus.ACTIVE
        and _active_owner_count(db, membership.tenant_id) <= 1
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "A tenant must keep at least one owner")


def change_role(db: Session, *, actor: User, membership: TenantMembership, role: str) -> None:
    if role not in {r.value for r in TenantRole}:
        raise HTTPException(422, f"Unknown role '{role}'")
    if membership.status != MembershipStatus.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Membership is revoked")
    if role == membership.role:
        return
    if role != TenantRole.OWNER.value:
        _guard_last_owner(db, membership)
    old = membership.role
    membership.role = role
    if role == TenantRole.VIEWER.value:
        # Viewers keep at most read access to accounts.
        db.execute(
            delete(AccountGrant).where(
                AccountGrant.tenant_id == membership.tenant_id,
                AccountGrant.user_id == membership.user_id,
                AccountGrant.grant.not_in([g.value for g in VIEWER_GRANTS]),
            )
        )
    record_event(
        db,
        event="membership.role_changed",
        actor_user_id=actor.id,
        tenant_id=membership.tenant_id,
        resource="tenant_memberships",
        resource_id=membership.id,
        old_role=old,
        new_role=role,
        target_user_id=membership.user_id,
    )


def revoke_membership(db: Session, *, actor: User, membership: TenantMembership) -> None:
    if membership.status != MembershipStatus.ACTIVE:
        return
    _guard_last_owner(db, membership)
    membership.status = MembershipStatus.REVOKED
    membership.revoked_at = _now()
    sessions = revoke_sessions(db, membership.user_id, membership.tenant_id)
    grants = (
        db.execute(
            delete(AccountGrant).where(
                AccountGrant.tenant_id == membership.tenant_id,
                AccountGrant.user_id == membership.user_id,
            )
        ).rowcount
        or 0
    )
    record_event(
        db,
        event="membership.revoked",
        actor_user_id=actor.id,
        tenant_id=membership.tenant_id,
        resource="tenant_memberships",
        resource_id=membership.id,
        target_user_id=membership.user_id,
        sessions_revoked=sessions,
        grants_removed=grants,
    )


# --- account trading grants ---


def add_grant(
    db: Session,
    *,
    actor: User,
    membership: TenantMembership,
    account_id: UUID,
    grant: str,
) -> AccountGrant:
    try:
        grant_enum = Grant(grant)
    except ValueError:
        raise HTTPException(422, f"Unknown grant '{grant}'") from None
    if grant_enum not in ALLOWED_GRANTS[IdentityKind.USER]:
        raise HTTPException(422, f"Users cannot hold {grant}")
    if membership.status != MembershipStatus.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Membership is revoked")
    if membership.role == TenantRole.VIEWER.value and grant_enum not in VIEWER_GRANTS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Viewers may only hold ACCOUNT_READ")
    account = db.get(Account, account_id)
    if account is None or account.tenant_id != membership.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    row = AccountGrant(
        tenant_id=membership.tenant_id,
        account_id=account_id,
        user_id=membership.user_id,
        grant=grant_enum.value,
        granted_by_user_id=actor.id,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Grant already exists") from None
    record_event(
        db,
        event="grant.added",
        actor_user_id=actor.id,
        tenant_id=membership.tenant_id,
        resource="account_grants",
        resource_id=row.id,
        grant=grant_enum.value,
        account_id=account_id,
        target_user_id=membership.user_id,
    )
    return row


def remove_grant(db: Session, *, actor: User, tenant_id: UUID, grant_id: UUID) -> None:
    row = db.get(AccountGrant, grant_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grant not found")
    db.delete(row)
    record_event(
        db,
        event="grant.removed",
        actor_user_id=actor.id,
        tenant_id=tenant_id,
        resource="account_grants",
        resource_id=grant_id,
        grant=row.grant,
        account_id=row.account_id,
        target_user_id=row.user_id,
    )


def principal_for(
    db: Session, user_id: UUID, tenant_id: UUID, account_id: UUID | None = None
) -> Principal:
    """`Principal@1.0` for a member: grants come only from explicit grant rows."""
    query = select(AccountGrant.grant).where(
        AccountGrant.tenant_id == tenant_id, AccountGrant.user_id == user_id
    )
    if account_id is not None:
        query = query.where(AccountGrant.account_id == account_id)
    grants = sorted({Grant(g) for g in db.scalars(query)})
    return Principal(
        schema_version=Principal.contract_version,
        principal_id=str(user_id),
        kind=IdentityKind.USER,
        tenant_id=str(tenant_id),
        grants=tuple(grants),
    )
