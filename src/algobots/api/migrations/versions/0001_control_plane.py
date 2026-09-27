"""control-plane skeleton: users, tenancy schema, and audit log (ALG-3078)

Revision ID: 0001
Revises:
Create Date: 2026-09-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "invite_codes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("claimed_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_invite_codes_code", "invite_codes", ["code"], unique=True)
    op.create_index("ix_invite_codes_created_by_user_id", "invite_codes", ["created_by_user_id"])

    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("broker", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("base_currency", sa.String(length=8), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"])

    op.create_table(
        "strategies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("params_json", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_strategies_user_id", "strategies", ["user_id"])

    op.create_table(
        "deployments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "strategy_id",
            sa.Uuid(),
            sa.ForeignKey("strategies.id"),
            nullable=False,
        ),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_deployments_user_id", "deployments", ["user_id"])
    op.create_index("ix_deployments_strategy_id", "deployments", ["strategy_id"])
    op.create_index("ix_deployments_account_id", "deployments", ["account_id"])

    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
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
        *_timestamps(),
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_index("ix_orders_account_id", "orders", ["account_id"])
    op.create_index("ix_orders_deployment_id", "orders", ["deployment_id"])
    op.create_index("ix_orders_user_created", "orders", ["user_id", "created_at"])

    op.create_table(
        "decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "strategy_id",
            sa.Uuid(),
            sa.ForeignKey("strategies.id"),
            nullable=False,
        ),
        sa.Column(
            "deployment_id",
            sa.Uuid(),
            sa.ForeignKey("deployments.id"),
            nullable=True,
        ),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_decisions_user_id", "decisions", ["user_id"])
    op.create_index("ix_decisions_strategy_id", "decisions", ["strategy_id"])
    op.create_index("ix_decisions_deployment_id", "decisions", ["deployment_id"])

    op.create_table(
        "clamp_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "deployment_id",
            sa.Uuid(),
            sa.ForeignKey("deployments.id"),
            nullable=True,
        ),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("clamp_kind", sa.String(length=64), nullable=False),
        sa.Column("old_value", sa.Float(), nullable=True),
        sa.Column("new_value", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_clamp_events_user_id", "clamp_events", ["user_id"])
    op.create_index("ix_clamp_events_deployment_id", "clamp_events", ["deployment_id"])
    op.create_index("ix_clamp_events_account_id", "clamp_events", ["account_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("resource", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("detail_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_user_created", "audit_log", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("clamp_events")
    op.drop_table("decisions")
    op.drop_table("orders")
    op.drop_table("deployments")
    op.drop_table("strategies")
    op.drop_table("accounts")
    op.drop_table("invite_codes")
    op.drop_table("users")
