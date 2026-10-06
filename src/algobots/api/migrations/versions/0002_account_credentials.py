"""account registry: encrypted credentials + unique per-user labels (ALG-3090)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_credentials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("encrypted_secrets", sa.Text(), nullable=False),
        sa.Column("key_id", sa.String(length=16), nullable=False),
        sa.Column("token_status", sa.String(length=16), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_refresh_error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_account_credentials_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_account_credentials_user"),
    )
    op.create_index(
        "uq_account_credentials_account_id", "account_credentials", ["account_id"], unique=True
    )
    op.create_index("ix_account_credentials_user_id", "account_credentials", ["user_id"])
    op.create_index(
        "ix_account_credentials_token_status", "account_credentials", ["token_status"]
    )
    # Registry semantics: labels are the per-user account nickname, unique per
    # tenant (multi-account-per-user-per-broker needs distinct handles).
    op.create_index("uq_accounts_user_label", "accounts", ["user_id", "label"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_accounts_user_label", table_name="accounts")
    op.drop_index("ix_account_credentials_token_status", table_name="account_credentials")
    op.drop_index("ix_account_credentials_user_id", table_name="account_credentials")
    op.drop_index("uq_account_credentials_account_id", table_name="account_credentials")
    op.drop_table("account_credentials")
