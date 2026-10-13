"""Explicit audit events for membership, role, grant and policy decisions (A03 checklist 4).

The HTTP audit middleware already writes one row per mutating request. These
helpers add a typed event row (`method` = `EVENT` or `DENY`) that says *what*
changed or was refused. Details hold ids, roles and action names only, never
request bodies, tokens or passwords.
"""

import json
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from algobots.api.models import AuditLog


def _detail(event: str, detail: dict[str, Any]) -> str:
    values = {k: (str(v) if isinstance(v, UUID) else v) for k, v in detail.items()}
    payload = {"event": event, **values}
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def record_event(
    db: Session,
    *,
    event: str,
    actor_user_id: UUID | None,
    tenant_id: UUID | None,
    resource: str,
    resource_id: UUID | None,
    **detail: Any,
) -> None:
    """Add an event row to the caller's transaction (it commits with the change)."""
    db.add(
        AuditLog(
            user_id=actor_user_id,
            tenant_id=tenant_id,
            method="EVENT",
            path=event,
            status_code=200,
            resource=resource,
            resource_id=None if resource_id is None else str(resource_id),
            detail_json=_detail(event, detail),
        )
    )


def record_denial(
    *,
    method: str,
    path: str,
    actor_user_id: UUID | None,
    tenant_id: UUID | None,
    role: str | None,
    action: str,
) -> None:
    """Persist a policy denial in its own transaction.

    The request's own session is rolled back when the 403 propagates, so the
    denial is written through a fresh session to survive that rollback.
    """
    from algobots.api.database import get_session_factory

    session = get_session_factory()()
    try:
        session.add(
            AuditLog(
                user_id=actor_user_id,
                tenant_id=tenant_id,
                method="DENY",
                path=path,
                status_code=403,
                resource="policy",
                resource_id=None,
                detail_json=_detail(
                    "policy.denied", {"action": action, "role": role, "request_method": method}
                ),
            )
        )
        session.commit()
    finally:
        session.close()
