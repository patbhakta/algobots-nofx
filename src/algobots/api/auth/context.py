"""Transaction-local tenant context and pooled-connection reset (A03 checklist 3).

The authenticated tenant id lives in `Session.info["tenant_id"]`. On
PostgreSQL every transaction a session begins re-applies it with
`set_config('app.tenant_id', <id>, true)` — the `true` makes it
transaction-local (`SET LOCAL` semantics), so COMMIT/ROLLBACK drops it and the
next transaction on the same pooled connection starts with no tenant. The
row-level policies from migration 0005 read that setting and match nothing when
it is empty, so a missing context denies instead of leaking.

As a second barrier, `install_pool_reset` runs `RESET app.tenant_id` whenever a
connection is returned to the pool, and invalidates the connection if the reset
fails, so even a stray session-level `SET` can't reach the next borrower.

SQLite has no row-level security; there, isolation rests on the application
filters (every tenant-owned query filters on `tenant_id`).
"""

from uuid import UUID

from sqlalchemy import event, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

TENANT_SETTING = "app.tenant_id"
# Tables whose rows must carry a tenant (NOT NULL since migration 0005).
TENANT_OWNED_TABLES = frozenset(
    {"accounts", "strategies", "orders", "decisions", "clamp_events", "account_grants"}
)
_SET_TENANT = text("SELECT set_config('app.tenant_id', :tenant_id, true)")


def _is_postgres(session: Session) -> bool:
    bind = session.get_bind()
    return bind is not None and bind.dialect.name == "postgresql"


def _apply(session: Session, connection) -> None:
    tenant_id = session.info.get("tenant_id")
    if tenant_id is not None and connection.dialect.name == "postgresql":
        connection.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})


def set_tenant(session: Session, tenant_id: UUID | None) -> None:
    """Bind the session to a tenant for the rest of its life (every transaction)."""
    session.info["tenant_id"] = tenant_id
    if tenant_id is not None and session.in_transaction() and _is_postgres(session):
        session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})


@event.listens_for(Session, "after_begin")
def _reapply_on_begin(session: Session, transaction, connection) -> None:
    _apply(session, connection)


@event.listens_for(Session, "before_flush")
def _fill_tenant_id(session: Session, flush_context, instances) -> None:
    """Stamp new tenant-owned rows that were built without a `tenant_id`.

    Request code always sets it explicitly. This covers writers outside the A03
    write scope (other packets' services, fixtures) that still build rows with
    only `user_id`: the session's tenant wins, otherwise the user's personal
    tenant. A row that resolves to no tenant fails the NOT NULL constraint.
    """
    from algobots.api.memberships.models import Tenant

    for obj in session.new:
        if getattr(obj, "__tablename__", None) not in TENANT_OWNED_TABLES:
            continue
        if obj.tenant_id is not None:
            continue
        tenant_id = session.info.get("tenant_id")
        if tenant_id is None and getattr(obj, "user_id", None) is not None:
            with session.no_autoflush:
                tenant_id = session.scalar(
                    select(Tenant.id).where(Tenant.personal_owner_user_id == obj.user_id)
                )
        obj.tenant_id = tenant_id


def install_pool_reset(engine: Engine) -> None:
    """Clear any tenant setting on connections returned to a PostgreSQL pool."""
    if engine.dialect.name != "postgresql":
        return

    @event.listens_for(engine, "checkin")
    def _reset_on_checkin(dbapi_connection, connection_record) -> None:
        if dbapi_connection is None:
            return
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute(f"RESET {TENANT_SETTING}")
            cursor.close()
            dbapi_connection.commit()
        except Exception as exc:  # noqa: BLE001 — a dirty connection must not be reused
            connection_record.invalidate(exc)
