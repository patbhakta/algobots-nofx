"""Pydantic schemas for credential storage and token-health reporting."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CredentialSet(BaseModel):
    """Broker secrets supplied once at provisioning; never serialized back out."""

    api_key: str = Field(min_length=1, max_length=512)
    api_secret: str = Field(min_length=1, max_length=512)
    token: str | None = Field(default=None, max_length=4096)
    token_expires_at: datetime | None = None


class CredentialHealthOut(BaseModel):
    """Secret-free view of one account's credential/token state."""

    model_config = ConfigDict(from_attributes=True)

    account_id: UUID
    token_status: str | None = None
    token_expires_at: datetime | None = None
    last_refreshed_at: datetime | None = None
    last_checked_at: datetime | None = None
    last_refresh_error: str | None = None
    key_id: str | None = None
    stored_at: datetime | None = None


class TokenSweepReport(BaseModel):
    """Aggregated, secret-free outcome of one token-health sweep."""

    checked: int
    healthy: int
    refreshed: int
    expired: int
    failed: int
    checked_at: datetime
    expired_account_ids: list[UUID]
