"""Admission: the bridge's refusal order, promoted to the gateway unchanged.

```
account scope -> request shape -> PAPER-only -> node reconciled and
heartbeat-fresh -> gate.pre_trade
```

That order is the whole point of the module, and it may not be reordered or
skipped (ALG-3340, docs/bridge.md; ALG-3262 before it). Each step answers a
different question, and the earlier ones are cheaper *and* more sensitive:
whether the caller may see the account at all precedes whether their JSON
parses, which precedes whether we would ever trade it, which precedes whether
anything is alive to trade it, which precedes whether risk allows it now.

**A refused intent is never written.** The command reaches
``algobots:cmd:<node>`` only after every check has passed, so a refusal leaves
no trace a later sprint could mistake for an admitted order.

The one thing that short-circuits the chain is an **idempotent replay**: a key
this gateway has already admitted returns the order it created, with no second
command and no second gate evaluation. A replay is not a new admission — if it
re-ran the gate, a retry during a risk envelope breach would turn a successful
submission into a failure the caller cannot distinguish from a rejection.
Scope and shape still run first, so a replay cannot be used to read another
member's order.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from algobots.gateway.auth import Caller, resolve_account
from algobots.gateway.errors import (
    IDEMPOTENCY_KEY_CONFLICT,
    IDEMPOTENCY_KEY_REQUIRED,
    GatewayError,
)
from algobots.gateway.node_events import admitted_order
from algobots.gateway.nodes import PAPER, NodeRegistry
from algobots.gateway.projection import InMemoryProjection, OrderRow, dec_str

SIDES = ("buy", "sell")
ORDER_TYPES = ("market", "limit")
TIMES_IN_FORCE = ("gtc", "ioc", "fok", "day")

# contracts/gateway.openapi.yaml: Decimal and IdempotencyKeyValue.
DECIMAL = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{8,64}$")

ORDER_FIELDS = {
    "account_id",
    "symbol",
    "side",
    "qty",
    "order_type",
    "limit_px",
    "time_in_force",
    "reduce_only",
}


@dataclass(frozen=True)
class OrderIntent:
    """A validated, in-scope intent — not yet admitted, not yet queued."""

    client_order_id: str
    account_id: str
    node: str
    symbol: str
    side: str
    qty: Decimal
    order_type: str
    limit_px: Decimal | None = None
    time_in_force: str | None = None
    reduce_only: bool = False

    def command(self, *, now: float) -> dict[str, Any]:
        """The ``algobots:cmd:<node>`` payload P1.3's ``CommandActor`` reads.

        ``client_order_id`` is the caller's idempotency key verbatim: the node
        submits it to Nautilus as the client order id, which is what makes the
        same command twice create one order *at the venue* and not merely in
        this process.
        """
        command: dict[str, Any] = {
            "command": "submit_order",
            "client_order_id": self.client_order_id,
            "account_id": self.account_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": dec_str(self.qty),
            "order_type": self.order_type,
            "time_in_force": self.time_in_force or "gtc",
            "reduce_only": self.reduce_only,
            "mode": PAPER,
            "admitted_ts": now,
        }
        if self.limit_px is not None:
            # Absent, not null — the contract's SubmitOrderCommand and
            # OrderRow.contract() agree on one spelling for "no limit price".
            command["limit_px"] = dec_str(self.limit_px)
        return command


@dataclass(frozen=True)
class GateDecision:
    """``allowed``, or a machine code and the reason a member is shown."""

    allowed: bool
    code: str = ""
    reason: str = ""
    approved_qty: Decimal | None = None  # a clamp may shrink the order


class PreTradeGate(Protocol):
    """The ALG-3262 pre-trade gate: kill switch, sleeve floor, daily-loss
    envelope, order-value clamp, affordability. The gateway owns the order of
    checks; the gate owns their content and its own refusal codes."""

    def pre_trade(self, intent: OrderIntent) -> GateDecision: ...


@dataclass(frozen=True)
class AllowAll:
    """A gate that allows everything — fixtures and contract tests only.

    Deliberately not the default anywhere: ``build_gateway`` takes the gate as
    a required argument, so no deployment can get an open gate by omission.
    """

    def pre_trade(self, intent: OrderIntent) -> GateDecision:
        return GateDecision(True)


@dataclass(frozen=True)
class Admission:
    """The outcome: the order, and whether this was a replay of an old key."""

    order: OrderRow
    replay: bool


def fingerprint(body: dict[str, Any]) -> str:
    """A stable digest of the request, so a reused key with a changed body is
    a conflict rather than a silently different order."""
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _bad(code: str, reason: str) -> GatewayError:
    return GatewayError(422, code, reason)


def require_idempotency_key(raw: str | None) -> str:
    """Every order write carries one (contract: ``IdempotencyKey`` is required)."""
    key = (raw or "").strip()
    if not key:
        raise GatewayError(
            422, IDEMPOTENCY_KEY_REQUIRED, "Idempotency-Key header is required on order writes"
        )
    if not IDEMPOTENCY_KEY.match(key):
        raise _bad(
            "invalid_idempotency_key",
            "Idempotency-Key must be 8-64 chars of [A-Za-z0-9._:-] — it becomes the "
            "Nautilus client order id",
        )
    return key


def _decimal(raw: Any, field: str, code: str) -> Decimal:
    """Decimals arrive as strings. A JSON number is a shape error, not a value
    to coerce: the contract says so, and binary floating point has no business
    anywhere near a quantity or a price."""
    if not isinstance(raw, str) or not DECIMAL.match(raw):
        raise _bad(code, f"{field} must be a decimal string, e.g. \"1.5\" — got {raw!r}")
    return Decimal(raw)


def validate(body: Any, *, account_id: str, node: str, client_order_id: str) -> OrderIntent:
    """Step 2: the request's shape. Runs after scope, before anything else."""
    if not isinstance(body, dict):
        raise _bad("invalid_request", "body must be a JSON object")
    unknown = set(body) - ORDER_FIELDS
    if unknown:
        # The contract sets additionalProperties: false. Accepting an unknown
        # field would let a caller believe it had an effect.
        raise _bad("unknown_field", f"unknown field(s): {', '.join(sorted(unknown))}")

    side = str(body.get("side", "")).strip().lower()
    if side not in SIDES:
        raise _bad("invalid_side", f"side must be one of {SIDES}")

    order_type = str(body.get("order_type", "")).strip().lower()
    if order_type not in ORDER_TYPES:
        raise _bad("invalid_order_type", f"order_type must be one of {ORDER_TYPES}")

    symbol = str(body.get("symbol", "")).strip()
    if not symbol:
        raise _bad("invalid_symbol", "symbol is required — the node's adapter names it")

    qty = _decimal(body.get("qty"), "qty", "invalid_qty")
    if qty <= 0:
        raise _bad("invalid_qty", "qty must be greater than zero")

    limit_px = None
    if order_type == "limit":
        if body.get("limit_px") is None:
            raise _bad("invalid_limit_px", "limit_px is required when order_type is limit")
        limit_px = _decimal(body["limit_px"], "limit_px", "invalid_limit_px")
        if limit_px <= 0:
            raise _bad("invalid_limit_px", "limit_px must be greater than zero")
    elif body.get("limit_px") is not None:
        raise _bad("invalid_limit_px", "limit_px is forbidden unless order_type is limit")

    tif = body.get("time_in_force")
    if tif is not None:
        tif = str(tif).strip().lower()
        if tif not in TIMES_IN_FORCE:
            raise _bad("invalid_time_in_force", f"time_in_force must be one of {TIMES_IN_FORCE}")

    reduce_only = body.get("reduce_only", False)
    if not isinstance(reduce_only, bool):
        raise _bad("invalid_reduce_only", "reduce_only must be a boolean")

    return OrderIntent(
        client_order_id=client_order_id,
        account_id=account_id,
        node=node,
        symbol=symbol,
        side=side,
        qty=qty,
        order_type=order_type,
        limit_px=limit_px,
        time_in_force=tif,
        reduce_only=reduce_only,
    )


