"""FastAPI dependencies: session-bound authentication and tenant context.

`get_auth_context` resolves the bearer token to a live `auth_sessions` row, an
active user and, when the session has one, the active tenant membership. The
tenant comes only from that server-side session plus a membership re-check on
every request, never from a request body or header. It is bound to the DB
session (`algobots.api.auth.context.set_tenant`) so PostgreSQL row-level
policies see it in every transaction of the request.

`get_current_user` keeps its S0.2 signature for routers outside A03
(deployments, account credentials, approvals) but now enforces tenancy for
them: it requires an active membership and applies the role matrix by HTTP
method (reads need `tenant.read`, anything else `resource.write`). Their rows
are also filtered to the active tenant by the ORM criteria in
`algobots.api.auth.context`. Tenant-independent routes (platform invites,
`/api/users/me`) use `get_authenticated_user`.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from algobots.api.auth.audit import record_denial
from algobots.api.auth.context import set_tenant
from algobots.api.auth.models import AuthSession
from algobots.api.auth.policy import Action, is_allowed
from algobots.api.database import get_db
from algobots.api.memberships.models import MembershipStatus, TenantMembership
from algobots.api.models import User
from algobots.api.security import decode_access_claims

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: AuthSession
    tenant_id: UUID | None
    role: str | None


@dataclass(frozen=True)
class TenantContext:
    user: User
    session: AuthSession
    tenant_id: UUID
    role: str


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def get_auth_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> AuthContext:
    """Authenticate the request; 401 unless token, session and user are all live."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Missing bearer token")
    claims = decode_access_claims(credentials.credentials)
    if claims is None:
        raise _unauthorized("Invalid or expired token")
    try:
        user_id = UUID(claims["sub"])
        session_id = UUID(claims["sid"])
    except ValueError:
        raise _unauthorized("Invalid token subject") from None

    auth_session = db.get(AuthSession, session_id)
    if (
        auth_session is None
        or auth_session.user_id != user_id
        or auth_session.revoked_at is not None
        or _aware(auth_session.expires_at) <= datetime.now(UTC)
    ):
        raise _unauthorized("Session revoked or expired")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("User not found or inactive")

    tenant_id: UUID | None = None
    role: str | None = None
    if auth_session.tenant_id is not None:
        membership = db.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == auth_session.tenant_id,
                TenantMembership.user_id == user.id,
                TenantMembership.status == MembershipStatus.ACTIVE,
            )
        )
        if membership is None:
            # Membership revoked after this session was issued: the session is
            # dead for every request, not just privileged ones.
            raise _unauthorized("Membership revoked")
        tenant_id, role = membership.tenant_id, membership.role

    set_tenant(db, tenant_id)
    request.state.tenant_id = tenant_id
    return AuthContext(user=user, session=auth_session, tenant_id=tenant_id, role=role)


_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_authenticated_user(ctx: AuthContext = Depends(get_auth_context)) -> User:
    """Authenticated user with no tenant requirement (platform-level routes)."""
    return ctx.user


def get_tenant_context(ctx: AuthContext = Depends(get_auth_context)) -> TenantContext:
    """Require an active tenant membership (403 when the session has none)."""
    if ctx.tenant_id is None or ctx.role is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No active tenant membership")
    return TenantContext(user=ctx.user, session=ctx.session, tenant_id=ctx.tenant_id, role=ctx.role)


def _enforce(request: Request, ctx: TenantContext, action: Action) -> None:
    if not is_allowed(ctx.role, action):
        record_denial(
            method=request.method,
            path=request.url.path,
            actor_user_id=ctx.user.id,
            tenant_id=ctx.tenant_id,
            role=ctx.role,
            action=action.value,
        )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"Role '{ctx.role}' may not perform {action.value}"
        )


def get_current_user(request: Request, ctx: TenantContext = Depends(get_tenant_context)) -> User:
    """Active tenant member allowed this request's method by the role matrix."""
    action = Action.TENANT_READ if request.method in _READ_METHODS else Action.RESOURCE_WRITE
    _enforce(request, ctx, action)
    return ctx.user


def require(action: Action):
    """Dependency factory: the active role must allow `action`, else audit + 403."""

    def _check(request: Request, ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        _enforce(request, ctx, action)
        return ctx

    return _check
