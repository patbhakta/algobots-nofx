"""Audit + access-log middleware.

`AuditMiddleware` (outermost) writes one `audit_log` row for every mutating
HTTP request (POST/PUT/PATCH/DELETE), regardless of outcome, with actor (JWT
sub when resolvable), method, path, status code, and the resource identified
by routers via `X-Audit-Resource` / `X-Audit-Resource-Id` response headers.

`AccessLogMiddleware` (inner) tags every response with an `X-Request-Id` and
emits one structured JSON line per request to the `algobots.api.access`
logger (observability proof for the S0.2 Q&A gate).
"""

import json
import logging
import time
from uuid import UUID, uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from algobots.api.security import decode_access_token

logger = logging.getLogger("algobots.api.access")

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _actor_user_id(request: Request) -> str | None:
    """Best-effort actor resolution from the Authorization header (no DB hit)."""
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    return decode_access_token(header[7:].strip())


def _actor_uuid(request: Request) -> UUID | None:
    sub = _actor_user_id(request)
    if sub is None:
        return None
    try:
        return UUID(sub)
    except ValueError:
        return None


def _write_audit_row(request: Request, response: Response) -> None:
    from algobots.api.database import get_session_factory
    from algobots.api.models import AuditLog

    resource = response.headers.get("X-Audit-Resource", "")
    resource_id = response.headers.get("X-Audit-Resource-Id") or None
    detail = json.dumps(
        {"request_id": response.headers.get("X-Request-Id", "")}, separators=(",", ":")
    )
    # Set by the auth dependency (A03) on the shared ASGI scope state.
    tenant_id = request.scope.get("state", {}).get("tenant_id")
    session = get_session_factory()()
    try:
        session.add(
            AuditLog(
                user_id=_actor_uuid(request),
                tenant_id=tenant_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                resource=resource,
                resource_id=resource_id,
                detail_json=detail,
            )
        )
        session.commit()
    finally:
        session.close()


class AuditMiddleware(BaseHTTPMiddleware):
    """Persist an audit row for every mutating request; never break responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.method in MUTATING_METHODS:
            try:
                _write_audit_row(request, response)
            except Exception:  # noqa: BLE001 — audit failures must not 500 the API
                logger.exception("audit_write_failed path=%s", request.url.path)
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Tag responses with X-Request-Id and emit one JSON access-log line."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        request_id = response.headers.get("X-Request-Id") or uuid4().hex[:16]
        response.headers["X-Request-Id"] = request_id
        logger.info(
            json.dumps(
                {
                    "event": "http",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "user_id": _actor_user_id(request),
                },
                separators=(",", ":"),
            )
        )
        return response
