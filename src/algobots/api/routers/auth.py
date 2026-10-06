"""Auth routes: invite-only registration, session-bound login/logout, OIDC, invites.

Registration has no public path (A03): a new user needs either the bootstrap
code (first user only), a platform invite code from a platform owner, or a
tenant invite token addressed to their email. Platform-invite and bootstrap
users get a personal tenant they own; tenant-invite users join the inviting
tenant with the invited role and get no personal tenant.
"""

import secrets
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from algobots.api.config import get_settings
from algobots.api.database import get_db
from algobots.api.dependencies import AuthContext, get_auth_context, get_authenticated_user
from algobots.api.memberships import service as memberships
from algobots.api.models import InviteCode, User, UserRole
from algobots.api.schemas import (
    InviteOut,
    LoginRequest,
    OIDCLoginRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from algobots.api.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

users_router = APIRouter(prefix="/api/users", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> Response:
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    settings = get_settings()
    bootstrap = False
    invite: InviteCode | None = None
    tenant_invite = None
    if payload.tenant_invite_token is not None:
        tenant_invite = memberships.find_redeemable_invite(db, payload.tenant_invite_token, email)
    else:
        user_count = db.scalar(select(func.count()).select_from(User))
        bootstrap = user_count == 0 and payload.invite_code == settings.bootstrap_invite_code
    if tenant_invite is None and not bootstrap:
        invite = db.scalar(select(InviteCode).where(InviteCode.code == payload.invite_code))
        if invite is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Invalid invite code")
        if invite.claimed_by_user_id is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Invite code already used")
        expires_at = invite.expires_at
        if expires_at.tzinfo is None:  # sqlite returns naive datetimes
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < datetime.now(UTC):
            raise HTTPException(status.HTTP_409_CONFLICT, "Invite code expired")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
        role=(UserRole.OWNER if bootstrap else UserRole.MEMBER).value,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        # A concurrent registration won the race for this email.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None
    if tenant_invite is not None:
        # Atomic single-use redemption; a lost race rolls the user back too.
        memberships.redeem_invite(db, tenant_invite, user)
    else:
        memberships.create_personal_tenant(db, user)
    if invite is not None:
        invite.claimed_by_user_id = user.id
        invite.claimed_at = datetime.now(UTC)
    db.commit()

    body = UserOut.model_validate(user).model_dump_json()
    return Response(
        content=body,
        status_code=status.HTTP_201_CREATED,
        media_type="application/json",
        headers={"X-Audit-Resource": "users", "X-Audit-Resource-Id": str(user.id)},
    )


def _issue_token(db: Session, user: User) -> TokenResponse:
    session = memberships.start_session(db, user)
    db.commit()
    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(user.id, session.id),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive")
    return _issue_token(db, user)


@router.post("/oidc/login", response_model=TokenResponse)
def oidc_login(payload: OIDCLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Exchange an ID token from the configured (local/fake) provider for a session.

    Verifies signature, issuer, audience and expiry, and requires a verified
    email that belongs to an existing active user. Unknown emails are refused:
    OIDC is a login method, not a registration path.
    """
    settings = get_settings()
    if not settings.oidc_issuer or not settings.oidc_shared_secret:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "OIDC login is not configured")
    try:
        claims = pyjwt.decode(
            payload.id_token,
            settings.oidc_shared_secret,
            algorithms=["HS256"],
            issuer=settings.oidc_issuer,
            audience=settings.oidc_audience,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "email"]},
        )
    except pyjwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid ID token") from None
    if claims.get("email_verified") is not True:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email not verified by provider")
    user = db.scalar(select(User).where(User.email == str(claims["email"]).lower()))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No invited account for this identity")
    return _issue_token(db, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> None:
    """Revoke the calling session; its token is rejected from the next request."""
    ctx.session.revoked_at = datetime.now(UTC)
    db.commit()
    response.headers["X-Audit-Resource"] = "auth_sessions"
    response.headers["X-Audit-Resource-Id"] = str(ctx.session.id)


@router.post("/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def create_invite(
    response: Response,
    current_user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> InviteOut:
    """Platform invite code (new user + personal tenant). Platform owners only."""
    if current_user.role != UserRole.OWNER.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only platform owners mint platform invites")
    settings = get_settings()
    invite = InviteCode(
        code=f"ALG-{secrets.token_urlsafe(18)}",
        created_by_user_id=current_user.id,
        expires_at=datetime.now(UTC) + timedelta(days=settings.invite_expire_days),
    )
    db.add(invite)
    db.commit()
    response.headers["X-Audit-Resource"] = "invite_codes"
    response.headers["X-Audit-Resource-Id"] = str(invite.id)
    return InviteOut.model_validate(invite)


@router.get("/invites", response_model=list[InviteOut])
def list_invites(
    current_user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> list[InviteCode]:
    return list(
        db.scalars(
            select(InviteCode)
            .where(InviteCode.created_by_user_id == current_user.id)
            .order_by(InviteCode.created_at.desc())
        )
    )


@users_router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_authenticated_user)) -> User:
    return current_user
