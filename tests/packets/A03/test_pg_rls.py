"""PostgreSQL row-level security: AC1 (database layer), AC2 (pooled
connections), and the AC5 redemption race on real row locks.

Needs a real PostgreSQL. Set `ALGOBOTS_A03_PG_ADMIN_URL` to a role that may
create databases and roles, e.g.
`postgresql+psycopg://admin@/postgres?host=/tmp/pg&port=55432`. Each run
creates a throwaway database, migrates it to head as the admin (table owner),
and runs the assertions as a fresh LOGIN role that is NOSUPERUSER NOBYPASSRLS
and a member of `algobots_app`, which is how the API must connect in
production. Without the variable every test here is skipped with a BLOCKED
reason, and `artifacts/A03/acceptance.json` must then report AC1-db/AC2 as
BLOCKED: SQLite has no row-level security and can't stand in.
"""

import os
import secrets
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from alembic import command
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from tests.conftest import TEST_PASSWORD, _alembic_config

from algobots.api import database
from algobots.api.auth.context import install_pool_reset, set_tenant
from algobots.api.main import app
from algobots.api.memberships import service
from algobots.api.memberships.models import Tenant, TenantInvite, TenantMembership
from algobots.api.models import Account, Strategy, User
from algobots.api.security import hash_password

ADMIN_URL = os.environ.get("ALGOBOTS_A03_PG_ADMIN_URL", "")
BLOCKED = (
    "BLOCKED: ALGOBOTS_A03_PG_ADMIN_URL not set; RLS and pooled-connection cases "
    "need real PostgreSQL and must not be claimed on SQLite"
)

pytestmark = pytest.mark.skipif(not ADMIN_URL, reason=BLOCKED)


