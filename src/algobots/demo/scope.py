"""Server-side account scope for /demo (A10-3).

Every /demo response is built from a ledger narrowed to the caller's granted
accounts, so the aggregate, the Accounts pane and the JSON views can only ever
contain granted rows. ``?account=`` is checked here, never just in navigation:
unknown -> 404, ungranted -> 403, aggregate with no grants -> 403.

The deployed demo has no login, so the caller is a fixed synthetic principal
from settings (``demo_principal_id`` / ``demo_account_grants``); the grant
check still runs on it. Tests swap identities via ``app.dependency_overrides``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from fastapi import HTTPException

from algobots.api.config import get_settings
from algobots.contracts.identity import Grant, IdentityKind, Principal
from algobots.demo import blotter as B
from algobots.demo import ledger as L


@dataclass(frozen=True)
class Scope:
    principal: Principal
    accounts: tuple[str, ...]  # granted demo accounts, in STRATEGIES order

    @classmethod
    def of(cls, principal: Principal, accounts: set[str] | tuple[str, ...]) -> Scope:
        # ACCOUNT_READ gates everything; per-account grants narrow it further
        held = set(accounts) if principal.has(Grant.ACCOUNT_READ) else set()
        return cls(principal, tuple(k for k in L.STRATEGIES if k in held))


def current_scope() -> Scope:
    """FastAPI dependency: the caller's identity and demo-account grants."""
    s = get_settings()
    principal = Principal(
        schema_version=Principal.contract_version,
        principal_id=s.demo_principal_id,
        kind=IdentityKind.USER,
        tenant_id=s.demo_tenant_id,
        grants=(Grant.ACCOUNT_READ,),
    )
    return Scope.of(principal, {a.strip().lower() for a in s.demo_account_grants.split(",")})


class Denied(HTTPException):
    def __init__(self, code: int, account: str, why: str) -> None:
        super().__init__(code, detail={"account": account, "state": "denied", "reason": why})
        self.account, self.why = account, why


def resolve(raw: str | None, scope: Scope) -> str:
    """Strict ``?account=``: the granted key, ``all``, or Denied (404/403)."""
    key = (raw or B.ALL).strip().lower()
    who = scope.principal.principal_id
    if key == B.ALL:
        if not scope.accounts:
            raise Denied(403, key, f"{who} holds no account grant")
        return key
    if key not in L.STRATEGIES:
        raise Denied(404, key, "unknown account")
    if key not in scope.accounts:
        raise Denied(403, key, f"{who} not granted {key}")
    return key


def narrow(lg: L.Ledger, scope: Scope) -> L.Ledger:
    """The ledger as this caller may see it: ungranted books never leave the server."""
    keep = set(scope.accounts)
    return replace(
        lg,
        books={k: b for k, b in lg.books.items() if k in keep},
        clamp_events=[d for d in lg.clamp_events if d.strategy in keep],
    )
