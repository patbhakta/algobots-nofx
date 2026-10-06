"""tenant memberships, hashed invites, sessions, account grants, row-level security (ALG-3099)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-06

A03 moves tenancy from "one user = one tenant" to real workspaces:

1. New tables `tenants`, `tenant_memberships`, `tenant_invites` (token stored
   as SHA-256 only), `auth_sessions` (server-side revocation) and
   `account_grants` (trading authority, separate from membership).
2. Every existing user gets a personal tenant and an `owner` membership; every
   tenant-owned row (`accounts`, `strategies`, `orders`, `decisions`,
   `clamp_events`) is stamped with its writer's personal tenant, so the S0.2
   isolation boundary is unchanged on day one. `audit_log` gains a nullable
   `tenant_id` and is backfilled the same way. No existing row is modified
   beyond the new column, and none is deleted.
3. `tenant_id` becomes NOT NULL on the tenant-owned tables. `(tenant_id, id)` is
   unique on `accounts` and `strategies`, and children reference them through
   composite foreign keys, so a row can never point at another tenant's parent.
4. PostgreSQL only: ENABLE + FORCE ROW LEVEL SECURITY on the tenant-owned tables
   and `account_grants`, with one policy matching
   `tenant_id = current_setting('app.tenant_id')`. An unset or empty setting
   matches nothing (default deny). FORCE makes the policy apply to the table
   owner too; only superusers and BYPASSRLS roles skip it. When the migrating
   role may create roles, a NOLOGIN NOBYPASSRLS group role `algobots_app` is
   created (if missing) and granted DML; the API's login role should be a member
   of it and must not be a superuser.

Downgrade guidance
------------------
`alembic downgrade 0004` drops the policies, `account_grants`, the composite
keys and the `tenant_id` columns, then the session, invite, membership and
tenant tables. Domain and audit rows from 0001–0004 are kept; what is lost is
workspace structure (memberships, invites, grants, multi-member tenants).
Before downgrading a database that has real workspaces, export
`tenants`, `tenant_memberships`, `tenant_invites` and `account_grants` (e.g.
`pg_dump -t ...`). The cluster-wide `algobots_app` role is not dropped; its
grants in this database are revoked.
"""

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TENANT_OWNED = ("accounts", "strategies", "orders", "decisions", "clamp_events")
RLS_TABLES = (*TENANT_OWNED, "account_grants")

_POLICY_EXPR = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"

_PG_CREATE_APP_ROLE = """
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'algobots_app')
     AND EXISTS (
       SELECT 1 FROM pg_roles
       WHERE rolname = current_user AND (rolsuper OR rolcreaterole)
     ) THEN
    CREATE ROLE algobots_app NOLOGIN NOSUPERUSER NOBYPASSRLS;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'algobots_app') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA public TO algobots_app';
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO algobots_app';
  END IF;
END
$$
"""

_PG_REVOKE_APP_ROLE = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'algobots_app') THEN
    EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM algobots_app';
  END IF;
