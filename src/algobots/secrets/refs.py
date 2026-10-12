"""Canonical secret references: ``secret://tenant/<tenant-id>/account/<account-id>``.

References are the only credential handle that crosses a boundary (API
responses, contracts, job payloads). They are opaque, contain no secret
material, and always name both the owning tenant and the account — so a
mismatched reference is detectable before any blob is opened.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

_SECRET_REF = re.compile(r"^secret://tenant/([0-9a-fA-F-]{36})/account/([0-9a-fA-F-]{36})$")


class SecretRefError(ValueError):
    """The text is not a canonical secret reference for a known account."""


@dataclass(frozen=True)
class SecretRef:
    tenant_id: UUID
    account_id: UUID

    def __str__(self) -> str:
        return build_secret_ref(self.tenant_id, self.account_id)


def build_secret_ref(tenant_id: UUID, account_id: UUID) -> str:
    return f"secret://tenant/{tenant_id}/account/{account_id}"


def parse_secret_ref(text: str) -> SecretRef:
    match = _SECRET_REF.fullmatch(text or "")
    if match is None:
        raise SecretRefError(f"not a canonical secret reference: {text!r}")
    return SecretRef(tenant_id=UUID(match.group(1)), account_id=UUID(match.group(2)))
