"""Reading ``algobots:cmd:<node>``: the contract's ``NodeCommand``, parsed.

This is the reader half of the envelope ``contracts/gateway.openapi.yaml``
defines as ``SubmitOrderCommand`` / ``CancelOrderCommand``. The writer half is
``OrderIntent.command`` in ``algobots.gateway.admission``, and the two are
tested against the same schema so neither can rename a field alone.

**The node re-validates everything the gateway already checked.** That looks
redundant and is not: the gateway and the node are separate processes with
separate deploys, and the stream between them is durable. A command written by
an older gateway, or replayed out of a stream after a rollback, reaches this
code without the admission chain running again. Re-checking PAPER here is what
makes roadmap rule 3 a property of the process that *places* the order rather
than a promise made by the process that queued it.

A command that fails to parse is **refused, not guessed at**. There is no
partial execution of a malformed order: the actor turns a refusal into a
logged, acknowledged no-op, because retrying a command that is structurally
wrong will never make it right and would block the stream behind it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

#: contracts/gateway.openapi.yaml: ``IdempotencyKeyValue``. Kept as its own
#: copy rather than imported from the gateway so the node has no dependency on
#: the API process' package; the contract test asserts the two agree.
CLIENT_ORDER_ID = re.compile(r"^[A-Za-z0-9._:-]{8,64}$")

DECIMAL = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")

SUBMIT = "submit_order"
CANCEL = "cancel_order"

SIDES = ("buy", "sell")
ORDER_TYPES = ("market", "limit")
TIMES_IN_FORCE = ("gtc", "ioc", "fok", "day")

#: Rule 3, asserted at the point of execution. Not configurable: a node that
#: could be told to run in another mode would make the constant pointless.
PAPER = "PAPER"

SUBMIT_FIELDS = {
    "command",
    "client_order_id",
    "account_id",
    "symbol",
    "side",
    "qty",
    "order_type",
    "limit_px",
    "time_in_force",
    "reduce_only",
    "mode",
    "admitted_ts",
}

CANCEL_FIELDS = {
    "command",
    "client_order_id",
    "account_id",
    "idempotency_key",
    "requested_ts",
}


class CommandRefused(Exception):
    """This command will never be executable. Acknowledge it and move on.

    Distinct from an execution failure, which may be worth a redelivery. A
    refusal is terminal by construction, so the stream must not retry it.
    """

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class SubmitOrder:
    """An admitted order intent, ready for the node's ``ExecutionClient``.

    ``client_order_id`` is the caller's idempotency key, verbatim. Nothing in
    this package derives, prefixes or regenerates it: the whole dedupe
    guarantee rests on the id the venue sees being the id the caller chose.
    """

    client_order_id: str
    account_id: str
    symbol: str
    side: str
    qty: Decimal
    order_type: str
    limit_px: Decimal | None = None
    time_in_force: str = "gtc"
    reduce_only: bool = False
    admitted_ts: float | None = None


@dataclass(frozen=True)
class CancelOrder:
    """A cancellation request for one working order."""

    client_order_id: str
    account_id: str
    idempotency_key: str
    requested_ts: float | None = None


def _require(body: dict[str, Any], field: str, code: str) -> Any:
    if body.get(field) in (None, ""):
        raise CommandRefused(code, f"{field} is required")
    return body[field]


def _client_order_id(raw: Any) -> str:
    """The key, checked against the same shape the gateway promised.

    A key that is not client-order-id safe cannot be handed to Nautilus, and
    silently rewriting it would break dedupe in the one place it has to hold.
    """
    key = str(raw or "").strip()
    if not CLIENT_ORDER_ID.match(key):
        raise CommandRefused(
            "invalid_client_order_id",
            f"{key!r} is not a client-order-id-safe idempotency key "
            "(8-64 chars of [A-Za-z0-9._:-])",
        )
    return key


def _decimal(raw: Any, field: str, code: str) -> Decimal:
    """Decimals are strings on the wire, as they are over HTTP."""
    if not isinstance(raw, str) or not DECIMAL.match(raw):
        raise CommandRefused(code, f"{field} must be a decimal string — got {raw!r}")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:  # pragma: no cover - the regex already rules this out
        raise CommandRefused(code, f"{field} is not a number: {raw!r}") from exc


def _float_or_none(raw: Any) -> float | None:
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def parse(body: Any) -> SubmitOrder | CancelOrder:
    """One stream entry -> the command it carries, or :class:`CommandRefused`."""
    if not isinstance(body, dict):
        raise CommandRefused("invalid_command", "a command must be a JSON object")

    name = str(body.get("command") or "").strip()
    if name == SUBMIT:
        return _submit(body)
    if name == CANCEL:
        return _cancel(body)
    raise CommandRefused("unknown_command", f"unknown command {name!r}")


def _reject_unknown(body: dict[str, Any], allowed: set[str], name: str) -> None:
    """``additionalProperties: false``, enforced on the reading side too.

    If the node ignored an unrecognised field it would execute an order the
    gateway believes it qualified — a ``reduce_only`` that silently did
    nothing is the example that matters.
    """
    unknown = set(body) - allowed
    if unknown:
        raise CommandRefused(
            "unknown_field", f"{name} carries unknown field(s): {', '.join(sorted(unknown))}"
        )


def _submit(body: dict[str, Any]) -> SubmitOrder:
    _reject_unknown(body, SUBMIT_FIELDS, SUBMIT)

    mode = str(body.get("mode") or "").strip().upper()
    if mode != PAPER:
        # Checked before anything else about the order, and before any venue
        # call: the cheapest possible refusal for the one mistake that matters.
        raise CommandRefused(
            "live_disabled", f"mode {mode or '(missing)'} — this node executes {PAPER} only"
        )

    client_order_id = _client_order_id(_require(body, "client_order_id", "invalid_client_order_id"))
    account_id = str(_require(body, "account_id", "invalid_account")).strip()

    symbol = str(body.get("symbol") or "").strip()
    if not symbol:
        raise CommandRefused("invalid_symbol", "symbol is required")

    side = str(body.get("side") or "").strip().lower()
    if side not in SIDES:
        raise CommandRefused("invalid_side", f"side must be one of {SIDES} — got {side!r}")

    order_type = str(body.get("order_type") or "").strip().lower()
    if order_type not in ORDER_TYPES:
        raise CommandRefused(
            "invalid_order_type", f"order_type must be one of {ORDER_TYPES} — got {order_type!r}"
        )

    qty = _decimal(body.get("qty"), "qty", "invalid_qty")
    if qty <= 0:
        raise CommandRefused("invalid_qty", "qty must be greater than zero")

    limit_px = None
    if order_type == "limit":
        if body.get("limit_px") is None:
            raise CommandRefused("invalid_limit_px", "limit_px is required for a limit order")
        limit_px = _decimal(body["limit_px"], "limit_px", "invalid_limit_px")
        if limit_px <= 0:
            raise CommandRefused("invalid_limit_px", "limit_px must be greater than zero")
    elif body.get("limit_px") is not None:
        raise CommandRefused(
            "invalid_limit_px", "limit_px is only meaningful when order_type is limit"
        )

    tif = str(body.get("time_in_force") or "gtc").strip().lower()
    if tif not in TIMES_IN_FORCE:
        raise CommandRefused(
            "invalid_time_in_force", f"time_in_force must be one of {TIMES_IN_FORCE}"
        )

    reduce_only = body.get("reduce_only", False)
    if not isinstance(reduce_only, bool):
        raise CommandRefused("invalid_reduce_only", "reduce_only must be a boolean")

    return SubmitOrder(
        client_order_id=client_order_id,
        account_id=account_id,
        symbol=symbol,
        side=side,
        qty=qty,
        order_type=order_type,
        limit_px=limit_px,
        time_in_force=tif,
        reduce_only=reduce_only,
        admitted_ts=_float_or_none(body.get("admitted_ts")),
    )


def _cancel(body: dict[str, Any]) -> CancelOrder:
    _reject_unknown(body, CANCEL_FIELDS, CANCEL)
    return CancelOrder(
        client_order_id=_client_order_id(
            _require(body, "client_order_id", "invalid_client_order_id")
        ),
        account_id=str(_require(body, "account_id", "invalid_account")).strip(),
        idempotency_key=_client_order_id(
            _require(body, "idempotency_key", "invalid_idempotency_key")
        ),
        requested_ts=_float_or_none(body.get("requested_ts")),
    )


__all__ = [
    "CANCEL",
    "CLIENT_ORDER_ID",
    "ORDER_TYPES",
    "PAPER",
    "SIDES",
    "SUBMIT",
    "TIMES_IN_FORCE",
    "CancelOrder",
    "CommandRefused",
    "SubmitOrder",
    "parse",
]
