"""broker connections, external account identities, secret grants (ALG-3100)

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-12

A04 (accounts, secrets, capability registry) adds three tenant-scoped tables.
Purely additive — no existing table, column or row is modified or deleted:

1. `broker_connections` — per-account provider/environment configuration with
   broker session state (UNCONFIGURED/CONNECTING/CONNECTED/DEGRADED/EXPIRED/
   REVOKED), egress allowlist, capability revision and the reconciliation
   posture. This is the broker *session* authentication surface, separate
   from control-plane user authentication (auth-contract rule).
2. `external_account_identities` — the venue-side identity of each account as
   a deterministic sha256 fingerprint, globally unique so the same external
   account cannot be connected twice across tenants. The fingerprint carries
   no tenant/user/credential data: the uniqueness conflict alone never
   reveals who owns the existing connection.
3. `secret_grants` — the SecretResolver ACL: one row per (account, assigned
   execution identity) with allowed environments, egress allowlist, rotation
   policy, state machine and secret version. Rotation bumps the version in
   place; revocation freezes resolution and flags reconciliation.

PostgreSQL only: ENABLE + FORCE ROW LEVEL SECURITY on all three tables with
the same `app.tenant_id` policy family as migration 0008 (default deny when
the setting is absent).

Downgrade guidance
------------------
`alembic downgrade 0009` drops only these three tables. Accounts, strategies
and their credentials from earlier packets are untouched; what is lost is the
A04 registry shape (connections, external identities, resolution grants).
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

RLS_TABLES = ("broker_connections", "external_account_identities", "secret_grants")

_POLICY_EXPR = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"

# 0008's `GRANT ... ON ALL TABLES` only covered tables existing then; the A04
# tables must grant DML to the app role themselves (same guard style).
_PG_GRANT_APP_ROLE = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'algobots_app') THEN
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON broker_connections, '
            'external_account_identities, secret_grants TO algobots_app';
  END IF;
END
$$
"""


def _ts(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    is_pg = op.get_bind().dialect.name == "postgresql"

    op.create_table(
        "broker_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("session_state", sa.String(length=16), nullable=False, server_default="UNCONFIGURED"),
        sa.Column("egress_allowlist", sa.Text(), nullable=False, server_default=""),
        sa.Column("capabilities_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sandbox_fidelity", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("reconciliation_state", sa.String(length=32), nullable=False, server_default="ok"),
        sa.Column("reconciliation_reason", sa.String(length=200), nullable=False, server_default=""),
        _ts("session_checked_at"),
        _ts("created_at", nullable=False),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["accounts.tenant_id", "accounts.id"],
            name="fk_broker_connections_tenant_account",
            ondelete="CASCADE",
        ),
    )
    op.create_index("uq_broker_connections_account", "broker_connections", ["account_id"], unique=True)
    op.create_index("ix_broker_connections_tenant", "broker_connections", ["tenant_id"])

    op.create_table(
        "external_account_identities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("ownership_epoch", sa.Integer(), nullable=False, server_default="1"),
        _ts("created_at", nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["accounts.tenant_id", "accounts.id"],
            name="fk_external_account_identities_tenant_account",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "uq_external_account_fingerprint", "external_account_identities", ["fingerprint"], unique=True
    )
    op.create_index(
        "ix_external_account_identities_tenant", "external_account_identities", ["tenant_id"]
    )

    op.create_table(
        "secret_grants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_principal_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("granted_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("allowed_environments", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("egress_allowlist", sa.Text(), nullable=False, server_default=""),
        sa.Column("rotation_policy", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="ACTIVE"),
        sa.Column("secret_version", sa.Integer(), nullable=False, server_default="1"),
        _ts("created_at", nullable=False),
        _ts("rotated_at"),
        _ts("revoked_at"),
        sa.Column("last_denial_reason", sa.String(length=128), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["accounts.tenant_id", "accounts.id"],
            name="fk_secret_grants_tenant_account",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("account_id", "assigned_principal_id", name="uq_secret_grants_principal"),
    )
    op.create_index("ix_secret_grants_tenant_state", "secret_grants", ["tenant_id", "state"])

    if is_pg:
        for table in RLS_TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY tenant_isolation ON {table} "
                f"USING ({_POLICY_EXPR}) WITH CHECK ({_POLICY_EXPR})"
            )
        op.execute(_PG_GRANT_APP_ROLE)


def downgrade() -> None:
    is_pg = op.get_bind().dialect.name == "postgresql"
    if is_pg:
        for table in RLS_TABLES:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_secret_grants_tenant_state", table_name="secret_grants")
    op.drop_table("secret_grants")
    op.drop_index("ix_external_account_identities_tenant", table_name="external_account_identities")
    op.drop_index("uq_external_account_fingerprint", table_name="external_account_identities")
    op.drop_table("external_account_identities")
    op.drop_index("ix_broker_connections_tenant", table_name="broker_connections")
    op.drop_index("uq_broker_connections_account", table_name="broker_connections")
    op.drop_table("broker_connections")
