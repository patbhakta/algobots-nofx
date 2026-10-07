"""execution ledger: intents, plans, child orders, outbox, receipts (ALG-3103 / A07)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-07

Append-only enforcement for `order_event_receipts`, `fill_receipts` and
`cash_movements` lives AT THE DATABASE LEVEL (BEFORE UPDATE / BEFORE DELETE
triggers raise, mirroring the `action_ledger` precedent in 0004): the receipt
and settlement history behind AC4's exactly-once guarantee cannot be rewritten
by any application path or ad-hoc SQL.

The partial unique index `uq_execution_intents_active_entry` is the
active-entry guard: at most one ACTIVE intent per (tenant, account,
business_hash) — repeated business signals with different transport keys are
rejected by the database, not by application discipline.
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

ACTIVE_ENTRY_STATUSES = (
    "ACCEPTED",
    "PLANNED",
    "SUBMITTED",
    "ACKNOWLEDGED",
    "PARTIALLY_FILLED",
    "PENDING_CANCEL",
    "PENDING_REPLACE",
    "UNKNOWN",
)
# The guard protects entries only; exits (cancel/reduce/flatten) with the same
# business shape stay admissible.
ENTRY_ACTION_VALUES = ("CREATE_TARGET", "PLACE_ORDER")
_ACTIVE_ENTRY_WHERE = (
    "status IN (" + ", ".join(f"'{s}'" for s in ACTIVE_ENTRY_STATUSES) + ")"
    " AND action IN (" + ", ".join(f"'{a}'" for a in ENTRY_ACTION_VALUES) + ")"
)

APPEND_ONLY_TABLES = ("order_event_receipts", "fill_receipts", "cash_movements")


def _sqlite_triggers(table: str) -> list[str]:
    msg = f"{table} is append-only"
    return [
        f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} "
        f"BEGIN SELECT RAISE(ABORT, '{msg}: UPDATE forbidden'); END",
        f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
        f"BEGIN SELECT RAISE(ABORT, '{msg}: DELETE forbidden'); END",
    ]


def _pg_triggers(table: str) -> list[str]:
    func = f"{table}_append_only"
    return [
        f"CREATE FUNCTION {func}() RETURNS trigger AS $$\n"
        f"BEGIN\n"
        f"  RAISE EXCEPTION '{table} is append-only: % forbidden', TG_OP;\n"
        f"END;\n"
        f"$$ LANGUAGE plpgsql",
        f"CREATE TRIGGER {table}_no_rewrite BEFORE UPDATE OR DELETE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION {func}()",
    ]


def upgrade() -> None:
    op.create_table(
        "execution_intents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("deployment_id", sa.String(length=128), nullable=True),
        sa.Column("authority_ref", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("business_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_execution_intents_tenant_id", "execution_intents", ["tenant_id"])
    op.create_index(
        "uq_execution_intents_tenant_idem",
        "execution_intents",
        ["tenant_id", "idempotency_key"],
        unique=True,
    )
    op.create_index(
        "uq_execution_intents_active_entry",
        "execution_intents",
        ["tenant_id", "account_id", "business_hash"],
        unique=True,
        sqlite_where=sa.text(_ACTIVE_ENTRY_WHERE),
        postgresql_where=sa.text(_ACTIVE_ENTRY_WHERE),
    )
    op.create_index(
        "ix_execution_intents_tenant_account_status",
        "execution_intents",
        ["tenant_id", "account_id", "status"],
    )

    op.create_table(
        "order_plans",
        sa.Column("plan_id", sa.String(length=128), primary_key=True),
        sa.Column(
            "intent_id", sa.Uuid(), sa.ForeignKey("execution_intents.id"), nullable=False
        ),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("plan_hash", sa.String(length=64), nullable=False),
        sa.Column("plan_json", sa.Text(), nullable=False),
        sa.Column("reservations_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_order_plans_intent_id", "order_plans", ["intent_id"])

    op.create_table(
        "child_orders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "intent_id", sa.Uuid(), sa.ForeignKey("execution_intents.id"), nullable=False
        ),
        sa.Column(
            "plan_id", sa.String(length=128), sa.ForeignKey("order_plans.plan_id"), nullable=False
        ),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("child_id", sa.String(length=128), nullable=False),
        sa.Column("client_order_id", sa.String(length=64), nullable=False),
        sa.Column("broker_order_id", sa.String(length=128), nullable=True),
        sa.Column("instrument_id", sa.String(length=128), nullable=False),
        sa.Column("product", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity_text", sa.Text(), nullable=False),
        sa.Column("limit_price_text", sa.Text(), nullable=True),
        sa.Column("max_notional_text", sa.Text(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("filled_qty_text", sa.Text(), nullable=False, server_default="0"),
        sa.Column("avg_px_text", sa.Text(), nullable=True),
        sa.Column("fees_text", sa.Text(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_child_orders_tenant_id", "child_orders", ["tenant_id"])
    op.create_index("ix_child_orders_intent_id", "child_orders", ["intent_id"])
    op.create_index(
        "uq_child_orders_tenant_account_client_id",
        "child_orders",
        ["tenant_id", "account_id", "client_order_id"],
        unique=True,
    )
    op.create_index(
        "uq_child_orders_tenant_account_broker_id",
        "child_orders",
        ["tenant_id", "account_id", "broker_order_id"],
        unique=True,
    )
    op.create_index(
        "uq_child_orders_intent_child", "child_orders", ["intent_id", "child_id"], unique=True
    )

    op.create_table(
        "order_event_receipts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("dedup_key", sa.String(length=256), nullable=False),
        sa.Column(
            "child_order_id", sa.Uuid(), sa.ForeignKey("child_orders.id"), nullable=True
        ),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("reconciliation_origin", sa.Boolean(), nullable=False),
        sa.Column("event_json", sa.Text(), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_order_event_receipts_child_order_id", "order_event_receipts", ["child_order_id"]
    )
    op.create_index(
        "uq_order_event_receipts_dedup", "order_event_receipts", ["dedup_key"], unique=True
    )

    op.create_table(
        "fill_receipts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("dedup_key", sa.String(length=256), nullable=False),
        sa.Column("child_order_id", sa.Uuid(), sa.ForeignKey("child_orders.id"), nullable=True),
        sa.Column("fill_id", sa.String(length=128), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("instrument_id", sa.String(length=128), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity_text", sa.Text(), nullable=False),
        sa.Column("price_text", sa.Text(), nullable=False),
        sa.Column("fee_text", sa.Text(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("corrects_fill_id", sa.String(length=128), nullable=True),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_fill_receipts_child_order_id", "fill_receipts", ["child_order_id"])
    op.create_index("uq_fill_receipts_dedup", "fill_receipts", ["dedup_key"], unique=True)

    op.create_table(
        "cash_movements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("movement_key", sa.String(length=256), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("amount_text", sa.Text(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("ref_type", sa.String(length=16), nullable=False),
        sa.Column("ref_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cash_movements_tenant_id", "cash_movements", ["tenant_id"])
    op.create_index("uq_cash_movements_key", "cash_movements", ["movement_key"], unique=True)

    op.create_table(
        "intent_outbox",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "intent_id", sa.Uuid(), sa.ForeignKey("execution_intents.id"), nullable=False
        ),
        sa.Column("plan_id", sa.String(length=128), nullable=False),
        sa.Column(
            "child_order_id", sa.Uuid(), sa.ForeignKey("child_orders.id"), nullable=False
        ),
        sa.Column("command_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("command_json", sa.Text(), nullable=False),
        sa.Column("emitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_intent_outbox_tenant_id", "intent_outbox", ["tenant_id"])
    op.create_index("ix_intent_outbox_intent_id", "intent_outbox", ["intent_id"])
    op.create_index("ix_intent_outbox_child_order_id", "intent_outbox", ["child_order_id"])
    op.create_index(
        "ix_intent_outbox_status_created", "intent_outbox", ["status", "created_at"]
    )

    op.create_table(
        "account_freezes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=128), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
    )
    op.create_index("ix_account_freezes_tenant_id", "account_freezes", ["tenant_id"])
    op.create_index(
        "uq_account_freezes_active",
        "account_freezes",
        ["tenant_id", "account_id"],
        unique=True,
        sqlite_where=sa.text("resolved_at IS NULL"),
        postgresql_where=sa.text("resolved_at IS NULL"),
    )

    bind = op.get_bind()
    for table in APPEND_ONLY_TABLES:
        if bind.dialect.name == "sqlite":
            for stmt in _sqlite_triggers(table):
                op.execute(stmt)
        else:
            for stmt in _pg_triggers(table):
                op.execute(stmt)


def downgrade() -> None:
    bind = op.get_bind()
    for table in APPEND_ONLY_TABLES:
        if bind.dialect.name == "sqlite":
            op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update")
            op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete")
        else:
            op.execute(f"DROP TRIGGER IF EXISTS {table}_no_rewrite ON {table}")
            op.execute(f"DROP FUNCTION IF EXISTS {table}_append_only()")

    op.drop_index("uq_account_freezes_active", table_name="account_freezes")
    op.drop_index("ix_account_freezes_tenant_id", table_name="account_freezes")
    op.drop_table("account_freezes")

    op.drop_index("ix_intent_outbox_status_created", table_name="intent_outbox")
    op.drop_index("ix_intent_outbox_child_order_id", table_name="intent_outbox")
    op.drop_index("ix_intent_outbox_intent_id", table_name="intent_outbox")
    op.drop_index("ix_intent_outbox_tenant_id", table_name="intent_outbox")
    op.drop_table("intent_outbox")

    op.drop_index("uq_cash_movements_key", table_name="cash_movements")
    op.drop_index("ix_cash_movements_tenant_id", table_name="cash_movements")
    op.drop_table("cash_movements")

    op.drop_index("uq_fill_receipts_dedup", table_name="fill_receipts")
    op.drop_index("ix_fill_receipts_child_order_id", table_name="fill_receipts")
    op.drop_table("fill_receipts")

    op.drop_index("uq_order_event_receipts_dedup", table_name="order_event_receipts")
    op.drop_index("ix_order_event_receipts_child_order_id", table_name="order_event_receipts")
    op.drop_table("order_event_receipts")

    op.drop_index("uq_child_orders_intent_child", table_name="child_orders")
    op.drop_index("uq_child_orders_tenant_account_broker_id", table_name="child_orders")
    op.drop_index("uq_child_orders_tenant_account_client_id", table_name="child_orders")
    op.drop_index("ix_child_orders_intent_id", table_name="child_orders")
    op.drop_index("ix_child_orders_tenant_id", table_name="child_orders")
    op.drop_table("child_orders")

    op.drop_index("ix_order_plans_intent_id", table_name="order_plans")
    op.drop_table("order_plans")

    op.drop_index("ix_execution_intents_tenant_account_status", table_name="execution_intents")
    op.drop_index("uq_execution_intents_active_entry", table_name="execution_intents")
    op.drop_index("uq_execution_intents_tenant_idem", table_name="execution_intents")
    op.drop_index("ix_execution_intents_tenant_id", table_name="execution_intents")
    op.drop_table("execution_intents")
