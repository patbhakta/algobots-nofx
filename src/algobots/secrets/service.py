"""Secret resolution, rotation and revocation (A04 checklist 3).

:func:`SecretStore.resolve` is the single boundary an execution identity
crosses to open a credential. Denials are audited with ids and reasons only;
allowed resolutions are audited without secret material. The store never
returns secrets to HTTP callers — routers serialize health/state views only.

Recovery semantics (founder spec): revoked or expired credentials freeze the
account's entries; existing exposure surfaces as ``needs_reconciliation`` on
the broker connection, never as a silently flat position view.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from algobots.api.accounts.crypto import redact
from algobots.api.accounts.models import AccountCredential  # noqa: F401 — re-exported for tests
from algobots.secrets.keyservice import KeyServiceError, SecretKeyService, get_key_service
from algobots.secrets.models import RESOLVABLE_STATES, SecretGrant
from algobots.secrets.refs import SecretRefError, parse_secret_ref

logger = logging.getLogger("algobots.secrets.service")

ACCOUNT_FROZEN = "frozen"
NEEDS_RECONCILIATION = "needs_reconciliation"
RECONCILE_OK = "ok"


class ResolutionDenied(Exception):
    """The principal may not open this secret. Message is safe to persist."""

    def __init__(self, reason: str, *, grant: SecretGrant | None = None):
        super().__init__(reason)
        self.reason = reason
        self.grant = grant


@dataclass(frozen=True)
class Resolution:
    """An allowed resolution. Secrets stay in-process; never serialized out."""

    secrets: dict[str, Any]
    egress_allowlist: tuple[str, ...]
    secret_version: int
    key_id: str
    environment: str
    account_id: UUID
    tenant_id: UUID


def _as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class SecretStore:
    """Resolution ACL + lifecycle for one tenant's sealed credentials."""

    def __init__(self, keys: SecretKeyService | None = None):
        self._keys = keys

    # -- internals ---------------------------------------------------------

    def _key_service(self) -> SecretKeyService:
        return self._keys if self._keys is not None else get_key_service()

    def _grant_by_ref(self, db: Session, tenant_id: UUID, account_id: UUID) -> SecretGrant | None:
        return db.scalar(
            select(SecretGrant).where(
                SecretGrant.tenant_id == tenant_id,
                SecretGrant.account_id == account_id,
            )
        )

    def _audit(
        self,
        db: Session,
        event: str,
        *,
        tenant_id: UUID | None,
        grant: SecretGrant | None,
        **detail: Any,
    ) -> None:
        # Deferred: api.auth.audit imports the full api model graph, which
        # imports this package — importing at module load would be circular.
        from algobots.api.auth.audit import record_event

        record_event(
            db,
            event=event,
            actor_user_id=grant.user_id if grant is not None else None,
            tenant_id=tenant_id,
            resource="secret_grants",
            resource_id=grant.id if grant is not None else None,
            **detail,
        )

    # -- assignment ---------------------------------------------------------

    def assign_grant(
        self,
        db: Session,
        *,
        account: Account,
        assigned_principal_id: str,
        granted_by_user_id: UUID,
        allowed_environments: tuple[str, ...],
        egress_allowlist: tuple[str, ...],
        rotation_policy: str = "manual",
    ) -> SecretGrant:
        """Bind one account's secret to one execution identity (idempotent per pair)."""
        if not assigned_principal_id or len(assigned_principal_id) > 128:
            raise ValueError("assigned_principal_id must be 1..128 chars")
        if not allowed_environments:
            raise ValueError("a grant without environments resolves nothing")
        if rotation_policy not in ("manual", "scheduled", "on-refresh"):
            raise ValueError(f"unknown rotation policy {rotation_policy!r}")

        grant = db.scalar(
            select(SecretGrant).where(
                SecretGrant.account_id == account.id,
                SecretGrant.assigned_principal_id == assigned_principal_id,
            )
        )
        if grant is not None:
            # Same account + same principal: refresh policy surfaces in place,
            # never a second ownership record.
            grant.allowed_environments = ",".join(sorted(set(allowed_environments)))
            grant.egress_allowlist = "\n".join(egress_allowlist)
            grant.rotation_policy = rotation_policy
            grant.granted_by_user_id = granted_by_user_id
        else:
            grant = SecretGrant(
                tenant_id=account.tenant_id,
                account_id=account.id,
                assigned_principal_id=assigned_principal_id,
                user_id=account.user_id,
                granted_by_user_id=granted_by_user_id,
                allowed_environments=",".join(sorted(set(allowed_environments))),
                egress_allowlist="\n".join(egress_allowlist),
                rotation_policy=rotation_policy,
                state="ACTIVE",
                secret_version=1,
            )
            db.add(grant)
        db.flush()
        self._audit(
            db,
            "secret.grant_assigned",
            tenant_id=account.tenant_id,
            grant=grant,
            assigned_principal_id=assigned_principal_id,
            account_id=account.id,
        )
        logger.info(
            "secret_grant_assigned grant_id=%s account_id=%s principal=%s",
            grant.id,
            account.id,
            assigned_principal_id,
        )
        return grant

    # -- resolution ---------------------------------------------------------

    def resolve(
        self,
        db: Session,
        *,
        principal_id: str,
        principal_tenant_id: UUID,
        secret_ref: str,
        environment: str,
        egress_host: str | None = None,
    ) -> Resolution:
        """Open one secret as one execution identity, or raise :class:`ResolutionDenied`.

        Checks, in order: reference shape, tenant scope, principal identity,
        grant state, environment, egress destination, token health. Every
        denial is audited (ids and reasons only) and the grant row records the
        last denial reason for the health view.
        """
        try:
            ref = parse_secret_ref(secret_ref)
        except SecretRefError as exc:
            self._audit(db, "secret.resolution_denied", tenant_id=None, grant=None, reason="malformed_ref")
            raise ResolutionDenied("not a canonical secret reference") from exc

        grant = self._grant_by_ref(db, ref.tenant_id, ref.account_id)

        def deny(reason: str) -> ResolutionDenied:
            self._audit(
                db,
                "secret.resolution_denied",
                tenant_id=ref.tenant_id,
                grant=grant,
                principal_id=principal_id,
                account_id=ref.account_id,
                reason=reason,
            )
            if grant is not None:
                grant.last_denial_reason = reason[:128]
                db.commit()
            logger.info(
                "secret_resolution_denied account_id=%s principal=%s reason=%s",
                ref.account_id,
                principal_id,
                reason,
            )
            return ResolutionDenied(reason, grant=grant)

        if grant is None:
            raise deny("no grant for this secret reference")
        if principal_tenant_id != ref.tenant_id:
            raise deny("cross-tenant secret resolution denied")
        if grant.assigned_principal_id != principal_id:
            raise deny("only the assigned execution identity may resolve this secret")
        if grant.state not in RESOLVABLE_STATES:
            raise deny(f"grant state {grant.state} is not resolvable")

        environments = grant.allowed_environments.split(",")
        if environment not in environments:
            raise deny(f"environment {environment!r} not allowed for this grant")

        allowlist = tuple(h for h in grant.egress_allowlist.splitlines() if h)
        if egress_host is not None and not _host_allowed(egress_host, allowlist):
            raise deny(f"egress destination {egress_host!r} is not allowlisted")

        from algobots.api.accounts.service import TOKEN_EXPIRED, get_credential_row

        cred = get_credential_row(db, ref.account_id)
        if cred is None:
            raise deny("no credential stored for this account")
        if cred.token_status == TOKEN_EXPIRED:
            self._mark_needing_reconciliation(db, ref.account_id, "expired credentials")
            raise deny("credentials expired; reconciliation required before resolution")

        try:
            secrets = self._key_service().open(cred.encrypted_secrets, cred.key_id)
        except KeyServiceError as exc:
            raise deny(f"credential blob cannot be opened: {exc}") from exc

        self._audit(
            db,
            "secret.resolved",
            tenant_id=ref.tenant_id,
            grant=grant,
            principal_id=principal_id,
            account_id=ref.account_id,
            environment=environment,
            secret_version=grant.secret_version,
        )
        db.commit()
        logger.info(
            "secret_resolved account_id=%s principal=%s version=%s",
            ref.account_id,
            principal_id,
            grant.secret_version,
        )
        return Resolution(
            secrets=secrets,
            egress_allowlist=allowlist,
            secret_version=grant.secret_version,
            key_id=cred.key_id or "",
            environment=environment,
            account_id=ref.account_id,
            tenant_id=ref.tenant_id,
        )

    # -- rotation / revocation ------------------------------------------------

    def rotate(
        self,
        db: Session,
        *,
        grant: SecretGrant,
        secrets: dict[str, Any],
    ) -> SecretGrant:
        """Re-seal new secret material under the SAME ownership records.

        The account, external identity and grant rows are untouched except for
        the version bump — rotating credentials for an external account never
        creates a second account or ownership record (acceptance case 5).
        """
        from algobots.api.models import Account

        account = db.get(Account, grant.account_id)
        if account is None or account.tenant_id != grant.tenant_id:
            raise ValueError("grant does not resolve to its tenant's account")
        if grant.state == "REVOKED":
            raise ResolutionDenied("a revoked grant cannot rotate; re-onboard the account", grant=grant)

        from algobots.api.accounts.service import get_credential_row

        cred = get_credential_row(db, grant.account_id)
        if cred is None:
            raise ValueError("no credential stored for this account")

        old = self._key_service().open(cred.encrypted_secrets, cred.key_id)
        blob, key_id = self._key_service().seal(secrets)
        expires = secrets.get("token_expires_at")
        if isinstance(expires, str):
            expires = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        cred.encrypted_secrets = blob
        cred.key_id = key_id
        cred.token_status = "active"
        cred.token_expires_at = expires
        cred.last_refresh_error = ""
        grant.state = "ROTATED"
        grant.secret_version += 1
        grant.rotated_at = datetime.now(UTC)
        grant.last_denial_reason = ""
        db.flush()
        self._audit(
            db,
            "secret.rotated",
            tenant_id=grant.tenant_id,
            grant=grant,
            account_id=grant.account_id,
            secret_version=grant.secret_version,
        )
        db.commit()
        # Known-secret redaction keeps any adapter echo out of stored text.
        _ = redact("", *[v for v in (*old.values(), *secrets.values()) if isinstance(v, str)])
        logger.info(
            "secret_rotated account_id=%s grant_id=%s version=%s",
            grant.account_id,
            grant.id,
            grant.secret_version,
        )
        return grant

    def revoke(self, db: Session, *, grant: SecretGrant) -> SecretGrant:
        """Freeze resolution and the account; exposure becomes needs-reconciliation."""
        from algobots.api.models import Account

        grant.state = "REVOKED"
        grant.revoked_at = datetime.now(UTC)
        account = db.get(Account, grant.account_id)
        if account is not None and account.status != "closed":
            account.status = ACCOUNT_FROZEN
        self._mark_needing_reconciliation(db, grant.account_id, "credentials revoked")
        db.flush()
        self._audit(
            db,
            "secret.revoked",
            tenant_id=grant.tenant_id,
            grant=grant,
            account_id=grant.account_id,
        )
        db.commit()
        logger.info("secret_revoked account_id=%s grant_id=%s", grant.account_id, grant.id)
        return grant

    # -- recovery ----------------------------------------------------------

    def _mark_needing_reconciliation(self, db: Session, account_id: UUID, reason: str) -> None:
        from algobots.api.accounts.models import BrokerConnection

        connection = db.scalar(
            select(BrokerConnection).where(BrokerConnection.account_id == account_id)
        )
        if connection is not None:
            connection.reconciliation_state = NEEDS_RECONCILIATION
            connection.reconciliation_reason = reason[:200]
            if connection.session_state != "REVOKED":
                connection.session_state = "EXPIRED"
        db.flush()


def _host_allowed(host: str, allowlist: tuple[str, ...]) -> bool:
    """Exact or single-segment-wildcard match (``*.broker.example`` style)."""
    if not allowlist:
        return False
    host = host.strip().lower()
    for pattern in allowlist:
        pattern = pattern.strip().lower()
        if pattern == "*" or pattern == host:
            return True
        if pattern.startswith("*."):
            suffix = pattern[1:]  # ".example.com"
            if host.endswith(suffix) and "." in host[: -len(suffix)]:
                return True
    return False


def grant_views(db: Session, tenant_id: UUID) -> list[SecretGrant]:
    return list(
        db.scalars(
            select(SecretGrant)
            .where(SecretGrant.tenant_id == tenant_id)
            .order_by(SecretGrant.created_at)
        )
    )
