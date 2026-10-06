"""Encrypted broker credentials model (1:1 with accounts)."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from algobots.api.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AccountCredential(Base):
    """Encrypted credential store for one broker account.

    `encrypted_secrets` holds a Fernet-sealed JSON blob (see
    `algobots.api.accounts.crypto`). No plaintext secret column exists.
    `token_status` is the token-health state machine the sweep drives:
    `active` -> (`active` after silent refresh | `expired` on failure/expiry).
    """

    __tablename__ = "account_credentials"
    __table_args__ = (Index("ix_account_credentials_token_status", "token_status"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("accounts.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    encrypted_secrets: Mapped[str] = mapped_column(Text, nullable=False)
    key_id: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    token_status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_refresh_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=True
    )
