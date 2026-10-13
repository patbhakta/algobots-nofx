"""Broker-account onboarding (A04 checklist 1-2, 5).

One call produces the full registry shape for an account: the tenant-scoped
``accounts`` row, its sealed ``account_credentials`` blob, the
``broker_connections`` session/config row and the globally-unique
``external_account_identities`` fingerprint. Duplicate external accounts are
rejected with a generic conflict that never names the owning tenant.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from algobots.api.accounts.crypto import get_credential_cipher
from algobots.api.accounts.models import (
    BrokerConnection,
    ExternalAccountIdentity,
)
from algobots.api.accounts.providers import (
    UnknownProviderError,
    capabilities_for,
    default_egress_hosts,
    environment_allowed_for_onboarding,
    provider_config,
)
from algobots.api.accounts.schemas import CredentialSet
from algobots.api.models import Account

logger = logging.getLogger("algobots.api.accounts.onboarding")


class DuplicateExternalAccountError(Exception):
    """The external account is already connected somewhere; owner is not revealed."""


class OnboardingRejected(ValueError):
    """The provider/environment/product combination is not onboardable in A04."""


def onboard_broker_account(
    db: Session,
    *,
    tenant_id: UUID,
    user_id: UUID,
    label: str,
    provider: str,
    environment: str,
    external_account_id: str,
    credentials: CredentialSet,
    base_currency: str = "USD",
    mode: str = "paper",
) -> tuple[Account, BrokerConnection, ExternalAccountIdentity]:
    """Create account + sealed credentials + connection + external identity."""
    try:
        config = provider_config(provider)
    except UnknownProviderError as exc:
        raise OnboardingRejected(str(exc)) from exc
    provider = config.slug
    if not environment_allowed_for_onboarding(config, environment):
        raise OnboardingRejected(
            f"provider {provider!r} cannot onboard environment {environment!r} in A04"
        )
    try:
        statement = capabilities_for(provider, environment)
    except UnknownProviderError as exc:
        raise OnboardingRejected(str(exc)) from exc
    if not external_account_id.strip():
        raise OnboardingRejected("external_account_id is required")

    fingerprint = ExternalAccountIdentity.fingerprint_of(provider, environment, external_account_id)
    existing = db.scalar(
        select(ExternalAccountIdentity).where(ExternalAccountIdentity.fingerprint == fingerprint)
    )
    if existing is not None:
        # Generic conflict: no owner identity, no tenant, no account id of the
        # existing holder ever crosses this boundary (A04 checklist 5).
        raise DuplicateExternalAccountError(
            "this external account is already connected; ownership transfer is a reviewed workflow"
        )

    account = Account(
        tenant_id=tenant_id,
        user_id=user_id,
        label=label,
        broker=provider,
        mode=mode,
        base_currency=base_currency,
        status="active",
    )
    db.add(account)
    db.flush()

    cipher = get_credential_cipher()
    from algobots.api.accounts.models import AccountCredential

    db.add(
        AccountCredential(
            account_id=account.id,
            user_id=user_id,
            encrypted_secrets=cipher.encrypt(credentials.model_dump(mode="json")),
            key_id=cipher.key_id,
            token_status="active",
            token_expires_at=credentials.token_expires_at,
        )
    )

    hosts = default_egress_hosts(provider)
    connection = BrokerConnection(
        tenant_id=tenant_id,
        account_id=account.id,
        user_id=user_id,
        provider=provider,
        environment=environment,
        session_state="CONNECTED" if config.kind == "mock" else "UNCONFIGURED",
        egress_allowlist="\n".join(hosts),
        capabilities_revision=statement.revision,
        sandbox_fidelity=statement.sandbox_fidelity,
        session_checked_at=datetime.now(UTC) if config.kind == "mock" else None,
    )
    db.add(connection)
    db.add(
        ExternalAccountIdentity(
            tenant_id=tenant_id,
            account_id=account.id,
            user_id=user_id,
            provider=provider,
            environment=environment,
            fingerprint=fingerprint,
        )
    )

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        # Fingerprint race: the unique index caught a concurrent duplicate.
        logger.info(
            "external_account_duplicate provider=%s environment=%s (race)",
            provider,
            environment,
        )
        raise DuplicateExternalAccountError(
            "this external account is already connected; ownership transfer is a reviewed workflow"
        ) from exc

    logger.info(
        "broker_account_onboarded account_id=%s provider=%s environment=%s kind=%s",
        account.id,
        provider,
        environment,
        config.kind,
    )
    return account, connection, db.scalar(
        select(ExternalAccountIdentity).where(ExternalAccountIdentity.account_id == account.id)
    )