END
$$
"""


def _ts(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "personal_owner_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=True,
            unique=True,
        ),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        _ts("created_at", nullable=False),
    )
    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        _ts("created_at", nullable=False),
        _ts("updated_at"),
        _ts("revoked_at"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_memberships_tenant_user"),
    )
    op.create_index("ix_tenant_memberships_user", "tenant_memberships", ["user_id"])
    op.create_table(
        "tenant_invites",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("invited_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        _ts("expires_at", nullable=False),
        _ts("redeemed_at"),
        sa.Column("redeemed_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        _ts("revoked_at"),
        _ts("created_at", nullable=False),
    )
    op.create_index("ix_tenant_invites_tenant", "tenant_invites", ["tenant_id"])
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=True),
        _ts("created_at", nullable=False),
        _ts("expires_at", nullable=False),
        _ts("revoked_at"),
    )
    op.create_index("ix_auth_sessions_user", "auth_sessions", ["user_id"])

    for table in (*TENANT_OWNED, "audit_log"):
        op.add_column(table, sa.Column("tenant_id", sa.Uuid(), nullable=True))

    # Backfill: one personal tenant + owner membership per existing user.
    users = sa.table(
        "users",
        sa.column("id", sa.Uuid()),
        sa.column("display_name", sa.String()),
    )
    tenants = sa.table(
        "tenants",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("personal_owner_user_id", sa.Uuid()),
        sa.column("created_by_user_id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    memberships = sa.table(
        "tenant_memberships",
        sa.column("id", sa.Uuid()),
        sa.column("tenant_id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("role", sa.String()),
        sa.column("status", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)
    for user_id, display_name in bind.execute(sa.select(users.c.id, users.c.display_name)):
        tenant_id = uuid4()
        bind.execute(
            tenants.insert().values(
                id=tenant_id,
                name=f"{display_name} (personal)"[:120],
                personal_owner_user_id=user_id,
                created_by_user_id=user_id,
                created_at=now,
            )
        )
        bind.execute(
            memberships.insert().values(
                id=uuid4(),
                tenant_id=tenant_id,
                user_id=user_id,
                role="owner",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
    for table in (*TENANT_OWNED, "audit_log"):
        op.execute(
            f"UPDATE {table} SET tenant_id = (SELECT t.id FROM tenants t "
            f"WHERE t.personal_owner_user_id = {table}.user_id) WHERE tenant_id IS NULL"
        )

    for table in TENANT_OWNED:
        with op.batch_alter_table(table) as batch:
            batch.alter_column("tenant_id", existing_type=sa.Uuid(), nullable=False)
            batch.create_foreign_key(f"fk_{table}_tenant", "tenants", ["tenant_id"], ["id"])
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"])
    op.create_index("uq_accounts_tenant_id", "accounts", ["tenant_id", "id"], unique=True)
    op.create_index("uq_strategies_tenant_id", "strategies", ["tenant_id", "id"], unique=True)

    for table, column, parent, name in (
        ("orders", "account_id", "accounts", "fk_orders_tenant_account"),
        ("decisions", "strategy_id", "strategies", "fk_decisions_tenant_strategy"),
        ("clamp_events", "account_id", "accounts", "fk_clamp_events_tenant_account"),
    ):
        with op.batch_alter_table(table) as batch:
            batch.create_foreign_key(name, parent, ["tenant_id", column], ["tenant_id", "id"])

    op.create_table(
        "account_grants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("grant", sa.String(length=32), nullable=False),
        sa.Column("granted_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        _ts("created_at", nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["accounts.tenant_id", "accounts.id"],
            name="fk_account_grants_tenant_account",
        ),
        sa.UniqueConstraint(
            "tenant_id", "account_id", "user_id", "grant", name="uq_account_grants_member_grant"
        ),
    )

    if is_pg:
        for table in RLS_TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY tenant_isolation ON {table} "
                f"USING ({_POLICY_EXPR}) WITH CHECK ({_POLICY_EXPR})"
            )
        op.execute(_PG_CREATE_APP_ROLE)


def downgrade() -> None:
    is_pg = op.get_bind().dialect.name == "postgresql"
    if is_pg:
        op.execute(_PG_REVOKE_APP_ROLE)
        for table in RLS_TABLES:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("account_grants")
    for table, name in (
        ("orders", "fk_orders_tenant_account"),
        ("decisions", "fk_decisions_tenant_strategy"),
        ("clamp_events", "fk_clamp_events_tenant_account"),
    ):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(name, type_="foreignkey")
    op.drop_index("uq_strategies_tenant_id", table_name="strategies")
    op.drop_index("uq_accounts_tenant_id", table_name="accounts")
    op.drop_index("ix_audit_log_tenant_id", table_name="audit_log")
    for table in TENANT_OWNED:
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_tenant", type_="foreignkey")
            batch.drop_column("tenant_id")
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_column("tenant_id")

    op.drop_index("ix_auth_sessions_user", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_tenant_invites_tenant", table_name="tenant_invites")
    op.drop_table("tenant_invites")
    op.drop_index("ix_tenant_memberships_user", table_name="tenant_memberships")
    op.drop_table("tenant_memberships")
    op.drop_table("tenants")
