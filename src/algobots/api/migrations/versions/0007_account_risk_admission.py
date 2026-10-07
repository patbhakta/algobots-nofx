"""account risk admission: pools, reservations, controls, marks (ALG-3104 / A08)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-07

Five tables for the A08 admission spine:

- ``account_admissions`` — one funds pool per (tenant, account) plus the
  ``version`` epoch the admission compare-and-swap serializes on;
- ``account_inventories`` — sellable inventory pools for SELL-side
  reservations;
- ``reservations`` — the persisted claims (contract ``Reservation`` @1.0 is
  the wire shape). Row-level CHECKs hold the lifecycle law at the DB level:
  a state is one of the four known states, a RELEASED row must carry its
  release reason (reconciled rejection / canceled / filled / expired /
  operator correction), and an UNCERTAIN row keeps its claim (it is active).
- ``account_controls`` — operator controls; flatten keeps separate actor and
  expiry columns (separately authorized, never implied by a pause);
- ``instrument_marks`` — last known mark with QUALITY and observation time
  (the stale-state gate consumes exactly this).
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

RESERVATION_STATES = ("HELD", "UNCERTAIN", "CONSUMED", "RELEASED")
RESERVATION_KINDS = ("CASH", "INVENTORY", "MARGIN")
ACTIVE_RESERVATION_WHERE = "state IN ('HELD', 'UNCERTAIN')"


def upgrade() -> None:
    op.create_table(
        "account_admissions",
        sa.Column("tenant_id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.String(length=128), primary_key=True),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("cash_available_text", sa.Text(), nullable=False),
        sa.Column("cash_reserved_text", sa.Text(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "account_inventories",
        sa.Column("tenant_id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.String(length=128), primary_key=True),
        sa.Column("instrument_id", sa.String(length=128), primary_key=True),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("held_text", sa.Text(), nullable=False, server_default="0"),
        sa.Column("reserved_text", sa.Text(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "reservations",
        sa.Column("reservation_id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("plan_id", sa.String(length=128), nullable=False),
        sa.Column("child_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("instrument_id", sa.String(length=128), nullable=True),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("amount_text", sa.Text(), nullable=False),
        sa.Column("buffer_text", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="HELD"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_reason", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            "state IN (" + ", ".join(f"'{s}'" for s in RESERVATION_STATES) + ")",
            name="ck_reservations_state",
        ),
        sa.CheckConstraint(
            "kind IN (" + ", ".join(f"'{k}'" for k in RESERVATION_KINDS) + ")",
            name="ck_reservations_kind",
        ),
        sa.CheckConstraint(
            "state <> 'RELEASED' OR release_reason IS NOT NULL",
            name="ck_reservations_release_needs_reason",
        ),
    )
    op.create_index("ix_reservations_tenant_id", "reservations", ["tenant_id"])
    op.create_index(
        "uq_reservations_plan_child",
        "reservations",
        ["tenant_id", "plan_id", "child_id"],
        unique=True,
    )
    op.create_index(
        "ix_reservations_tenant_account_state",
        "reservations",
        ["tenant_id", "account_id", "state"],
    )

    op.create_table(
        "account_controls",
        sa.Column("tenant_id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.String(length=128), primary_key=True),
        sa.Column("entries_paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "cancel_entries_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("reduce_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("flatten_authorized_by", sa.String(length=128), nullable=True),
        sa.Column("flatten_authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("flatten_valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(flatten_authorized_by IS NULL) = (flatten_valid_until IS NULL)",
            name="ck_controls_flatten_window_complete",
        ),
    )

    op.create_table(
        "instrument_marks",
        sa.Column("tenant_id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.String(length=128), primary_key=True),
        sa.Column("instrument_id", sa.String(length=128), primary_key=True),
        sa.Column("price_text", sa.Text(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("quality", sa.String(length=16), nullable=False, server_default="STALE_CACHE"),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("instrument_marks")
    op.drop_table("account_controls")
    op.drop_index("ix_reservations_tenant_account_state", table_name="reservations")
    op.drop_index("uq_reservations_plan_child", table_name="reservations")
    op.drop_index("ix_reservations_tenant_id", table_name="reservations")
    op.drop_table("reservations")
    op.drop_table("account_inventories")
    op.drop_table("account_admissions")
