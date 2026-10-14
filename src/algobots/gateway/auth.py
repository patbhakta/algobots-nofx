"""Who is calling, and which accounts are theirs.

P1.1 needs the 401/403 boundary to exist and be testable; P2.1 replaces the
session lookup with NoFX's own session verification. The seam is
:class:`Sessions`, and the default implementation knows no sessions at all —
an unconfigured gateway answers ``401`` to everything rather than falling back
to an implicit principal. A gateway that cannot identify the caller has no
business reading an account.

The grant check is the demo's rule (ALG-3260) restated: the account scope is
resolved on the server for every request, never inferred from navigation, and
an ungranted account is refused even when the caller names it explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from algobots.gateway.errors import (
    NO_SESSION,
    NOT_GRANTED,
    UNKNOWN_ACCOUNT,
    GatewayError,
)
from algobots.gateway.nodes import NodeRegistry


@dataclass(frozen=True)
class Caller:
    """An authenticated principal and the accounts it is granted."""

    principal_id: str
    accounts: tuple[str, ...]


class Sessions(Protocol):
    """Bearer token -> caller, or ``None`` for no (or expired) session."""

    def caller(self, token: str | None) -> Caller | None: ...


@dataclass(frozen=True)
class NoSessions:
    """The fail-closed default: nobody is authenticated."""

    def caller(self, token: str | None) -> Caller | None:
        return None


@dataclass(frozen=True)
class StaticSessions:
    """Tokens held in memory — tests, and the compose-local dev gateway.

    Not a credential store: the tokens are supplied by whoever builds the app,
    so nothing secret is defined in this package (roadmap rule 3).
    """

    tokens: dict[str, Caller]

    def caller(self, token: str | None) -> Caller | None:
        return self.tokens.get(token) if token else None


def require_caller(sessions: Sessions, authorization: str | None) -> Caller:
    """The caller behind an ``Authorization: Bearer <token>`` header, or 401."""
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    caller = sessions.caller(token)
    if caller is None:
        raise GatewayError(401, NO_SESSION, "no session, or the session expired")
    return caller


def resolve_account(raw: str, *, caller: Caller, registry: NodeRegistry) -> str:
    """One named account: the granted id, or the typed refusal.

    Unknown is ``404`` and ungranted is ``403``, as the contract declares. The
    distinction is deliberate: NoFX renders "no such account" and "not yours"
    differently, and collapsing them would make a member's own missing account
    look like someone else's.
    """
    account = raw.strip()
    if registry.by_account(account) is None:
        raise GatewayError(404, UNKNOWN_ACCOUNT, f"no account {account!r}")
    if account not in caller.accounts:
        raise GatewayError(
            403, NOT_GRANTED, f"{caller.principal_id} is not granted account {account!r}"
        )
    return account


def scope_accounts(raw: str | None, *, caller: Caller, registry: NodeRegistry) -> tuple[str, ...]:
    """The accounts a list endpoint may read: one named, or every granted one.

    No grants is ``403``, not an empty list — an empty list reads as "you have
    no positions", which is a different and misleading fact.
    """
    if raw:
        return (resolve_account(raw, caller=caller, registry=registry),)
    granted = tuple(n.account_id for n in registry.accounts() if n.account_id in caller.accounts)
    if not granted:
        raise GatewayError(403, NOT_GRANTED, f"{caller.principal_id} holds no account grant")
    return granted


__all__ = [
    "Caller",
    "NoSessions",
    "Sessions",
    "StaticSessions",
    "require_caller",
    "resolve_account",
    "scope_accounts",
]
