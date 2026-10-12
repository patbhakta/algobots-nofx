"""Server-side login sessions (A03 checklist 2: logout, revocation).

Every access token carries a `sid` claim naming one row here. The row is
checked on every authenticated request, so logout, member revocation and
role-driven revocation take effect on the next request: the declared
revocation window is 0 s, well inside the 60 s target (AC3).
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from algobots.api.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (Index("ix_auth_sessions_user", "user_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    # Active tenant for this session; switched only via an authenticated,
    # membership-checked request, never taken from a request body.
    tenant_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
