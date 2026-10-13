"""PostgreSQL row-level security for the A04 registry tables.

Needs a real PostgreSQL. Set `ALGOBOTS_A04_PG_ADMIN_URL` to a role that may
create databases and roles, e.g.
`postgresql+psycopg://admin@/postgres?host=/tmp/pg&port=55432`. Each run
creates a throwaway database, migrates it to head as the admin (table owner),
seeds two tenants directly through the owner engine (the HTTP surface is
covered by the SQLite suite), and asserts the RLS policies as a fresh LOGIN
role that is NOSUPERUSER NOBYPASSRLS and a member of `algobots_app` — how the
API must connect in production. Without the variable every test here skips
with a BLOCKED reason, and `artifacts/A04/acceptance.json` must report the
RLS case as BLOCKED: SQLite has no row-level security and can't stand in.
"""

import os
import secrets
import uuid

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from tests.conftest import _alembic_config

from algobots.api.auth.context import install_pool_reset
from algobots.api.memberships import service
from algobots.api.models import Account, User

ADMIN_URL = os.environ.get("ALGOBOTS_A04_PG_ADMIN_URL", "")
BLOCKED = (
    "BLOCKED: ALGOBOTS_A04_PG_ADMIN_URL not set; RLS and fingerprint-unique cases "
    "need real PostgreSQL and must not be claimed on SQLite"
)

A04_TABLES = ("broker_connections", "external_account_identities", "secret_grants")

pytestmark = pytest.mark.skipif(not ADMIN_URL, reason=BLOCKED)


