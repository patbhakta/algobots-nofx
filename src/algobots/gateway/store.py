"""The projection, in Postgres. P1.2's answer to "what survives a restart".

``InMemoryProjection`` could serve the whole contract (P1.1) but forgot
everything when the process died. :class:`SqlProjection` is the same fold
written to the Phase 0 ``compose.yaml`` Postgres, so the gateway's "Done when"
holds: start a new gateway over the same database and ``/positions`` returns
the positions the old one had, because they were never in the old one's memory.

Three properties this module exists to guarantee:

1. **At-least-once is survivable.** ``docs/bridge.md``: a node restart can
   replay a fill. ``gateway_fills`` is ``UNIQUE (client_order_id, trade_id)``
   and :meth:`SqlProjection.add_fill` recomputes ``filled_qty`` and ``avg_px``
   as an aggregate *over the fills table* rather than adding to the value
   already stored. So re-folding a fill is a no-op twice over: the insert is
   refused, and even if it were not, summing the same set again gives the same
   answer. An incremental ``filled_qty += last_qty`` would double a member's
   position on a replay, which is the bug this sprint is here to prevent.

2. **The ``/events`` cursor is durable.** ``seq`` comes from a database
   sequence, not from ``len(events)``. A restarted gateway keeps counting, so a
   client reconnecting with ``?since=`` is never handed frames it has already
   seen, and never silently skipped past.

3. **Decimals stay exact.** Money is stored as the contract's own digit string
   and summed in :class:`~decimal.Decimal`. Nothing here touches a float.

The same code runs on PostgreSQL (the deploy) and SQLite (CI, which has no
Postgres service): everything is portable SQLAlchemy Core, and
``tests/gateway/test_sql_projection.py`` runs the restart proof on both, the
second only when ``ALGOBOTS_GATEWAY_TEST_PG_URL`` points at one.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from algobots.gateway.projection import (
    ZERO,
    FillRow,
    OrderRow,
    PositionRow,
    dec_str,
    iso,
)

METADATA = sa.MetaData()

#: Mirrors migration 0011. ``tests/gateway/test_sql_projection.py`` asserts the
#: two agree, because a column that exists here and not there is a failure that
#: only ever happens on the deploy.
SEQ = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

EVENTS = sa.Table(
    "gateway_events",
    METADATA,
    sa.Column("seq", SEQ, primary_key=True, autoincrement=True),
    sa.Column("type", sa.String(length=16), nullable=False),
    sa.Column("account_id", sa.String(length=64), nullable=False),
    sa.Column("ts_event", sa.String(length=32), nullable=False),
    sa.Column("payload", sa.Text(), nullable=False, server_default="{}"),
    sa.Index("ix_gateway_events_account_seq", "account_id", "seq"),
)

ORDERS = sa.Table(
    "gateway_orders",
    METADATA,
    sa.Column("client_order_id", sa.String(length=64), primary_key=True),
    sa.Column("account_id", sa.String(length=64), nullable=False),
    sa.Column("symbol", sa.String(length=64), nullable=False),
    sa.Column("side", sa.String(length=8), nullable=False),
    sa.Column("qty", sa.Text(), nullable=False),
    sa.Column("order_type", sa.String(length=16), nullable=False),
    sa.Column("status", sa.String(length=24), nullable=False),
    sa.Column("mode", sa.String(length=16), nullable=False, server_default="PAPER"),
    sa.Column("venue_order_id", sa.String(length=64), nullable=True),
    sa.Column("filled_qty", sa.Text(), nullable=False),
    sa.Column("avg_px", sa.Text(), nullable=True),
    sa.Column("limit_px", sa.Text(), nullable=True),
    sa.Column("time_in_force", sa.String(length=8), nullable=True),
    sa.Column("reason", sa.String(length=512), nullable=True),
    sa.Column("submitted_at", sa.String(length=32), nullable=False),
    sa.Column("updated_at", sa.String(length=32), nullable=False),
    sa.Column("fingerprint", sa.String(length=64), nullable=False, server_default=""),
    sa.Column("node", sa.String(length=64), nullable=False, server_default=""),
    sa.Column("ordinal", SEQ, nullable=False, server_default="0"),
    sa.Index("ix_gateway_orders_account_ordinal", "account_id", "ordinal"),
    sa.Index("ix_gateway_orders_status", "account_id", "status"),
)

FILLS = sa.Table(
    "gateway_fills",
    METADATA,
    sa.Column("id", SEQ, primary_key=True, autoincrement=True),
    sa.Column(
        "client_order_id",
        sa.String(length=64),
        sa.ForeignKey("gateway_orders.client_order_id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("trade_id", sa.String(length=64), nullable=False),
    sa.Column("qty", sa.Text(), nullable=False),
    sa.Column("px", sa.Text(), nullable=False),
    sa.Column("ts_event", sa.String(length=32), nullable=False),
    sa.Column("commission", sa.Text(), nullable=True),
    sa.Column("commission_currency", sa.String(length=16), nullable=True),
    sa.UniqueConstraint("client_order_id", "trade_id", name="uq_gateway_fills_trade"),
    sa.Index("ix_gateway_fills_order", "client_order_id", "id"),
)

POSITIONS = sa.Table(
    "gateway_positions",
    METADATA,
    sa.Column("position_id", sa.String(length=64), primary_key=True),
    sa.Column("account_id", sa.String(length=64), nullable=False),
    sa.Column("symbol", sa.String(length=64), nullable=False),
    sa.Column("side", sa.String(length=8), nullable=False),
    sa.Column("qty", sa.Text(), nullable=False),
    sa.Column("avg_px", sa.Text(), nullable=False),
    sa.Column("opened_at", sa.String(length=32), nullable=False),
    sa.Column("unrealized_pnl", sa.Text(), nullable=True),
    sa.Column("realized_pnl", sa.Text(), nullable=True),
    sa.Index("ix_gateway_positions_account", "account_id"),
)

BALANCES = sa.Table(
    "gateway_balances",
    METADATA,
    sa.Column("account_id", sa.String(length=64), primary_key=True),
    sa.Column("currency", sa.String(length=16), primary_key=True),
    sa.Column("total", sa.Text(), nullable=False),
    sa.Column("free", sa.Text(), nullable=False),
    sa.Column("locked", sa.Text(), nullable=True),
    sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
)

#: The contract Event keys that have their own column; everything else on an
#: event (``order``, ``fill``, ``position``, ``account``) goes to ``payload``.
EVENT_COLUMNS = ("type", "account_id", "ts_event")


def _dec(raw: Any) -> Decimal | None:
    return None if raw is None or raw == "" else Decimal(str(raw))


def _text(value: Decimal | None) -> str | None:
    return None if value is None else dec_str(value)


class SqlProjection:
    """:class:`~algobots.gateway.projection.Projection`, backed by a database.

    ``engine`` is expected to point at the Phase 0 ``compose.yaml`` Postgres in
    the deploy. Nothing in here is PostgreSQL-specific, so the same class is
    what CI tests against SQLite — the point being that the restart proof
    exercises this code and not a stand-in for it.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._started = iso(datetime.now(UTC))

    # --- reads ---------------------------------------------------------------

    def order(self, client_order_id: str) -> OrderRow | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                sa.select(ORDERS).where(ORDERS.c.client_order_id == client_order_id)
            ).mappings().first()
            return None if row is None else self._order_row(conn, row)

    def orders(
        self, *, accounts: tuple[str, ...], status: str | None = None, limit: int = 100
    ) -> list[OrderRow]:
        """Newest first, scoped to the caller's accounts.

        The scope is a SQL predicate rather than a filter applied to a full
        read: an order belonging to another member must never be loaded into
        the process that is answering this request.
        """
        if not accounts:
            return []
        query = sa.select(ORDERS).where(ORDERS.c.account_id.in_(accounts))
        if status is not None:
            query = query.where(ORDERS.c.status == status)
        query = query.order_by(ORDERS.c.ordinal.desc()).limit(limit)
        with self._engine.connect() as conn:
            rows = conn.execute(query).mappings().all()
            return [self._order_row(conn, row) for row in rows]

    def positions(self, *, accounts: tuple[str, ...]) -> list[PositionRow]:
        if not accounts:
            return []
        query = (
            sa.select(POSITIONS)
            .where(POSITIONS.c.account_id.in_(accounts))
            .order_by(POSITIONS.c.position_id)
        )
        with self._engine.connect() as conn:
            return [_position_row(row) for row in conn.execute(query).mappings()]

    def position(self, position_id: str) -> PositionRow | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                sa.select(POSITIONS).where(POSITIONS.c.position_id == position_id)
            ).mappings().first()
            return None if row is None else _position_row(row)

    def balances(self, account_id: str) -> list[dict[str, Any]]:
        query = (
            sa.select(BALANCES)
            .where(BALANCES.c.account_id == account_id)
            .order_by(BALANCES.c.ordinal)
        )
        with self._engine.connect() as conn:
            out = []
            for row in conn.execute(query).mappings():
                balance = {
                    "currency": row["currency"],
                    "total": row["total"],
                    "free": row["free"],
                }
                if row["locked"] is not None:
                    balance["locked"] = row["locked"]
                out.append(balance)
            return out

    def events_since(self, seq: int, *, accounts: tuple[str, ...]) -> list[dict[str, Any]]:
        if not accounts:
            return []
        query = (
            sa.select(EVENTS)
            .where(EVENTS.c.seq > seq, EVENTS.c.account_id.in_(accounts))
            .order_by(EVENTS.c.seq)
        )
        with self._engine.connect() as conn:
            return [_event(row) for row in conn.execute(query).mappings()]

    @property
    def as_of(self) -> str:
        """The newest ``ts_event`` the nodes have reported.

        A plain ``max()`` over the stored text is a max over instants because
        every value is written by ``projection.iso``: UTC, fixed-width
        milliseconds, trailing ``Z``, so lexical and chronological order agree.
        """
        with self._engine.connect() as conn:
            newest = conn.execute(sa.select(sa.func.max(EVENTS.c.ts_event))).scalar()
        return max(newest, self._started) if newest else self._started

    @property
    def head(self) -> int:
        """The newest assigned ``seq``; a client resuming here loses nothing."""
        with self._engine.connect() as conn:
            return int(conn.execute(sa.select(sa.func.max(EVENTS.c.seq))).scalar() or 0)

    def health(self) -> dict[str, Any]:
        """``/health``'s ``projection`` block.

        Unreachable is reported, not raised: the probe's job is to say that the
        gateway cannot serve reads, and a ``/health`` that 500s when Postgres is
        down tells an operator less than one that answers ``degraded``.
        """
        try:
            return {"reachable": True, "head": self.head}
        except sa.exc.SQLAlchemyError:
            return {"reachable": False, "head": 0}

    # --- folds (admission and node_events are the only callers) --------------

    def put_order(self, order: OrderRow) -> OrderRow:
        """Insert or replace one order row. Admission's write.

        New orders get the next ``ordinal`` so ``/orders`` can return newest
        first without trusting a timestamp two orders may share.
        """
        values = _order_values(order)
        with self._engine.begin() as conn:
            exists = conn.execute(
                sa.select(ORDERS.c.ordinal).where(
                    ORDERS.c.client_order_id == order.client_order_id
                )
            ).scalar()
            if exists is None:
                nxt = conn.execute(sa.select(sa.func.max(ORDERS.c.ordinal))).scalar() or 0
                conn.execute(ORDERS.insert().values(**values, ordinal=int(nxt) + 1))
            else:
                conn.execute(
                    ORDERS.update()
                    .where(ORDERS.c.client_order_id == order.client_order_id)
                    .values(**values)
                )
            # Fills are rows in their own table, so the order row never carries
            # them; read them back so the caller sees the stored truth.
            return replace(order, fills=_fills(conn, order.client_order_id))

    def amend_order(self, client_order_id: str, **changes: Any) -> OrderRow | None:
        """Apply a node-reported change. Unknown orders are ignored, not created.

        Same rule as the in-memory fold: an order the gateway never admitted
        has no admission record, and inventing one here would make a refused
        intent indistinguishable from an admitted one.
        """
        current = self.order(client_order_id)
        if current is None:
            return None
        # At-least-once delivery includes replaying pre-fill lifecycle events;
        # never let an older accepted/submitted event regress durable state.
        updated_at = changes.get("updated_at")
        if updated_at is not None and updated_at < current.updated_at:
            return current
        # `fills` is not a column; a caller that wants to add one calls add_fill.
        changes.pop("fills", None)
        updated = replace(current, **changes)
        with self._engine.begin() as conn:
            conn.execute(
                ORDERS.update()
                .where(ORDERS.c.client_order_id == client_order_id)
                .values(**_order_values(updated))
            )
        return updated

    def add_fill(
        self,
        client_order_id: str,
        fill: FillRow,
        *,
        updated_at: str,
        venue_order_id: str | None = None,
        reason: str | None = None,
    ) -> OrderRow | None:
        """Record one execution and re-derive the order from all of them.

        ``None`` means nothing changed, for either of the two reasons the
        caller treats identically — the order was never admitted here, or this
        ``(client_order_id, trade_id)`` has already been folded. The second is
        the at-least-once case: ``docs/bridge.md`` warns a node restart can
        replay a fill, and a replay must not move a member's filled quantity.
        """
        with self._engine.begin() as conn:
            row = conn.execute(
                sa.select(ORDERS).where(ORDERS.c.client_order_id == client_order_id)
            ).mappings().first()
            if row is None:
                return None
            try:
                # A savepoint, so the duplicate's IntegrityError rolls back
                # only the insert and leaves this transaction usable.
                with conn.begin_nested():
                    conn.execute(
                        FILLS.insert().values(
                            client_order_id=client_order_id,
                            trade_id=fill.trade_id,
                            qty=dec_str(fill.qty),
                            px=dec_str(fill.px),
                            ts_event=fill.ts_event,
                            commission=_text(fill.commission),
                            commission_currency=fill.commission_currency,
                        )
                    )
            except IntegrityError:
                return None  # uq_gateway_fills_trade: already folded

            fills = _fills(conn, client_order_id)
            qty = _dec(row["qty"]) or ZERO
            filled = sum((f.qty for f in fills), ZERO)
            notional = sum((f.qty * f.px for f in fills), ZERO)
            values: dict[str, Any] = {
                "filled_qty": dec_str(filled),
                "avg_px": _text(notional / filled) if filled else None,
                # The node fills in slices; only the last one is terminal.
                "status": "filled" if filled >= qty else "partially_filled",
                "updated_at": updated_at,
            }
            if venue_order_id:
                values["venue_order_id"] = venue_order_id
            if reason:
                values["reason"] = reason
            conn.execute(
                ORDERS.update()
                .where(ORDERS.c.client_order_id == client_order_id)
                .values(**values)
            )
            return _order_from(dict(row) | values, fills)

    def put_position(self, position: PositionRow) -> PositionRow:
        position_id = position.position_id or position.symbol
        values = {
            "account_id": position.account_id,
            "symbol": position.symbol,
            "side": position.side,
            "qty": dec_str(position.qty),
            "avg_px": dec_str(position.avg_px),
            "opened_at": position.opened_at,
            "unrealized_pnl": _text(position.unrealized_pnl),
            "realized_pnl": _text(position.realized_pnl),
        }
        with self._engine.begin() as conn:
            exists = conn.execute(
                sa.select(POSITIONS.c.position_id).where(POSITIONS.c.position_id == position_id)
            ).scalar()
            if exists is None:
                conn.execute(POSITIONS.insert().values(position_id=position_id, **values))
            else:
                conn.execute(
                    POSITIONS.update()
                    .where(POSITIONS.c.position_id == position_id)
                    .values(**values)
                )
        return position

    def drop_position(self, position_id: str) -> None:
        """A closed position leaves ``/positions``, which lists open ones."""
        with self._engine.begin() as conn:
            conn.execute(POSITIONS.delete().where(POSITIONS.c.position_id == position_id))

    def put_balances(self, account_id: str, balances: list[dict[str, Any]]) -> None:
        """Replace this account's balances with the node's latest `AccountState`.

        A replace and not a merge: the node reports the whole account, so a
        currency missing from the new state is a currency the account no longer
        holds. Merging would leave a stale balance on screen forever.
        """
        with self._engine.begin() as conn:
            conn.execute(BALANCES.delete().where(BALANCES.c.account_id == account_id))
            if balances:
                conn.execute(
                    BALANCES.insert(),
                    [
                        {
                            "account_id": account_id,
                            "currency": b["currency"],
                            "total": b["total"],
                            "free": b["free"],
                            "locked": b.get("locked"),
                            "ordinal": i,
                        }
                        for i, b in enumerate(balances)
                    ],
                )

    def append_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Assign the next ``seq`` from the database and store the frame.

        The sequence is the contract's resume cursor, so it has to be allocated
        by something that outlives the process: a restarted gateway continues
        the count instead of re-issuing numbers a client has already seen.
        """
        payload = {k: v for k, v in event.items() if k not in EVENT_COLUMNS and k != "seq"}
        with self._engine.begin() as conn:
            result = conn.execute(
                EVENTS.insert().values(
                    type=event["type"],
                    account_id=event["account_id"],
                    ts_event=event["ts_event"],
                    payload=json.dumps(payload, default=str),
                )
            )
            seq = int(result.inserted_primary_key[0])
        return {"seq": seq, **event}

    # --- helpers -------------------------------------------------------------

    def _order_row(self, conn: sa.Connection, row: sa.RowMapping) -> OrderRow:
        return _order_from(dict(row), _fills(conn, row["client_order_id"]))


def _fills(conn: sa.Connection, client_order_id: str) -> tuple[FillRow, ...]:
    """This order's executions, oldest first (the order the node sent them)."""
    rows = conn.execute(
        sa.select(FILLS)
        .where(FILLS.c.client_order_id == client_order_id)
        .order_by(FILLS.c.id)
    ).mappings()
    return tuple(
        FillRow(
            trade_id=row["trade_id"],
            qty=_dec(row["qty"]) or ZERO,
            px=_dec(row["px"]) or ZERO,
            ts_event=row["ts_event"],
            commission=_dec(row["commission"]),
            commission_currency=row["commission_currency"],
        )
        for row in rows
    )


