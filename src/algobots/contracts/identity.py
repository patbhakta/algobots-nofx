"""Separated principal identities (A01 checklist 4).

Execution, memory, research and build-agent identities are distinct kinds
with disjoint authority. A build agent never holds trading or investment
memory grants; a research/model identity never holds a trading grant
(roadmap: "Models cannot call this endpoint with a trading-authorized
identity").
"""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from pydantic import model_validator

from . import registry
from .base import Identifier, VersionedContract

__all__ = ["ALLOWED_GRANTS", "Grant", "IdentityKind", "Principal"]


class IdentityKind(StrEnum):
    USER = "USER"
    EXECUTION_SERVICE = "EXECUTION_SERVICE"
    MEMORY_SERVICE = "MEMORY_SERVICE"
    RESEARCH_AGENT = "RESEARCH_AGENT"
    BUILD_AGENT = "BUILD_AGENT"


class Grant(StrEnum):
    ACCOUNT_READ = "ACCOUNT_READ"
    TRADE_PAPER = "TRADE_PAPER"
    TRADE_LIVE = "TRADE_LIVE"
    APPROVE_PLAN = "APPROVE_PLAN"
    INVESTMENT_MEMORY_READ = "INVESTMENT_MEMORY_READ"
    INVESTMENT_MEMORY_WRITE = "INVESTMENT_MEMORY_WRITE"
    MEMORY_PUBLISH_SHARED = "MEMORY_PUBLISH_SHARED"
    ENGINEERING_MEMORY_READ = "ENGINEERING_MEMORY_READ"
    ENGINEERING_MEMORY_WRITE = "ENGINEERING_MEMORY_WRITE"
    REPO_WRITE = "REPO_WRITE"
    TASK_CLAIM = "TASK_CLAIM"


G = Grant
ALLOWED_GRANTS: dict[IdentityKind, frozenset[Grant]] = {
    IdentityKind.USER: frozenset(
        {
            G.ACCOUNT_READ,
            G.TRADE_PAPER,
            G.TRADE_LIVE,
            G.APPROVE_PLAN,
            G.INVESTMENT_MEMORY_READ,
            G.INVESTMENT_MEMORY_WRITE,
            G.MEMORY_PUBLISH_SHARED,
        }
    ),
    IdentityKind.EXECUTION_SERVICE: frozenset({G.ACCOUNT_READ, G.TRADE_PAPER, G.TRADE_LIVE}),
    IdentityKind.MEMORY_SERVICE: frozenset({G.INVESTMENT_MEMORY_READ, G.INVESTMENT_MEMORY_WRITE}),
    IdentityKind.RESEARCH_AGENT: frozenset(
        {G.ACCOUNT_READ, G.INVESTMENT_MEMORY_READ, G.INVESTMENT_MEMORY_WRITE}
    ),
    IdentityKind.BUILD_AGENT: frozenset(
        {G.REPO_WRITE, G.TASK_CLAIM, G.ENGINEERING_MEMORY_READ, G.ENGINEERING_MEMORY_WRITE}
    ),
}


@registry.register
class Principal(VersionedContract):
    """An authenticated identity. Tenant scope is derived from it, never from user input."""

    contract_name: ClassVar[str] = "Principal"
    contract_version: ClassVar[str] = "1.0"

    principal_id: Identifier
    kind: IdentityKind
    tenant_id: Identifier | None
    grants: tuple[Grant, ...]

    @model_validator(mode="after")
    def _grants_fit_kind(self) -> Principal:
        if len(set(self.grants)) != len(self.grants):
            raise ValueError("duplicate grants")
        forbidden = sorted(set(self.grants) - ALLOWED_GRANTS[self.kind])
        if forbidden:
            raise ValueError(f"{self.kind} identities cannot hold {', '.join(forbidden)}")
        if self.kind is IdentityKind.BUILD_AGENT and self.tenant_id is not None:
            raise ValueError("build-agent identities are not tenant-scoped")
        if self.kind is not IdentityKind.BUILD_AGENT and self.tenant_id is None:
            raise ValueError(f"{self.kind} identities require a tenant_id")
        return self

    def has(self, grant: Grant) -> bool:
        return grant in self.grants