def admit(
    body: Any,
    *,
    caller: Caller,
    idempotency_key: str | None,
    registry: NodeRegistry,
    projection: InMemoryProjection,
    gate: PreTradeGate,
    now: float | None = None,
) -> tuple[Admission, OrderIntent | None]:
    """Run the chain. Returns the admission and, when it is not a replay, the
    intent whose command the caller must publish.

    Publishing is left to the caller so that this function has no side effect
    outside the projection: "a refused intent is never written" is then a
    property of the code path, not a thing to remember.
    """
    now = time.time() if now is None else now

    # 1. account scope — before the body is even looked at.
    key = require_idempotency_key(idempotency_key)
    account_id = resolve_account(
        str((body or {}).get("account_id", "")) if isinstance(body, dict) else "",
        caller=caller,
        registry=registry,
    )

    # 2. request shape.
    node = registry.by_account(account_id)
    assert node is not None  # resolve_account already proved it exists
    intent = validate(body, account_id=account_id, node=node.node, client_order_id=key)
    digest = fingerprint(body)

    # An already-admitted key: return its order, unchanged. No second command.
    existing = projection.order(key)
    if existing is not None:
        if existing.fingerprint != digest:
            raise GatewayError(
                409,
                IDEMPOTENCY_KEY_CONFLICT,
                f"Idempotency-Key {key!r} was used with a different request body",
            )
        return Admission(existing, replay=True), None

    # 3. PAPER-only, then 4. the node is reconciled and heartbeat-fresh.
    fit = registry.require_fit(account_id, now=now)

    # 5. the pre-trade gate.
    decision = gate.pre_trade(intent)
    if not decision.allowed:
        raise GatewayError(403, decision.code or "gate_denied", decision.reason)
    if decision.approved_qty is not None:
        if decision.approved_qty <= 0:
            raise GatewayError(
                403, "clamped_to_zero", "the order-value clamp left nothing to trade"
            )
        intent = OrderIntent(**{**intent.__dict__, "qty": decision.approved_qty})

    order = projection.put_order(
        admitted_order(
            client_order_id=key,
            account_id=account_id,
            node=fit.node,
            symbol=intent.symbol,
            side=intent.side,
            qty=intent.qty,
            order_type=intent.order_type,
            limit_px=intent.limit_px,
            time_in_force=intent.time_in_force,
            now=now,
            fingerprint=digest,
        )
    )
    return Admission(order, replay=False), intent


__all__ = [
    "DECIMAL",
    "IDEMPOTENCY_KEY",
    "ORDER_TYPES",
    "SIDES",
    "TIMES_IN_FORCE",
    "Admission",
    "AllowAll",
    "GateDecision",
    "OrderIntent",
    "PreTradeGate",
    "admit",
    "fingerprint",
    "require_idempotency_key",
    "validate",
]
