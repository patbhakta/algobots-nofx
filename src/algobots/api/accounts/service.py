"""Account-registry service: encrypted credential CRUD + token-health sweep.

Sweep contract (silent-refresh-or-expire): for every account holding
credentials in `active` token state, a token that is missing an expiry or
expires after `now + margin` is healthy; a token inside the margin is silently
refreshed through the broker's registered refresher and re-sealed encrypted.
Accounts with no refresher, a failing refresher, or an undecryptable blob are
marked `expired` with a redacted error and never abort the sweep.

Logging discipline: this module logs account ids, brokers, and outcomes only.
Plaintext secrets never enter log calls; error text passes through `redact`
with every decrypted secret value before it is stored or logged.
"""

import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from algobots.api.accounts.crypto import get_credential_cipher, redact
from algobots.api.accounts.models import AccountCredential
from algobots.api.accounts.refresh import TokenRefresher
from algobots.api.accounts.schemas import CredentialSet, TokenSweepReport
from algobots.api.config import get_settings
from algobots.api.models import Account

logger = logging.getLogger("algobots.api.accounts.service")

TOKEN_ACTIVE = "active"
TOKEN_EXPIRED = "expired"


def _as_aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; normalize to UTC-aware for comparison."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def set_credentials(db: Session, account: Account, secrets: CredentialSet) -> AccountCredential:
    """Create or replace the encrypted credential blob for one account."""
    cipher = get_credential_cipher()
    row = db.scalar(select(AccountCredential).where(AccountCredential.account_id == account.id))
    if row is None:
        row = AccountCredential(account_id=account.id, user_id=account.user_id)
        db.add(row)
    row.encrypted_secrets = cipher.encrypt(secrets.model_dump(mode="json"))
    row.key_id = cipher.key_id
    row.token_status = TOKEN_ACTIVE
    row.token_expires_at = secrets.token_expires_at
    row.last_refresh_error = ""
    db.commit()
    logger.info(
        "credentials_stored account_id=%s broker=%s mode=%s",
        account.id,
        account.broker,
        account.mode,
    )
    return row


def get_credential_row(db: Session, account_id: UUID) -> AccountCredential | None:
    """Fetch the raw credential row (tenant check happens at the router)."""
    return db.scalar(select(AccountCredential).where(AccountCredential.account_id == account_id))


def get_decrypted_secrets(db: Session, account_id: UUID) -> dict[str, Any] | None:
    """Decrypt the stored blob, or None when absent/undecryptable."""
    row = get_credential_row(db, account_id)
    if row is None:
        return None
    return get_credential_cipher().try_decrypt(row.encrypted_secrets)


def clear_credentials(db: Session, account_id: UUID) -> bool:
    """Delete the stored blob; True when a row was removed."""
    row = get_credential_row(db, account_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def sweep_token_health(
    db: Session,
    *,
    user_id: UUID | None = None,
    now: datetime | None = None,
    refresh_margin: timedelta | None = None,
    refreshers: Mapping[str, TokenRefresher] | None = None,
) -> TokenSweepReport:
    """Run one silent-refresh-or-expire pass; per-account failures never raise."""
    now = _as_aware(now or datetime.now(UTC))
    margin = refresh_margin or timedelta(seconds=get_settings().token_refresh_margin_seconds)
    registry = refreshers if refreshers is not None else _global_registry()

    query = (
        select(AccountCredential, Account)
        .join(Account, AccountCredential.account_id == Account.id)
        .where(AccountCredential.token_status == TOKEN_ACTIVE)
        .order_by(AccountCredential.created_at)
    )
    if user_id is not None:
        query = query.where(AccountCredential.user_id == user_id)

    checked = healthy = refreshed = expired = failed = 0
    expired_account_ids: list[UUID] = []

    for row, account in db.execute(query).all():
        checked += 1
        plain_secrets: dict[str, Any] | None = None
        try:
            expires = _as_aware(row.token_expires_at) if row.token_expires_at is not None else None
            if expires is None or expires > now + margin:
                healthy += 1
                continue

            refresher = registry.get(account.broker.strip().lower())
            if refresher is None:
                expired += 1
                expired_account_ids.append(account.id)
                row.token_status = TOKEN_EXPIRED
                row.last_refresh_error = (
                    f"no token refresher registered for broker '{account.broker}'"
                )
                logger.info(
                    "token_expired account_id=%s broker=%s reason=no_refresher",
                    account.id,
                    account.broker,
                )
                continue

            cipher = get_credential_cipher()
            plain_secrets = cipher.try_decrypt(row.encrypted_secrets)
            if plain_secrets is None:
                expired += 1
                expired_account_ids.append(account.id)
                row.token_status = TOKEN_EXPIRED
                row.last_refresh_error = "decryption failed (key mismatch or corrupt blob)"
                logger.warning(
                    "token_expired account_id=%s broker=%s reason=undecryptable_blob",
                    account.id,
                    account.broker,
                )
                continue

            outcome = refresher(account, plain_secrets)
            plain_secrets["token"] = outcome.token
            if outcome.token_expires_at is not None:
                plain_secrets["token_expires_at"] = outcome.token_expires_at.isoformat()
            if outcome.api_secret is not None:
                plain_secrets["api_secret"] = outcome.api_secret

            row.encrypted_secrets = cipher.encrypt(plain_secrets)
            row.key_id = cipher.key_id
            row.token_expires_at = outcome.token_expires_at
            row.token_status = TOKEN_ACTIVE
            row.last_refreshed_at = now
            row.last_refresh_error = ""
            refreshed += 1
            logger.info(
                "token_refreshed account_id=%s broker=%s",
                account.id,
                account.broker,
            )
        except Exception as exc:  # noqa: BLE001 — one bad account must not kill the sweep
            failed += 1
            expired_account_ids.append(account.id)
            row.token_status = TOKEN_EXPIRED
            known_secrets = [v for v in (plain_secrets or {}).values() if isinstance(v, str) and v]
            row.last_refresh_error = redact(f"{type(exc).__name__}: {exc}", *known_secrets)
            logger.warning(
                "token_refresh_failed account_id=%s broker=%s error=%s",
                account.id,
                account.broker,
                row.last_refresh_error,
            )
        finally:
            row.last_checked_at = now

    db.commit()
    logger.info(
        "token_sweep_complete checked=%d healthy=%d refreshed=%d expired=%d failed=%d",
        checked,
        healthy,
        refreshed,
        expired,
        failed,
    )
    return TokenSweepReport(
        checked=checked,
        healthy=healthy,
        refreshed=refreshed,
        expired=expired,
        failed=failed,
        checked_at=now,
        expired_account_ids=expired_account_ids,
    )


def _global_registry() -> dict[str, TokenRefresher]:
    from algobots.api.accounts.refresh import REFRESHERS

    return REFRESHERS
