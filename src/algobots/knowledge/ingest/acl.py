"""Tenant/source ACLs for the knowledge surface (A14-2, on A03 tenancy).

Two permission classes govern reads (packet law: authored knowledge and
engineering documentation are separate classes):

- ``authored_knowledge`` — the vault's authored research notes. Readable by
  every active member (viewer and up).
- ``engineering_docs`` — engineering documentation (runbooks, wiring,
  operational detail). Readable by member and owner only; viewers are denied
  by default, mirroring A03's rule that viewers never act and see the least.

Syncing a source (re-running ingest + indexing) is a write: member and up.
Removing a source (tombstone + ACL revocation) is destructive: owner only.

The role values are A03's ``TenantRole`` values carried on the authenticated
session's active membership; unknown roles are denied (default deny), exactly
like ``algobots.api.auth.policy.is_allowed``. This module stays stdlib-only:
it maps roles to knowledge actions and persists per-source ACL records; the
A03 layer (``get_tenant_context``) is what proves the role is real.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from algobots.knowledge.ingest.models import utcnow_iso


class PermissionClass(StrEnum):
    AUTHORED_KNOWLEDGE = "authored_knowledge"
    ENGINEERING_DOCS = "engineering_docs"


class KnowledgeAction(StrEnum):
    READ_AUTHORED = "knowledge.read_authored"
    READ_ENGINEERING = "knowledge.read_engineering"
    SYNC = "knowledge.sync"
    REMOVE_SOURCE = "knowledge.remove_source"


# Role -> allowed knowledge actions. Roles are A03 TenantRole values; rows
# missing from the matrix are denied (default deny).
KNOWLEDGE_ROLE_MATRIX: dict[str, frozenset[KnowledgeAction]] = {
    "owner": frozenset(KnowledgeAction),
    "member": frozenset(
        {KnowledgeAction.READ_AUTHORED, KnowledgeAction.READ_ENGINEERING, KnowledgeAction.SYNC}
    ),
    "viewer": frozenset({KnowledgeAction.READ_AUTHORED}),
}

READ_ACTION_FOR_CLASS: dict[PermissionClass, KnowledgeAction] = {
    PermissionClass.AUTHORED_KNOWLEDGE: KnowledgeAction.READ_AUTHORED,
    PermissionClass.ENGINEERING_DOCS: KnowledgeAction.READ_ENGINEERING,
}


def allowed(role: str | None, action: KnowledgeAction) -> bool:
    """True only for a matrix row that contains the action (default deny)."""
    if role is None:
        return False
    return action in KNOWLEDGE_ROLE_MATRIX.get(role, frozenset())


def can_read_class(role: str | None, permission_class: PermissionClass) -> bool:
    return allowed(role, READ_ACTION_FOR_CLASS[permission_class])


@dataclass
class SourceAcl:
    """Per-source access record: the permission class plus revocation state.

    ``revoked_at`` is None while the ACL is live. A revoked ACL denies reads
    for every role including owner — revocation is removal's teeth, and the
    only way back is an explicit restore (auditable, never implicit).
    """

    source_id: str
    permission_class: str = PermissionClass.AUTHORED_KNOWLEDGE.value
    revoked_at: str | None = None
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.updated_at:
            self.updated_at = utcnow_iso()

    @property
    def permission(self) -> PermissionClass:
        return PermissionClass(self.permission_class)

    @property
    def live(self) -> bool:
        return self.revoked_at is None

    def to_json(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "permission_class": self.permission_class,
            "revoked_at": self.revoked_at,
            "updated_at": self.updated_at,
        }


def acl_from_json(data: dict[str, Any]) -> SourceAcl:
    return SourceAcl(
        source_id=data["source_id"],
        permission_class=data.get("permission_class", PermissionClass.AUTHORED_KNOWLEDGE.value),
        revoked_at=data.get("revoked_at"),
        updated_at=data.get("updated_at", ""),
    )


def default_acl(source_id: str) -> SourceAcl:
    """Unregistered sources default to the authored-knowledge class."""
    return SourceAcl(source_id=source_id)
