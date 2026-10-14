"""gateway projection of the node event streams (ALG-3370, ROADMAP-v3 P1.2)

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-14

P1.2: the gateway serves `/orders`, `/positions`, `/accounts` and `/events`
from a fold of the nodes' Redis event streams held here, never from a node's
memory. Five additive tables, none of which any earlier packet reads:

1. `gateway_events` — the append-only log. `seq` is the monotonic cursor the
   contract's `Event` requires, so a client reconnecting to `/events` with
   `?since=` resumes exactly where it stopped. Because the column is a
   database sequence and not a count of what some process has seen, the
   cursor keeps counting across a gateway restart instead of restarting at 0
   and replaying the world.
2. `gateway_orders` — one row per admitted order, keyed by the client order
   id the gateway issued at admission (which is also the idempotency key).
3. `gateway_fills` — one row per execution, `UNIQUE (client_order_id,
   trade_id)`. This constraint is the sprint's at-least-once defence: a node
   restart can replay a fill (docs/bridge.md), and the second fold of the
   same `trade_id` has to be refused by the database rather than silently
   added to a member's filled quantity.
4. `gateway_positions` — open positions by the node's own position id.
5. `gateway_balances` — the last `AccountState` each node reported.

Money and quantities are `TEXT`, not `NUMERIC` or `FLOAT`. The contract's
`Decimal` is a string (`^-?[0-9]+(\\.[0-9]+)?$`) and the projection sums fills
in Python `Decimal`, so storing the canonical digits keeps one exact code path
on both PostgreSQL (the deploy) and SQLite (CI, which has no DECIMAL type and
would round-trip `NUMERIC` through binary floating point). A rounding error
here is a wrong number on a member's balance.

No row-level security, unlike 0008/0010: these tables are keyed by the
gateway's own `account_id` strings rather than a control-plane `tenant_id`
uuid, and the gateway has no `app.tenant_id` on its connection. Scoping is
done in every query from the caller's granted accounts
(`auth.scope_accounts`), which is what `tests/gateway` exercises. Giving these
tables a tenant policy would need the gateway to carry a tenant context it
does not have in Phase 1, and a policy that is never satisfied denies every
read.

Downgrade guidance
------------------
`alembic downgrade 0010` drops only these five tables. Nothing outside the
Phase 1 gateway reads them, so no earlier packet loses data; what is lost is
the gateway's folded state, which the nodes can re-emit.
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

TABLES = (
    "gateway_balances",
    "gateway_positions",
    "gateway_fills",
    "gateway_orders",
    "gateway_events",
)

# 0008's `GRANT ... ON ALL TABLES` only covered tables existing then, so each
# later migration grants DML to the app role itself (0010's guard style).
_PG_GRANT_APP_ROLE = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'algobots_app') THEN
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON gateway_events, '
            'gateway_orders, gateway_fills, gateway_positions, '
            'gateway_balances TO algobots_app';
    EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE gateway_events_seq_seq '
            'TO algobots_app';
  END IF;
END
$$
"""


def _seq() -> sa.Column:
    """The event cursor: BIGSERIAL on PostgreSQL, rowid alias on SQLite.

    SQLite only auto-assigns an `INTEGER PRIMARY KEY`, not a `BIGINT` one, so
    the variant is required for the CI database to hand out a `seq` at all.
    """
    return sa.Column(
        "seq",
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )


def _dec(name: str, nullable: bool = True) -> sa.Column:
    """A contract `Decimal`: exact digits as text (see the module docstring)."""
    return sa.Column(name, sa.Text(), nullable=nullable)