@pytest.fixture(scope="module")
def pg():
    suffix = uuid.uuid4().hex[:10]
    db_name = f"a04_{suffix}"
    role = f"a04_app_{suffix}"
    password = secrets.token_hex(16)
    admin_base = make_url(ADMIN_URL)
    admin = sa.create_engine(admin_base, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    owner_url = admin_base.set(database=db_name)
    cfg = _alembic_config(owner_url.render_as_string(hide_password=False).replace("%", "%%"))
    command.upgrade(cfg, "head")
    with admin.connect() as conn:
        conn.execute(
            sa.text(
                f"CREATE ROLE {role} LOGIN PASSWORD '{password}' "
                "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE IN ROLE algobots_app"
            )
        )
    owner = sa.create_engine(owner_url)
    app_url = owner_url.set(username=role, password=password)
    try:
        yield {"owner": owner, "app_url": app_url, "role": role, "db": db_name}
    finally:
        owner.dispose()
        command.downgrade(cfg, "base")
        with admin.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
            conn.execute(sa.text(f'DROP ROLE IF EXISTS {role}'))
        admin.dispose()


def _seed_tenant(owner_engine, label: str) -> dict:
    """User + personal tenant + one mock-venue account (A04 shape)."""
    from algobots.api.accounts.models import BrokerConnection, ExternalAccountIdentity

    with Session(owner_engine) as s:
        user = User(
            email=f"a04-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
            display_name=label,
            role="member",
        )
        s.add(user)
        s.flush()
        tenant = service.create_personal_tenant(s, user)
        account = Account(
            tenant_id=tenant.id, user_id=user.id, label=label, broker="mock", mode="paper"
        )
        s.add(account)
        s.flush()
        s.add(
            BrokerConnection(
                tenant_id=tenant.id,
                account_id=account.id,
                user_id=user.id,
                provider="mock",
                environment="synthetic-paper",
                session_state="CONNECTED",
            )
        )
        s.add(
            ExternalAccountIdentity(
                tenant_id=tenant.id,
                account_id=account.id,
                user_id=user.id,
                provider="mock",
                environment="synthetic-paper",
                fingerprint=ExternalAccountIdentity.fingerprint_of(
                    "mock", "synthetic-paper", f"ext-{label}"
                ),
            )
        )
        s.commit()
        return {"user": user.id, "tenant": tenant.id, "account": account.id}


@pytest.fixture(scope="module")
def tenants(pg) -> dict:
    return {"a": _seed_tenant(pg["owner"], "alpha"), "b": _seed_tenant(pg["owner"], "beta")}


@pytest.fixture()
def app_engine(pg):
    engine = sa.create_engine(pg["app_url"], pool_size=1, max_overflow=0, pool_timeout=10)
    install_pool_reset(engine)
    yield engine
    engine.dispose()


def _set_tenant(conn, tenant_id) -> None:
    conn.execute(
        sa.text("SELECT set_config('app.tenant_id', :tid, false)"), {"tid": str(tenant_id)}
    )


def test_a04_rls_tables_are_forced_and_scoped(pg, app_engine, tenants):
    """The three new tables carry FORCE RLS; the app role sees only its tenant."""
    with pg["owner"].connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = ANY(:t)"
            ),
            {"t": list(A04_TABLES)},
        ).all()
    assert {r[0] for r in rows} == set(A04_TABLES)
    for _, rls, forced in rows:
        assert (rls, forced) == (True, True)

    with app_engine.connect() as conn:
        # No tenant setting: default deny.
        for table in A04_TABLES:
            assert conn.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one() == 0

        # Tenant A setting: exactly A's rows, and writes are checked the same way.
        _set_tenant(conn, tenants["a"]["tenant"])
        assert conn.execute(
            sa.text("SELECT count(*) FROM broker_connections")
        ).scalar_one() == 1
        assert conn.execute(
            sa.text("SELECT count(*) FROM external_account_identities")
        ).scalar_one() == 1
        assert conn.execute(
            sa.text(
                "SELECT count(*) FROM broker_connections bc "
                "JOIN accounts a ON a.id = bc.account_id "
                "WHERE a.tenant_id <> :tid"
            ),
            {"tid": str(tenants["a"]["tenant"])},
        ).scalar_one() == 0

        # Cross-tenant INSERT is rejected: RLS WITH CHECK ( surfaces as a
        # ProgrammingError wrapping psycopg's InsufficientPrivilege).
        with pytest.raises(sa.exc.ProgrammingError):
            conn.execute(
                sa.text(
                    "INSERT INTO broker_connections "
                    "(id, tenant_id, account_id, user_id, provider, environment, "
                    " session_state, egress_allowlist, capabilities_revision, "
                    " sandbox_fidelity, reconciliation_state, reconciliation_reason, "
                    " created_at) VALUES ("
                    "gen_random_uuid(), :tid, :acct, :uid, 'mock', 'synthetic-paper', "
                    "'UNCONFIGURED', '', 0, 'unknown', 'ok', '', now())"
                ),
                {
                    "tid": str(tenants["b"]["tenant"]),
                    "acct": str(tenants["b"]["account"]),
                    "uid": str(tenants["b"]["user"]),
                },
            )


def test_a04_fingerprint_unique_index_blocks_cross_tenant_duplicates(pg, tenants):
    """The globally-unique fingerprint index enforces duplicate detection at
    the database layer, independent of the API."""
    from algobots.api.accounts.models import ExternalAccountIdentity

    dup = ExternalAccountIdentity.fingerprint_of("mock", "synthetic-paper", "ext-alpha")
    with Session(pg["owner"]) as s:
        existing = s.execute(
            sa.select(ExternalAccountIdentity.fingerprint)
        ).scalars().all()
        assert dup in existing  # tenant A's row uses exactly that fingerprint
        beta_account = tenants["b"]["account"]
        s.add(
            ExternalAccountIdentity(
                tenant_id=tenants["b"]["tenant"],
                account_id=beta_account,
                user_id=tenants["b"]["user"],
                provider="mock",
                environment="synthetic-paper",
                fingerprint=dup,
            )
        )
        with pytest.raises(sa.exc.IntegrityError):
            s.flush()
        s.rollback()