def _order_from(row: dict[str, Any], fills: tuple[FillRow, ...]) -> OrderRow:
    return OrderRow(
        client_order_id=row["client_order_id"],
        account_id=row["account_id"],
        symbol=row["symbol"],
        side=row["side"],
        qty=_dec(row["qty"]) or ZERO,
        order_type=row["order_type"],
        status=row["status"],
        submitted_at=row["submitted_at"],
        updated_at=row["updated_at"],
        mode=row["mode"],
        venue_order_id=row["venue_order_id"],
        filled_qty=_dec(row["filled_qty"]) or ZERO,
        avg_px=_dec(row["avg_px"]),
        limit_px=_dec(row["limit_px"]),
        time_in_force=row["time_in_force"],
        reason=row["reason"],
        fills=fills,
        fingerprint=row["fingerprint"],
        node=row["node"],
    )


def _order_values(order: OrderRow) -> dict[str, Any]:
    """Every column except ``ordinal``, which only ``put_order`` assigns."""
    return {
        "client_order_id": order.client_order_id,
        "account_id": order.account_id,
        "symbol": order.symbol,
        "side": order.side,
        "qty": dec_str(order.qty),
        "order_type": order.order_type,
        "status": order.status,
        "mode": order.mode,
        "venue_order_id": order.venue_order_id,
        "filled_qty": dec_str(order.filled_qty),
        "avg_px": _text(order.avg_px),
        "limit_px": _text(order.limit_px),
        "time_in_force": order.time_in_force,
        "reason": order.reason,
        "submitted_at": order.submitted_at,
        "updated_at": order.updated_at,
        "fingerprint": order.fingerprint,
        "node": order.node,
    }


