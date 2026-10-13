"""Encrypted broker credentials model (1:1 with accounts) plus A04 registry rows.

- :class:`AccountCredential` — Fernet-sealed secrets, one row per account.
- :class:`BrokerConnection` — per-account provider/environment configuration,
  broker session state and reconciliation posture (A04).
- :class:`ExternalAccountIdentity` — the venue-side identity of an account as
  a deterministic fingerprint, globally unique so the same external account
  cannot be onboarded twice across tenants (A04 checklist 5).
"""

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, Uuid
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


class BrokerConnection(Base):
    """One account's broker-facing connection: provider config + session state.

    User authentication (control plane JWT) is separate from this broker
    session state, which only the provider handshake moves between
    UNCONFIGURED -> CONNECTING -> CONNECTED / DEGRADED / EXPIRED / REVOKED.
    `reconciliation_state` carries the A04 recovery posture: revoked or
    expired credentials freeze entries and mark exposure as
    `needs_reconciliation` — never a silently flat view.
    """

    __tablename__ = "broker_connections"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["accounts.tenant_id", "accounts.id"],
            name="fk_broker_connections_tenant_account",
            ondelete="CASCADE",
        ),
        Index("uq_broker_connections_account", "account_id", unique=True),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    account_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    session_state: Mapped[str] = mapped_column(String(16), nullable=False, default="UNCONFIGURED")
    egress_allowlist: Mapped[str] = mapped_column(Text, nullable=False, default="")
    capabilities_revision: Mapped[int] = mapped_column(nullable=False, default=0)
    sandbox_fidelity: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    reconciliation_state: Mapped[str] = mapped_column(String(32), nullable=False, default="ok")
    reconciliation_reason: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    session_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=True
    )

    @property
    def egress_hosts(self) -> tuple[str, ...]:
        return tuple(h for h in self.egress_allowlist.splitlines() if h)


class ExternalAccountIdentity(Base):
    """Venue-side identity of one account, as a deterministic fingerprint.

    The fingerprint is `sha256(provider:environment:external_account_id)` —
    globally comparable across tenants (that is how duplicate connections are
    detected) but carrying no tenant, user or credential information, so the
    uniqueness conflict alone never reveals who owns the existing connection.
    Ownership transfer (later) bumps `ownership_epoch` in place.
    """

    __tablename__ = "external_account_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["accounts.tenant_id", "accounts.id"],
            name="fk_external_account_identities_tenant_account",
            ondelete="CASCADE",
        ),
        Index("uq_external_account_fingerprint", "fingerprint", unique=True),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    account_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    ownership_epoch: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    @classmethod
    def fingerprint_of(cls, provider: str, environment: str, external_account_id: str) -> str:
        material = (
            f"{provider.lower()}:{environment}:{external_account_id.strip().lower()}".encode()
        )
        return hashlib.sha256(material).hexdigest()

    @property
    def masked_external_id(self) -> str:
        """`ext-…a1b2` — display-safe; the raw external id is not stored here."""
        return f"{self.provider}/…{self.fingerprint[-4:]}"


def default_egress_allowlist(provider: str) -> str:
    """Known provider egress defaults (A04 control; newline-joined hosts)."""
    catalog = {
        "mock": ["mock.local"],
        "alpaca": ["*.alpaca.markets"],
    }
    return "\n".join(catalog.get(provider, []))
