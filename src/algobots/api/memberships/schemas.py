"""Request/response schemas for tenants, memberships, invites and grants."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from algobots.api.schemas import ORMModel


class TenantOut(BaseModel):
    id: UUID
    name: str
    role: str
    personal: bool
    active: bool


class MeOut(BaseModel):
    id: UUID
    email: EmailStr
    display_name: str
    tenant_id: UUID | None
    role: str | None
    tenants: list[TenantOut]
    grants: list[str]


class MembershipOut(ORMModel):
    id: UUID
    tenant_id: UUID
    user_id: UUID
    role: str
    status: str
    created_at: datetime
    revoked_at: datetime | None


class MembershipUpdate(BaseModel):
    role: str = Field(min_length=1, max_length=16)


class InviteCreate(BaseModel):
    email: EmailStr
    role: str = Field(default="member", min_length=1, max_length=16)


class TenantInviteOut(ORMModel):
    id: UUID
    tenant_id: UUID
    email: EmailStr
    role: str
    expires_at: datetime
    redeemed_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class TenantInviteCreated(TenantInviteOut):
    # Plaintext token: returned exactly once, never stored or listed.
    token: str


class InviteRedeem(BaseModel):
    token: str = Field(min_length=8, max_length=128)


class GrantCreate(BaseModel):
    account_id: UUID
    grant: str = Field(min_length=1, max_length=32)


class GrantOut(ORMModel):
    id: UUID
    tenant_id: UUID
    account_id: UUID
    user_id: UUID
    grant: str
    created_at: datetime