@pytest.fixture(scope="module")
def pg():
    suffix = uuid.uuid4().hex[:10]
    db_name = f"a03_{suffix}"
    role = f"a03_app_{suffix}"
    password = secrets.token_hex(16)
    admin_base = make_url(ADMIN_URL)
    admin = sa.create_engine(admin_base, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    owner_url = admin_base.set(database=db_name)
    # configparser treats "%" as interpolation; URL-encoded socket paths need "%%".
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
            conn.execute(sa.text(f"DROP ROLE IF EXISTS {role}"))
        admin.dispose()


def _seed_tenant(owner_engine, label: str = "main") -> dict:
    """User + personal tenant + an account and strategy with shared-looking labels."""
    with Session(owner_engine) as s:
        user = User(
            email=f"u-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
            display_name="U",
            role="member",
        )
        s.add(user)
        s.flush()
        tenant = service.create_personal_tenant(s, user)
        account = Account(
            tenant_id=tenant.id, user_id=user.id, label=label, broker="alpaca", mode="paper"
        )
        strategy = Strategy(tenant_id=tenant.id, user_id=user.id, name="momentum", kind="trend")
        s.add_all([account, strategy])
        s.commit()
        return {
            "user": user.id,
            "tenant": tenant.id,
            "account": account.id,
            "strategy": strategy.id,
        }


@pytest.fixture(scope="module")
def tenants(pg) -> dict:
    return {"a": _seed_tenant(pg["owner"]), "b": _seed_tenant(pg["owner"])}


@pytest.fixture()
def app_engine(pg):
    engine = sa.create_engine(pg["app_url"], pool_size=1, max_overflow=0, pool_timeout=10)
    install_pool_reset(engine)
    yield engine
    engine.dispose()


def _setting(s: Session) -> str | None:
    return s.execute(sa.text("SELECT current_setting('app.tenant_id', true)")).scalar()


def _pid(s: Session) -> int:
    return s.execute(sa.text("SELECT pg_backend_pid()")).scalar()


# --- AC1, database layer ---------------------------------------------------------


def test_ac1_rls_app_role_is_not_privileged(pg, app_engine):
    with app_engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
        assert row == (False, False)
        forced = conn.execute(
            sa.text(
                "SELECT relname FROM pg_class WHERE relrowsecurity AND relforcerowsecurity "
                "AND relname = ANY(:t)"
            ),
            {
                "t": [
                    "accounts",
                    "strategies",
                    "orders",
                    "decisions",
                    "clamp_events",
                    "account_grants",
                ]
            },
        ).scalars()
        assert set(forced) == {
            "accounts",
            "strategies",
            "orders",
            "decisions",
            "clamp_events",
            "account_grants",
        }


def test_ac1_rls_tenant_sees_and_touches_only_own_rows(tenants, app_engine):
    a, b = tenants["a"], tenants["b"]
    factory = sessionmaker(bind=app_engine)
    with factory() as s:
        set_tenant(s, a["tenant"])
        labels = s.execute(sa.select(Account.id, Account.label)).all()
        assert {row.id for row in labels} == {a["account"]}
        assert {row.label for row in labels} == {"main"}  # B also has a "main"
        assert s.get(Account, b["account"]) is None
        assert (
            s.execute(
                sa.update(Account).where(Account.id == b["account"]).values(label="x")
            ).rowcount
            == 0
        )
        assert s.execute(sa.delete(Strategy).where(Strategy.id == b["strategy"])).rowcount == 0
        s.commit()

    # Writing a row into B while acting as A violates the policy's WITH CHECK.
    with factory() as s:
        set_tenant(s, a["tenant"])
        s.add(Account(tenant_id=b["tenant"], user_id=a["user"], label="smuggled", broker="alpaca"))
        with pytest.raises(sa.exc.ProgrammingError, match="row-level security"):
            s.flush()
        s.rollback()

    # No tenant context at all: nothing is visible (default deny).
    with factory() as s:
        assert s.scalars(sa.select(Account)).all() == []
        assert s.scalars(sa.select(Strategy)).all() == []


def test_ac1_rls_cannot_be_switched_off_by_app_role(tenants, app_engine):
    with app_engine.connect() as conn:
        conn.execute(sa.text("SET row_security = off"))
        with pytest.raises(sa.exc.DBAPIError, match="row-level security"):
            conn.execute(sa.text("SELECT * FROM accounts")).all()
        conn.rollback()


# --- AC2, pooled connection --------------------------------------------------------


def test_ac2_pooled_connection_carries_no_tenant_across_transactions(tenants, app_engine):
    a, b = tenants["a"], tenants["b"]
    factory = sessionmaker(bind=app_engine)

    with factory() as s:
        set_tenant(s, a["tenant"])
        pid = _pid(s)
        assert _setting(s) == str(a["tenant"])
        assert {x.id for x in s.scalars(sa.select(Account))} == {a["account"]}
        s.commit()
        # Same session, next transaction: the binding is re-applied...
        assert _setting(s) == str(a["tenant"])
        s.commit()

    # ...but the next borrower of the same pooled connection starts clean.
    with factory() as s:
        assert _pid(s) == pid, "pool_size=1 must hand back the same backend"
        assert _setting(s) in (None, "")
        assert s.scalars(sa.select(Account)).all() == []
        s.commit()

    with factory() as s:
        set_tenant(s, b["tenant"])
        assert _pid(s) == pid
        assert {x.id for x in s.scalars(sa.select(Account))} == {b["account"]}


def test_ac2_rollback_and_error_leave_no_context(tenants, app_engine):
    factory = sessionmaker(bind=app_engine)
    with factory() as s:
        set_tenant(s, tenants["a"]["tenant"])
        with pytest.raises(sa.exc.DBAPIError):
            s.execute(sa.text("SELECT 1/0"))
        s.rollback()
    with factory() as s:
        assert _setting(s) in (None, "")
        assert s.scalars(sa.select(Account)).all() == []


def test_ac2_stray_session_level_set_is_reset_on_checkin(tenants, app_engine):
    factory = sessionmaker(bind=app_engine)
    with factory() as s:
        pid = _pid(s)
        # A non-local SET would survive COMMIT; the pool checkin hook clears it.
        s.execute(sa.text(f"SET app.tenant_id = '{tenants['a']['tenant']}'"))
        assert _setting(s) == str(tenants["a"]["tenant"])
        # COMMIT returns the connection to the pool; the checkin hook resets it.
        s.commit()
    with factory() as s:
        assert _pid(s) == pid
        assert _setting(s) in (None, "")
        assert s.scalars(sa.select(Account)).all() == []


def test_ac2_http_requests_interleaved_on_pooled_connections(pg, monkeypatch):
    """Full stack on PostgreSQL as the non-bypass role, with a tiny pool."""
    engine = sa.create_engine(pg["app_url"], pool_size=1, max_overflow=1, pool_timeout=10)
    install_pool_reset(engine)
    pids: set[int] = set()

    @sa.event.listens_for(engine, "checkout")
    def _track(dbapi_connection, record, proxy):
        cur = dbapi_connection.cursor()
        cur.execute("SELECT pg_backend_pid()")
        pids.add(cur.fetchone()[0])
        cur.close()

    monkeypatch.setattr(database, "_engine", engine)
    monkeypatch.setattr(
        database, "_session_factory", sessionmaker(bind=engine, expire_on_commit=False)
    )
    client = TestClient(app)
    try:
        # A platform owner (seeded as table owner) invites owners A and B.
        with Session(pg["owner"]) as s:
            founder_user = User(
                email=f"pg-founder-{uuid.uuid4().hex[:6]}@example.com",
                password_hash=hash_password(TEST_PASSWORD),
                display_name="Founder",
                role="owner",
            )
            s.add(founder_user)
            s.flush()
            service.create_personal_tenant(s, founder_user)
            s.commit()
            founder_email = founder_user.email

        def login(email: str) -> dict:
            r = client.post("/api/auth/login", json={"email": email, "password": TEST_PASSWORD})
            assert r.status_code == 200, r.text
            return {"Authorization": f"Bearer {r.json()['access_token']}"}

        def register(email: str, code: str) -> dict:
            r = client.post(
                "/api/auth/register",
                json={
                    "email": email,
                    "password": TEST_PASSWORD,
                    "display_name": email[:6],
                    "invite_code": code,
                },
            )
            assert r.status_code == 201, r.text
            return login(email)

        founder = login(founder_email)
        heads = {}
        for name in ("a", "b"):
            code = client.post("/api/auth/invites", headers=founder).json()["code"]
            heads[name] = register(f"pg-{name}@example.com", code)

        ids = {}
        for name in ("a", "b"):
            r = client.post(
                "/api/accounts", headers=heads[name], json={"label": "main", "broker": "alpaca"}
            )
            assert r.status_code == 201, r.text
            ids[name] = r.json()["id"]

        for _ in range(5):
            for me, other in (("a", "b"), ("b", "a")):
                listed = client.get("/api/accounts", headers=heads[me]).json()
                assert [x["id"] for x in listed] == [ids[me]]
                assert (
                    client.get(f"/api/accounts/{ids[other]}", headers=heads[me]).status_code == 404
                )
                assert (
                    client.patch(
                        f"/api/accounts/{ids[other]}", headers=heads[me], json={"label": "pwned"}
                    ).status_code
                    == 404
                )
                dump = client.get("/api/export", headers=heads[me]).text
                assert ids[other] not in dump
        assert 1 <= len(pids) <= 2, "requests must have reused pooled connections"
    finally:
        engine.dispose()


# --- AC5 on PostgreSQL row locks -------------------------------------------------


def test_ac5_concurrent_redemption_postgres(pg, tenants):
    racers = 8
    token = f"tinv_{secrets.token_urlsafe(32)}"
    with Session(pg["owner"]) as s:
        user = User(
            email="racer-pg@example.com", password_hash="x", display_name="R", role="member"
        )
        s.add(user)
        s.flush()
        tenant = s.get(Tenant, tenants["a"]["tenant"])
        s.add(
            TenantInvite(
                tenant_id=tenant.id,
                email=user.email,
                role="member",
                token_hash=service.hash_invite_token(token),
                invited_by_user_id=tenants["a"]["user"],
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        s.commit()
        user_id = user.id

    engine = sa.create_engine(pg["app_url"], pool_size=racers, max_overflow=0)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    barrier = threading.Barrier(racers)
    outcomes: list[str] = []
    lock = threading.Lock()

    def race() -> None:
        with factory() as s:
            racer = s.get(User, user_id)
            invite = service.find_redeemable_invite(s, token, racer.email)
            barrier.wait()
            try:
                service.redeem_invite(s, invite, racer)
                s.commit()
                result = "won"
            except HTTPException as exc:
                s.rollback()
                result = f"lost:{exc.status_code}"
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=race) for _ in range(racers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    engine.dispose()

    assert outcomes.count("won") == 1
    assert outcomes.count("lost:409") == racers - 1
    with Session(pg["owner"]) as s:
        rows = s.scalars(
            sa.select(TenantMembership).where(
                TenantMembership.tenant_id == tenants["a"]["tenant"],
                TenantMembership.user_id == user_id,
            )
        ).all()
        assert len(rows) == 1
