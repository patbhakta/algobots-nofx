"""Tenant-aware keyset cursors for list APIs (A03 checklist 4).

A cursor is `base64url(json{t, c, i}).hmac`: the tenant it was issued for, and
the `(created_at, id)` of the last row served. The HMAC (keyed from the JWT
secret) stops clients from forging positions, and the embedded tenant stops a
cursor minted in tenant A from paging tenant B: decoding it under another
tenant is a 400, never a silent page of someone else's rows. Every page query
also filters on the caller's tenant, so a cursor carries a position, not access.
"""

import base64
import hashlib
import hmac
import json
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, Response, status
from sqlalchemy import Select, and_, or_

from algobots.api.config import get_settings

MAX_PAGE = 1000
CURSOR_HEADER = "X-Next-Cursor"


def _key() -> bytes:
    return hashlib.sha256(b"algobots-cursor:" + get_settings().jwt_secret.encode()).digest()


def _sign(body: bytes) -> str:
    return base64.urlsafe_b64encode(hmac.new(_key(), body, hashlib.sha256).digest()).decode()


def encode_cursor(tenant_id: UUID, created_at: datetime, row_id: UUID) -> str:
    body = json.dumps(
        {"t": str(tenant_id), "c": created_at.isoformat(), "i": str(row_id)},
        separators=(",", ":"),
    ).encode()
    return f"{base64.urlsafe_b64encode(body).decode()}.{_sign(body)}"


def decode_cursor(cursor: str, tenant_id: UUID) -> tuple[datetime, UUID]:
    """Return `(created_at, id)`; 400 if forged, malformed or from another tenant."""
    try:
        body_b64, signature = cursor.split(".", 1)
        body = base64.urlsafe_b64decode(body_b64.encode())
        if not hmac.compare_digest(signature, _sign(body)):
            raise ValueError("bad signature")
        data = json.loads(body)
        if UUID(data["t"]) != tenant_id:
            raise ValueError("cursor belongs to another tenant")
        return datetime.fromisoformat(data["c"]), UUID(data["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid cursor") from exc


def paginate(
    db,
    query: Select,
    model,
    *,
    tenant_id: UUID,
    cursor: str | None,
    limit: int | None,
    response: Response,
) -> list:
    """Run a newest-first keyset page of `query` (already tenant-filtered).

    With no `limit` and no `cursor` the full list is returned (S0.2 behaviour).
    When more rows remain, the next cursor is set in the `X-Next-Cursor` header.
    """
    query = query.order_by(model.created_at.desc(), model.id.desc())
    if cursor is not None:
        created_at, row_id = decode_cursor(cursor, tenant_id)
        query = query.where(
            or_(
                model.created_at < created_at,
                and_(model.created_at == created_at, model.id < row_id),
            )
        )
    if limit is None and cursor is None:
        return list(db.scalars(query))
    size = max(1, min(limit or MAX_PAGE, MAX_PAGE))
    rows = list(db.scalars(query.limit(size + 1)))
    if len(rows) > size:
        rows = rows[:size]
        last = rows[-1]
        response.headers[CURSOR_HEADER] = encode_cursor(tenant_id, last.created_at, last.id)
    return rows