def _ts(name: str, nullable: bool = False) -> sa.Column:
    """An ISO-8601 instant, stored as the node emitted it.

    Kept as text on purpose: the contract renders `date-time` with exactly
    millisecond precision and a `Z` suffix, and these values are transcribed
    from the node rather than computed here. A round trip through a timestamp
    column would reformat them, so `/orders` would stop returning what the
    node actually said.
    """
    return sa.Column(name, sa.String(length=32), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "gateway_events",
        _seq(),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        _ts("ts_event"),
        # The contract Event's `order`/`fill`/`position`/`account` bodies,
        # exactly as they were sent, so a resumed stream replays the frame it
        # would have delivered and not a re-render of today's row.
        sa.Column("payload", sa.Text(), nullable=False, server_default="{}"),
    )
    # `/events` filters by account and resumes after a seq; this is that query.
    op.create_index("ix_gateway_events_account_seq", "gateway_events", ["account_id", "seq"])

    op.create_table(
        "gateway_orders",
        sa.Column("client_order_id", sa.String(length=64), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        _dec("qty", nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="PAPER"),
        sa.Column("venue_order_id", sa.String(length=64), nullable=True),
        _dec("filled_qty", nullable=False),
        _dec("avg_px"),
        _dec("limit_px"),
        sa.Column("time_in_force", sa.String(length=8), nullable=True),
        sa.Column("reason", sa.String(length=512), nullable=True),
        _ts("submitted_at"),
        _ts("updated_at"),
        # Gateway bookkeeping, never serialized (the contract sets
        # `additionalProperties: false`): the idempotency comparison and the
        # node a command for this order is addressed to.
        sa.Column("fingerprint", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("node", sa.String(length=64), nullable=False, server_default=""),
        # `/orders` is newest first. Admission order, not `submitted_at`: two
        # orders admitted in the same millisecond still have to come back in a
        # stable order, or `limit` would drop an arbitrary one of them.
        sa.Column(
            "ordinal",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index(
        "ix_gateway_orders_account_ordinal", "gateway_orders", ["account_id", "ordinal"]
    )
    op.create_index("ix_gateway_orders_status", "gateway_orders", ["account_id", "status"])

    op.create_table(
        "gateway_fills",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "client_order_id",
            sa.String(length=64),
            sa.ForeignKey("gateway_orders.client_order_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trade_id", sa.String(length=64), nullable=False),
        _dec("qty", nullable=False),
        _dec("px", nullable=False),
        _ts("ts_event"),
        _dec("commission"),
        sa.Column("commission_currency", sa.String(length=16), nullable=True),
        # Delivery is at-least-once: the same fill can arrive twice. The
        # database refuses the second one.
        sa.UniqueConstraint("client_order_id", "trade_id", name="uq_gateway_fills_trade"),
    )
    op.create_index("ix_gateway_fills_order", "gateway_fills", ["client_order_id", "id"])

    op.create_table(
        "gateway_positions",
        sa.Column("position_id", sa.String(length=64), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        _dec("qty", nullable=False),
        _dec("avg_px", nullable=False),
        _ts("opened_at"),
        _dec("unrealized_pnl"),
        _dec("realized_pnl"),
    )
    op.create_index("ix_gateway_positions_account", "gateway_positions", ["account_id"])

    op.create_table(
        "gateway_balances",
        sa.Column("account_id", sa.String(length=64), primary_key=True),
        sa.Column("currency", sa.String(length=16), primary_key=True),
        _dec("total", nullable=False),
        _dec("free", nullable=False),
        _dec("locked"),
        # The node reports balances as an ordered list; keep its order so
        # `/accounts` does not reshuffle a member's currencies between reads.
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(_PG_GRANT_APP_ROLE)


def downgrade() -> None:
    op.drop_index("ix_gateway_positions_account", table_name="gateway_positions")
    op.drop_index("ix_gateway_fills_order", table_name="gateway_fills")
    op.drop_index("ix_gateway_orders_status", table_name="gateway_orders")
    op.drop_index("ix_gateway_orders_account_ordinal", table_name="gateway_orders")
    op.drop_index("ix_gateway_events_account_seq", table_name="gateway_events")
    for table in TABLES:
        op.drop_table(table)
