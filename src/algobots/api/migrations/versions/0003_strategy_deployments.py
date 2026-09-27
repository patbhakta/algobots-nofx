"""strategy deployments: freeze columns, breakers, fleet breakers (ALG-3091)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# Partial-unique backstop for the duplicate-deployment guard: one ACTIVE
# deployment per (strategy, symbol, account). Stopped rows free the tuple.
_ACTIVE_WHERE = "status <> 'stopped'"


def upgrade() -> None:
    op.add_column(
        "deployments",
        sa.Column("symbol", sa.String(length=32), nullable=False, server_default=""),
    )
    op.add_column(
        "deployments",
        sa.Column("frozen_spec_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "deployments",
        sa.Column("artifact_hash", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "deployments",
        sa.Column("max_order_value", sa.String(length=64), nullable=False, server_default="0"),
    )
    op.add_column(
        "deployments",
        sa.Column("max_daily_loss", sa.String(length=64), nullable=False, server_default="0"),
    )
    op.add_column(
        "deployments",
        sa.Column("breaker_state", sa.String(length=16), nullable=False, server_default="closed"),
    )
    op.add_column(
        "deployments", sa.Column("breaker_reason", sa.Text(), nullable=False, server_default="")
    )
    op.add_column("deployments", sa.Column("tripped_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "uq_deployments_active_tuple",
        "deployments",
        ["strategy_id", "symbol", "account_id"],
        unique=True,
        sqlite_where=sa.text(_ACTIVE_WHERE),
        postgresql_where=sa.text(_ACTIVE_WHERE),
    )
    op.create_table(
        "fleet_breakers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("tripped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_fleet_breakers_user"),
    )
    op.create_index("uq_fleet_breakers_user_id", "fleet_breakers", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_fleet_breakers_user_id", table_name="fleet_breakers")
    op.drop_table("fleet_breakers")
    op.drop_index("uq_deployments_active_tuple", table_name="deployments")
    op.drop_column("deployments", "tripped_at")
    op.drop_column("deployments", "breaker_reason")
    op.drop_column("deployments", "breaker_state")
    op.drop_column("deployments", "max_daily_loss")
    op.drop_column("deployments", "max_order_value")
    op.drop_column("deployments", "artifact_hash")
    op.drop_column("deployments", "frozen_spec_json")
    op.drop_column("deployments", "symbol")
