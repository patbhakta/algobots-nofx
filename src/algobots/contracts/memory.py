"""Memory record, namespaces and the ``MemoryStore`` platform interface.

Namespaces: ``engineering/project``, ``investment/shared``,
``investment/{tenant}/research``, ``investment/{tenant}/accounts/{account}``.
Build-agent identities reach only the engineering namespace; investment
identities never reach it. Tenant scope comes from the principal, not the
caller. ``MemoryStore`` method names are platform interfaces, not claimed
TencentDB SDK names.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Annotated, Any, ClassVar, Literal, Protocol, runtime_checkable

from pydantic import Field, model_validator

from . import registry
from .base import ContractModel, Identifier, Sha256Hex, UtcDatetime, VersionedContract
from .enums import EvidenceClass
from .identity import Grant, IdentityKind, Principal

__all__ = [
    "MemoryRecord",
    "MemoryScope",
    "MemoryStore",
    "namespace_permits",
    "parse_namespace",
]

_NAMESPACE = re.compile(
    r"^(?:engineering/project"
    r"|investment/shared"
    r"|investment/(?P<tenant>[A-Za-z0-9._-]+)/research"
    r"|investment/(?P<atenant>[A-Za-z0-9._-]+)/accounts/(?P<account>[A-Za-z0-9._-]+))$"
)


def parse_namespace(namespace: str) -> tuple[str | None, str | None]:
    """Return ``(tenant_id, account_id)`` encoded by ``namespace``; raise if malformed."""
    match = _NAMESPACE.match(namespace)
    if match is None:
        raise ValueError(f"unknown memory namespace {namespace!r}")
    return match["tenant"] or match["atenant"], match["account"]


def namespace_permits(principal: Principal, namespace: str, *, write: bool) -> bool:
    tenant, _ = parse_namespace(namespace)
    if namespace == "engineering/project":
        needed = Grant.ENGINEERING_MEMORY_WRITE if write else Grant.ENGINEERING_MEMORY_READ
        return principal.kind is IdentityKind.BUILD_AGENT and principal.has(needed)
    if principal.kind is IdentityKind.BUILD_AGENT:
        return False
    if namespace == "investment/shared":
        needed = Grant.MEMORY_PUBLISH_SHARED if write else Grant.INVESTMENT_MEMORY_READ
        return principal.has(needed)
    needed = Grant.INVESTMENT_MEMORY_WRITE if write else Grant.INVESTMENT_MEMORY_READ
    return principal.tenant_id == tenant and principal.has(needed)


@registry.register
class MemoryRecord(VersionedContract):
    contract_name: ClassVar[str] = "MemoryRecord"
    contract_version: ClassVar[str] = "1.0"

    record_id: Identifier
    version: Annotated[int, Field(ge=1)]
    namespace: str
    tenant_id: Identifier | None = None
    account_id: Identifier | None = None
    source_version: Identifier
    source_hash: Sha256Hex
    source_anchor: Identifier
    source_event_time: UtcDatetime
    available_at: UtcDatetime
    ingested_at: UtcDatetime
    instrument_id: Identifier | None = None
    horizon: Annotated[str, Field(pattern=r"^\d+(m|h|d|w)$")] | None = None
    regime_definition_version: Identifier | None = None
    revisions: dict[Literal["strategy", "data", "model", "question"], Identifier] = {}
    evidence_class: EvidenceClass
    approval_state: Literal["PROPOSED", "APPROVED", "REJECTED"]
    acl_revision: Annotated[int, Field(ge=0)]
    tombstoned: bool = False
    replaces_record_id: Identifier | None = None

    @model_validator(mode="after")
    def _scope_matches_namespace(self) -> MemoryRecord:
        tenant, account = parse_namespace(self.namespace)
        if (self.tenant_id, self.account_id) != (tenant, account):
            raise ValueError(
                f"tenant/account ({self.tenant_id}, {self.account_id}) do not match "
                f"namespace {self.namespace!r}"
            )
        if self.available_at > self.ingested_at:
            raise ValueError("available_at cannot be later than ingested_at")
        return self


class MemoryScope(ContractModel):
    """The namespaces a call may touch, derived from the authenticated principal."""

    principal: Principal
    namespaces: Annotated[tuple[str, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def _authorized(self) -> MemoryScope:
        denied = [
            ns for ns in self.namespaces if not namespace_permits(self.principal, ns, write=False)
        ]
        if denied:
            raise ValueError(f"principal {self.principal.principal_id} may not read {denied}")
        return self


@runtime_checkable
class MemoryStore(Protocol):
    """Platform memory interface; adapters (A15) implement it."""

    def upsert_version(
        self, record: MemoryRecord, expected_version: int | None
    ) -> MemoryRecord: ...

    def get(self, record_id: str, scope: MemoryScope, as_of: datetime) -> MemoryRecord | None: ...

    def search(
        self, query: str, scope: MemoryScope, filters: Mapping[str, Any], limit: int
    ) -> Sequence[MemoryRecord]: ...

    def tombstone(self, record_id: str, expected_version: int) -> MemoryRecord: ...

    def export_snapshot(
        self, scope: MemoryScope, watermark: datetime
    ) -> Sequence[MemoryRecord]: ...

    def health(self) -> Mapping[str, Any]: ...
