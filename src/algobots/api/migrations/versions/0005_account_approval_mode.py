"""accounts.approval_mode: Auto / Semi-auto per account (ALG-3266)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-07

Splits the approval axis from the environment axis: `mode` stays
paper|live (legacy `semi_auto` still parks), `approval_mode` is
auto|semi_auto. A PAPER account can now be Semi-auto, so its order-ticket
legs park in the S4.3 approval queue and fill on paper only when approved.
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("approval_mode", sa.String(length=16), nullable=False, server_default="auto"),
    )


def downgrade() -> None:
    with op.batch_alter_table("accounts") as batch:
        batch.drop_column("approval_mode")
