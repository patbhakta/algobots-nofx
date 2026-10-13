"""fleet breaker scoped to (tenant, user) (ALG-3186 / ALG-3184 finding 2)

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-08

The fleet breaker used to be one row per USER: `effective_state` folded it
into every deployment that user owned, in every tenant, and a single reset
(anywhere the user still had `resource.write`, e.g. their personal tenant)
un-halted deployments in tenants where they had been demoted or revoked.

This migration scopes the breaker to the workspace:

1. add `fleet_breakers.tenant_id` (nullable first, then backfilled);
2. backfill: every existing row moves to its user's personal tenant (the
   oldest active `owner` membership — 0005 guarantees one per user, so day-one
   state is personal-tenant-only and no row is left behind);
3. make `tenant_id` NOT NULL with an FK to `tenants.id`;
4. replace the unique index on `user_id` with `uq_fleet_breakers_tenant_user`
   on `(tenant_id, user_id)`.

Downgrade guidance
------------------
`alembic downgrade 0005` deletes every non-personal-tenant breaker row (a
tenant cannot own a breaker row anymore) and restores the per-user unique
index. Reset/trip state stored on deleted rows is lost; personal-tenant
breaker state survives.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_BACKFILL = """
UPDATE fleet_breakers
SET tenant_id = (
    SELECT m.tenant_id
    FROM tenant_memberships m
    WHERE m.user_id = fleet_breakers.user_id
      AND m.role = 'owner'
      AND m.status = 'active'
    ORDER BY m.created_at
    LIMIT 1
)
"""

# Downgrade keeps the personal-tenant row when a user somehow has several.
# IS DISTINCT FROM: the SQLite-only ``IS NOT (subquery)`` spelling is a syntax
# error on PostgreSQL (the pg_rls suite downgrades to base on teardown).
_DEDUPE = """
DELETE FROM fleet_breakers
WHERE tenant_id IS DISTINCT FROM (
    SELECT m.tenant_id
    FROM tenant_memberships m
    WHERE m.user_id = fleet_breakers.user_id
      AND m.role = 'owner'
      AND m.status = 'active'
    ORDER BY m.created_at
    LIMIT 1
)
"""


def upgrade() -> None:
    op.add_column("fleet_breakers", sa.Column("tenant_id", sa.Uuid(), nullable=True))
    op.execute(_BACKFILL)
    op.drop_index("uq_fleet_breakers_user_id", table_name="fleet_breakers")
    with op.batch_alter_table("fleet_breakers") as batch:
        batch.alter_column("tenant_id", existing_type=sa.Uuid(), nullable=False)
        batch.create_foreign_key(
            "fk_fleet_breakers_tenant", "tenants", ["tenant_id"], ["id"]
        )
    op.create_index(
        "uq_fleet_breakers_tenant_user",
        "fleet_breakers",
        ["tenant_id", "user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_fleet_breakers_tenant_user", table_name="fleet_breakers")
    with op.batch_alter_table("fleet_breakers") as batch:
        batch.drop_constraint("fk_fleet_breakers_tenant", type_="foreignkey")
        batch.alter_column("tenant_id", existing_type=sa.Uuid(), nullable=True)
    op.execute(_DEDUPE)
    with op.batch_alter_table("fleet_breakers") as batch:
        batch.drop_column("tenant_id")
    op.create_index("uq_fleet_breakers_user_id", "fleet_breakers", ["user_id"], unique=True)
