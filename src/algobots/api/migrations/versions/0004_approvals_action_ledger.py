"""approval queue + append-only action ledger (ALG-3092)

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-27

Append-only enforcement for `action_ledger` lives AT THE DATABASE LEVEL:
BEFORE UPDATE / BEFORE DELETE triggers raise, so no application path (and
no ad-hoc SQL) can rewrite history. This is deliberately distinct from the
S0.2 middleware `audit_log` table (HTTP request audit): the action ledger
records approval-domain actions with reason and latency per action.
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_LEDGER_IMMUTABLE_MSG = "action_ledger is append-only"

_SQLITE_NO_UPDATE = (
    f"CREATE TRIGGER action_ledger_no_update BEFORE UPDATE ON action_ledger "
    f"BEGIN SELECT RAISE(ABORT, '{_LEDGER_IMMUTABLE_MSG}: UPDATE forbidden'); END"
)
_SQLITE_NO_DELETE = (
    f"CREATE TRIGGER action_ledger_no_delete BEFORE DELETE ON action_ledger "
    f"BEGIN SELECT RAISE(ABORT, '{_LEDGER_IMMUTABLE_MSG}: DELETE forbidden'); END"
)

_PG_FUNCTION = (
    "CREATE FUNCTION action_ledger_append_only() RETURNS trigger AS $$\n"
    "BEGIN\n"
    f"  RAISE EXCEPTION '{_LEDGER_IMMUTABLE_MSG}: % forbidden', TG_OP;\n"
    "END;\n"
    "$$ LANGUAGE plpgsql"
)
_PG_TRIGGER = (
    "CREATE TRIGGER action_ledger_no_rewrite BEFORE UPDATE OR DELETE ON action_ledger "
    "FOR EACH ROW EXECUTE FUNCTION action_ledger_append_only()"
)


def upgrade() -> None:
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("order_id", sa.Uuid(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column(
            "deployment_id",
            sa.Uuid(),
            sa.ForeignKey("deployments.id"),
            nullable=True,
        ),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("limit_price", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("park_reason", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("parked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("uq_approval_requests_order_id", "approval_requests", ["order_id"], unique=True)
    op.create_index("ix_approval_requests_user_id", "approval_requests", ["user_id"])
    op.create_index("ix_approval_requests_account_id", "approval_requests", ["account_id"])
    op.create_index("ix_approval_requests_deployment_id", "approval_requests", ["deployment_id"])
    op.create_index("ix_approval_requests_user_status", "approval_requests", ["user_id", "status"])
    op.create_index(
        "ix_approval_requests_user_parked", "approval_requests", ["user_id", "parked_at"]
    )

    op.create_table(
        "broadcasts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "approval_request_id",
            sa.Uuid(),
            sa.ForeignKey("approval_requests.id"),
            nullable=False,
        ),
        sa.Column("total_qty", sa.Float(), nullable=False),
        sa.Column("sent_qty", sa.Float(), nullable=False),
        sa.Column("queued_qty", sa.Float(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_broadcasts_approval_request_id", "broadcasts", ["approval_request_id"], unique=True
    )
    op.create_index("ix_broadcasts_user_id", "broadcasts", ["user_id"])
    op.create_index("ix_broadcasts_user_created", "broadcasts", ["user_id", "created_at"])

    op.create_table(
        "action_ledger",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("detail_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_action_ledger_user_id", "action_ledger", ["user_id"])
    op.create_index("ix_action_ledger_user_created", "action_ledger", ["user_id", "created_at"])

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(_SQLITE_NO_UPDATE)
        op.execute(_SQLITE_NO_DELETE)
    else:
        op.execute(_PG_FUNCTION)
        op.execute(_PG_TRIGGER)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS action_ledger_no_update")
        op.execute("DROP TRIGGER IF EXISTS action_ledger_no_delete")
    else:
        op.execute("DROP TRIGGER IF EXISTS action_ledger_no_rewrite ON action_ledger")
        op.execute("DROP FUNCTION IF EXISTS action_ledger_append_only()")
    op.drop_index("ix_action_ledger_user_created", table_name="action_ledger")
    op.drop_index("ix_action_ledger_user_id", table_name="action_ledger")
    op.drop_table("action_ledger")
    op.drop_index("ix_broadcasts_user_created", table_name="broadcasts")
    op.drop_index("ix_broadcasts_user_id", table_name="broadcasts")
    op.drop_index("uq_broadcasts_approval_request_id", table_name="broadcasts")
    op.drop_table("broadcasts")
    op.drop_index("ix_approval_requests_user_parked", table_name="approval_requests")
    op.drop_index("ix_approval_requests_user_status", table_name="approval_requests")
    op.drop_index("ix_approval_requests_deployment_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_account_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_user_id", table_name="approval_requests")
    op.drop_index("uq_approval_requests_order_id", table_name="approval_requests")
    op.drop_table("approval_requests")
