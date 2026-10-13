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

Application-level criteria (both dialects): once a request has bound a session
(`set_tenant`, even to "no tenant"), every ORM SELECT/UPDATE/DELETE on a
tenant-owned table is narrowed to that tenant via `with_loader_criteria`. That
includes the tables owned by other packets that still carry only `user_id`
(deployments, account credentials, approval requests, broadcasts, action
ledger): they are narrowed through the tenant's accounts/approvals/orders, so a
user who belongs to two tenants can't reach one tenant's rows from the other.
With no tenant bound the criteria match nothing. Sessions that never call
`set_tenant` (migrations, background sweeps, the audit writer) are unfiltered.
"""

from uuid import UUID

from sqlalchemy import event, false, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

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


def _tenant_criteria(tenant_id: UUID | None) -> list:
    from algobots.api.accounts.models import AccountCredential
    from algobots.api.approvals.models import ActionLedger, ApprovalRequest, Broadcast
    from algobots.api.deployments.models import Deployment
    from algobots.api.memberships.models import AccountGrant
    from algobots.api.models import Account, ClampEvent, Decision, Order, Strategy

    if tenant_id is None:
        models = (
            Account, Strategy, Order, Decision, ClampEvent, AccountGrant,
            Deployment, AccountCredential, ApprovalRequest, Broadcast, ActionLedger,
        )  # fmt: skip
        return [with_loader_criteria(m, false(), include_aliases=True) for m in models]

    tenant_accounts = select(Account.id).where(Account.tenant_id == tenant_id)
    tenant_approvals = select(ApprovalRequest.id).where(
        ApprovalRequest.account_id.in_(tenant_accounts)
    )
    tenant_orders = select(Order.id).where(Order.tenant_id == tenant_id)
    tenant_deployments = select(Deployment.id).where(Deployment.account_id.in_(tenant_accounts))
    criteria = [
        with_loader_criteria(m, m.tenant_id == tenant_id, include_aliases=True)
        for m in (Account, Strategy, Order, Decision, ClampEvent, AccountGrant)
    ]
    criteria += [
        with_loader_criteria(m, m.account_id.in_(tenant_accounts), include_aliases=True)
        for m in (Deployment, AccountCredential, ApprovalRequest)
    ]
    criteria.append(
        with_loader_criteria(
            Broadcast, Broadcast.approval_request_id.in_(tenant_approvals), include_aliases=True
        )
    )
    criteria.append(
        with_loader_criteria(
            ActionLedger,
            or_(
                ActionLedger.subject_id.in_(tenant_approvals),
                ActionLedger.subject_id.in_(tenant_orders),
                ActionLedger.subject_id.in_(tenant_deployments),
            ),
            include_aliases=True,
        )
    )
    return criteria


@event.listens_for(Session, "do_orm_execute")
def _scope_to_tenant(state: ORMExecuteState) -> None:
    if "tenant_id" not in state.session.info:
        return
    if not (state.is_select or state.is_update or state.is_delete):
        return
    state.statement = state.statement.options(*_tenant_criteria(state.session.info["tenant_id"]))


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
