"""Auth routes: invite-code registration, JWT login, invite management."""

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from algobots.api.config import get_settings
from algobots.api.database import get_db
from algobots.api.dependencies import get_current_user
from algobots.api.models import DEMO_OWNER_EMAIL, InviteCode, User, UserRole
from algobots.api.schemas import (
    InviteOut,
    LoginRequest,
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
    # the seeded /demo registry owner (inactive, cannot log in) never consumes the bootstrap
    user_count = db.scalar(
        select(func.count()).select_from(User).where(User.email != DEMO_OWNER_EMAIL)
    )
    bootstrap = user_count == 0 and payload.invite_code == settings.bootstrap_invite_code

    invite: InviteCode | None = None
    if not bootstrap:
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
    db.flush()
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


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive")
    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(user.id),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def create_invite(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InviteOut:
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
    current_user: User = Depends(get_current_user),
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
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
