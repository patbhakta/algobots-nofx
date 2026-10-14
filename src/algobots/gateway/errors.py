"""The gateway's one failure shape (contract: ``components.schemas.Error``).

Every 4xx and 5xx the gateway returns is ``{code, reason}`` — a machine code
the frontend switches on and a reason it may show the member verbatim. This is
the bridge's typed error (``algobots.bridge.admission.BridgeApiError``) with
the ``{"error": {...}}`` wrapper removed, because the contract declares the
envelope at the top level of the body.

A ``code`` is snake_case and stable: NoFX branches on it, so renaming one is a
contract change. The admission codes carried over from docs/bridge.md are
collected here so there is one list, not one per call site.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

# Admission refusals (docs/bridge.md, ALG-3340). The pre-trade gate adds its
# own codes on top of these; it owns them, so they are not enumerated here.
LIVE_DISABLED = "live_disabled"
WORKER_UNAVAILABLE = "worker_unavailable"
NODE_UNKNOWN = "node_unknown"
INVALID_REQUEST = "invalid_request"
IDEMPOTENCY_KEY_REQUIRED = "idempotency_key_required"
IDEMPOTENCY_KEY_CONFLICT = "idempotency_key_conflict"
NO_SESSION = "no_session"
NOT_GRANTED = "not_granted"
UNKNOWN_ACCOUNT = "unknown_account"
UNKNOWN_ORDER = "unknown_order"
ORDER_TERMINAL = "order_terminal"


class GatewayError(Exception):
    """A typed gateway failure: HTTP ``status`` + machine ``code`` + reason.

    ``details`` is optional structured context for the frontend. It is part of
    the contract's ``Error`` schema and may never carry a secret.
    """

    def __init__(
        self, status: int, code: str, reason: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(f"[{code}] {reason}")
        self.status, self.code, self.reason = status, code, reason
        self.details = details

    def body(self) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code, "reason": self.reason}
        if self.details:
            body["details"] = self.details
        return body

    def response(self) -> JSONResponse:
        return JSONResponse(status_code=self.status, content=self.body())


async def gateway_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Render :class:`GatewayError` as the contract's envelope, never a 500."""
    assert isinstance(exc, GatewayError)
    return exc.response()


__all__ = [
    "IDEMPOTENCY_KEY_CONFLICT",
    "IDEMPOTENCY_KEY_REQUIRED",
    "INVALID_REQUEST",
    "LIVE_DISABLED",
    "NODE_UNKNOWN",
    "NOT_GRANTED",
    "NO_SESSION",
    "ORDER_TERMINAL",
    "UNKNOWN_ACCOUNT",
    "UNKNOWN_ORDER",
    "WORKER_UNAVAILABLE",
    "GatewayError",
    "gateway_error_handler",
]