def _position_row(row: sa.RowMapping) -> PositionRow:
    return PositionRow(
        account_id=row["account_id"],
        symbol=row["symbol"],
        side=row["side"],
        qty=_dec(row["qty"]) or ZERO,
        avg_px=_dec(row["avg_px"]) or ZERO,
        opened_at=row["opened_at"],
        position_id=row["position_id"],
        unrealized_pnl=_dec(row["unrealized_pnl"]),
        realized_pnl=_dec(row["realized_pnl"]),
    )


def _event(row: sa.RowMapping) -> dict[str, Any]:
    """Re-assemble a stored frame into the contract's ``Event``."""
    payload = json.loads(row["payload"] or "{}")
    return {
        "seq": int(row["seq"]),
        "type": row["type"],
        "account_id": row["account_id"],
        "ts_event": row["ts_event"],
        **payload,
    }


#: Where the gateway's projection lives, most specific first.
#:
#: The gateway's own variable wins so the Phase 0 stack can point it at a
#: different database from the control plane's without either having to move.
#: Roadmap rule 3: the URL carries a password, so it comes from the
#: environment or the encrypted store — never the repo, and it is never logged
#: (``engine_from_env`` raises the variable *name*, not its value).
DATABASE_URL_VARS = ("ALGOBOTS_GATEWAY_DATABASE_URL", "DATABASE_URL")


def engine_from_env(env: dict[str, str] | None = None) -> Engine:
    """Build the projection engine from the environment.

    ``pool_pre_ping`` because the gateway outlives any single Postgres
    connection: the compose database can restart under it, and the next
    ``/positions`` has to reconnect rather than answer with a dead socket.
    """
    source = os.environ if env is None else env
    for name in DATABASE_URL_VARS:
        url = source.get(name)
        if url:
            return sa.create_engine(url, pool_pre_ping=True, future=True)
    raise RuntimeError(
        "the gateway projection needs a database: set "
        f"{' or '.join(DATABASE_URL_VARS)} (see deploy/docker-compose.yml)"
    )


def projection_from_env(env: dict[str, str] | None = None) -> SqlProjection:
    """The deploy's projection. Assumes ``alembic upgrade head`` has run."""
    return SqlProjection(engine_from_env(env))


__all__ = [
    "BALANCES",
    "DATABASE_URL_VARS",
    "EVENTS",
    "FILLS",
    "METADATA",
    "ORDERS",
    "POSITIONS",
    "SqlProjection",
    "engine_from_env",
    "projection_from_env",
]
