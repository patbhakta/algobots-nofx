"""Tenant-scoped credential routes + token-health sweep trigger (S4.1).

Every route filters by the authenticated user; another tenant's rows are
indistinguishable from missing rows (404). Responses expose token health
only — sealed secrets are write-only from the API's point of view.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from algobots.api.accounts.schemas import CredentialHealthOut, CredentialSet, TokenSweepReport
from algobots.api.accounts.service import (
    clear_credentials,
    get_credential_row,
    set_credentials,
    sweep_token_health,
)
from algobots.api.database import get_db
from algobots.api.dependencies import get_current_user
from algobots.api.models import Account, User

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _audit(response: Response, resource: str, resource_id: UUID | None) -> None:
    response.headers["X-Audit-Resource"] = resource
    if resource_id is not None:
        response.headers["X-Audit-Resource-Id"] = str(resource_id)


def _owned_account_or_404(db: Session, current_user: User, account_id: UUID) -> Account:
    account = db.get(Account, account_id)
    if account is None or account.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return account


def _health_out(account_id: UUID, row) -> CredentialHealthOut:
    if row is None:
        return CredentialHealthOut(account_id=account_id)
    return CredentialHealthOut(
        account_id=account_id,
        token_status=row.token_status,
        token_expires_at=row.token_expires_at,
        last_refreshed_at=row.last_refreshed_at,
        last_checked_at=row.last_checked_at,
        last_refresh_error=row.last_refresh_error or None,
        key_id=row.key_id or None,
        stored_at=row.created_at,
    )


@router.put("/{account_id}/credentials", response_model=CredentialHealthOut)
def replace_credentials(
    account_id: UUID,
    payload: CredentialSet,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CredentialHealthOut:
    """Provision or replace the account's encrypted credentials (write-only)."""
    account = _owned_account_or_404(db, current_user, account_id)
    row = set_credentials(db, account, payload)
    _audit(response, "account_credentials", row.id)
    return _health_out(account.id, row)


@router.get("/{account_id}/credentials/health", response_model=CredentialHealthOut)
def credential_health(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CredentialHealthOut:
    """Secret-free token-health view for one account."""
    _owned_account_or_404(db, current_user, account_id)
    return _health_out(account_id, get_credential_row(db, account_id))


@router.delete("/{account_id}/credentials", status_code=status.HTTP_204_NO_CONTENT)
def delete_credentials(
    account_id: UUID,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Forget the stored credentials for one account."""
    _owned_account_or_404(db, current_user, account_id)
    removed = clear_credentials(db, account_id)
    _audit(response, "account_credentials", account_id if removed else None)


@router.post("/token-sweep", response_model=TokenSweepReport)
def run_token_sweep(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TokenSweepReport:
    """Sweep the caller's accounts: silent-refresh-or-expire, never crashes."""
    report = sweep_token_health(db, user_id=current_user.id)
    _audit(response, "account_credentials", None)
    return report
