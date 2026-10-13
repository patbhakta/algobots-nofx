"""Secret resolution grants (A04).

The :class:`SecretResolver` contract is the ACL surface between an account's
sealed credential blob and the single execution identity allowed to open it.
It carries references only — never secret material. Rotation bumps
``secret_version`` in place (the same ownership record), revocation moves the
grant to ``REVOKED`` and freezes the account pending reconciliation.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import Field, model_validator

from . import registry
from .base import Identifier, UtcDatetime, VersionedContract
from .enums import RuntimeEnvironment

__all__ = [
    "EgressHost",
    "ROTATION_POLICIES",
    "SecretResolver",
    "SecretState",
    "SecretRefText",
]

# secret://tenant/<tenant-id>/account/<account-id>
SecretRefText = Annotated[str, Field(pattern=r"^secret://tenant/[A-Za-z0-9._:/#@-]+/account/[A-Za-z0-9._:/#@-]+$")]
EgressHost = Annotated[
    str, Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.*-]+(\.[A-Za-z0-9*-]+)*$")
]
SecretState = Literal["ACTIVE", "ROTATED", "REVOKED", "EXPIRED"]
ROTATION_POLICIES = ("manual", "scheduled", "on-refresh")  # type: ignore[assignment]


@registry.register
class SecretResolver(VersionedContract):
    """One resolution grant: which execution identity may open which secret.

    Enforcement lives in :mod:`algobots.secrets.service` — tenant scope and
    principal identity must both match, the grant must be in a resolvable
    state, and every allow/deny is audited without secret material.
    """

    contract_name: ClassVar[str] = "SecretResolver"
    contract_version: ClassVar[str] = "1.0"

    grant_id: Identifier
    secret_ref: SecretRefText
    tenant_id: Identifier
    account_id: Identifier
    assigned_principal_id: Identifier
    allowed_environments: tuple[RuntimeEnvironment, ...]
    egress_allowlist: tuple[EgressHost, ...]
    rotation_policy: Literal["manual", "scheduled", "on-refresh"]
    state: SecretState
    secret_version: Annotated[int, Field(ge=1)]
    granted_by: Identifier
    created_at: UtcDatetime
    rotated_at: UtcDatetime | None = None
    revoked_at: UtcDatetime | None = None

    @model_validator(mode="after")
    def _state_timestamps(self) -> SecretResolver:
        if self.state == "ACTIVE" and (self.rotated_at or self.revoked_at):
            raise ValueError("ACTIVE grants carry no rotated_at/revoked_at")
        if self.state == "ROTATED" and self.rotated_at is None:
            raise ValueError("ROTATED grants require rotated_at")
        if self.state == "REVOKED" and self.revoked_at is None:
            raise ValueError("REVOKED grants require revoked_at")
        if self.state == "EXPIRED" and self.revoked_at is not None:
            raise ValueError("EXPIRED grants are swept, not revoked")
        if not self.allowed_environments:
            raise ValueError("a grant without environments resolves nothing")
        return self

    def resolvable_in(self, environment: RuntimeEnvironment) -> bool:
        return self.state in ("ACTIVE", "ROTATED") and environment in self.allowed_environments
