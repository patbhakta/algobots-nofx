"""ORM model for secret-resolution grants (A04).

One row per (account, assigned execution identity): the database backing of
the ``SecretResolver`` contract. Tenant-scoped with a composite foreign key
to ``accounts`` (a grant can never point at another tenant's account) and
covered by the same PostgreSQL row-level security policy family as the other
tenant-owned tables (migration 0010).
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from algobots.api.database import Base

# ACTIVE  -> resolvable; ROTATED -> current version resolvable (bump in place);
# REVOKED -> frozen, resolution denied; EXPIRED -> swept (dead token), denied.
RESOLVABLE_STATES = ("ACTIVE", "ROTATED")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SecretGrant(Base):
    """Which single execution identity may resolve one account's secret."""

    __tablename__ = "secret_grants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["accounts.tenant_id", "accounts.id"],
            name="fk_secret_grants_tenant_account",
            ondelete="CASCADE",
        ),
        UniqueConstraint("account_id", "assigned_principal_id", name="uq_secret_grants_principal"),
        Index("ix_secret_grants_tenant_state", "tenant_id", "state"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    account_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    # The one execution identity (contracts.Principal principal_id) that may resolve.
    assigned_principal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    granted_by_user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    allowed_environments: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    egress_allowlist: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rotation_policy: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    secret_version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_denial_reason: Mapped[str] = mapped_column(String(128), nullable=False, default="")

    @property
    def secret_ref(self) -> str:
        from algobots.secrets.refs import build_secret_ref

        return build_secret_ref(self.tenant_id, self.account_id)
