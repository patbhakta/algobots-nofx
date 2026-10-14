"""P1.2: the projection is in Postgres, and a restart does not lose it.

The sprint's "Done when" is `test_restarting_the_gateway_rebuilds_the_same_positions`:
a second gateway, built over the same database with no shared memory, answers
`/positions` and `/orders` with what the first one folded.

Every test runs against SQLite by default so the proof is green in CI, which
has no Postgres service. Point `ALGOBOTS_GATEWAY_TEST_PG_URL` at a database and
the identical bodies run against the real thing as well:

    ALGOBOTS_GATEWAY_TEST_PG_URL=postgresql+psycopg://user:pw@host:5432/db \
      pytest tests/gateway/test_sql_projection.py

CI runs this module through the repository's ordinary ``pytest`` job. The
optional environment variable promotes the same proof from SQLite to the
Phase 0 Postgres when the deployment verification environment provides it.
"""

from __future__ import annotations

import json
import os
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
import yaml
from alembic import command
from alembic.config import Config
from jsonschema import Draft202012Validator, RefResolver

from algobots.gateway.admission import AllowAll
from algobots.gateway.app import build_gateway, get_health, list_orders, list_positions
from algobots.gateway.auth import Caller, StaticSessions
from algobots.gateway.fixture_node import fixture_stack
from algobots.gateway.projection import FillRow, InMemoryProjection
from algobots.gateway.store import METADATA, SqlProjection, engine_from_env

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = yaml.safe_load((REPO_ROOT / "contracts" / "gateway.openapi.yaml").read_text())
AUTH = {"Authorization": "Bearer fixture-session"}

PG_URL = os.environ.get("ALGOBOTS_GATEWAY_TEST_PG_URL", "")

#: The five tables migration 0011 adds. Named here so a table added to the
#: migration without being added to `store.METADATA` is a failure.
GATEWAY_TABLES = (
    "gateway_events",
    "gateway_orders",
    "gateway_fills",
    "gateway_positions",
    "gateway_balances",
)


def assert_schema(name: str, body: object) -> None:
    schema = SPEC["components"]["schemas"][name]
    validator = Draft202012Validator(schema, resolver=RefResolver.from_schema(SPEC))
    errors = sorted(validator.iter_errors(body), key=lambda error: list(error.path))
    assert not errors, "\n".join(error.message for error in errors)


def request(app):  # noqa: ANN001, ANN201
    return SimpleNamespace(app=app, headers={"authorization": AUTH["Authorization"]})


def positions_body(app):  # noqa: ANN001, ANN201
    """Call the route directly without FastAPI's ``Query`` default wrapper."""
    return list_positions(request(app), account=None)


def orders_body(app):  # noqa: ANN001, ANN201
    """Call the route directly without FastAPI's ``Query`` default wrappers."""
    return list_orders(request(app), account=None, status=None, limit=100)


# --- the two databases under test -------------------------------------------


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgresql",
            marks=pytest.mark.skipif(
                not PG_URL, reason="set ALGOBOTS_GATEWAY_TEST_PG_URL to run against Postgres"
            ),
        ),
    ]
)
def engine(request, tmp_path):  # noqa: ANN001, ANN201
    """A migrated, empty projection database.

    The PostgreSQL run gets its own schema per test and drops it afterwards, so
    the suite can point at the deploy's database without touching the deploy's
    rows.
    """
    if request.param == "sqlite":
        engine = sa.create_engine(f"sqlite:///{tmp_path / 'projection.db'}")
        METADATA.create_all(engine)
        yield engine
        engine.dispose()
        return

    schema = f"gw_test_{uuid.uuid4().hex[:12]}"
    admin = sa.create_engine(PG_URL)
    with admin.begin() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    engine = sa.create_engine(
        PG_URL, connect_args={"options": f"-csearch_path={schema}"}, pool_pre_ping=True
    )
    METADATA.create_all(engine)
    yield engine
    engine.dispose()
    with admin.begin() as conn:
        conn.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


def gateway_over(engine, *, projection=None):  # noqa: ANN001, ANN201
    """A fresh gateway and fixture node over ``engine``.

    Calling this twice with the same engine is the restart: the second gateway
    shares no object with the first, only the database.
    """
    store = SqlProjection(engine) if projection is None else projection
    registry, store, bus, node = fixture_stack(projection=store)
    app = build_gateway(
        registry=registry,
        projection=store,
        bus=bus,
        gate=AllowAll(),
        sessions=StaticSessions({"fixture-session": Caller("member-1", ("laya",))}),
    )
    return app, node, bus, store


def submit_and_fill(app, node, client_order_id: str, qty: str = "1000") -> None:
    """Admit one market order and let the fixture node fill it."""
    from algobots.gateway.app import submit_order

    submit_order(
        request(app),
        {"account_id": "laya", "symbol": "EUR/USD", "side": "buy", "qty": qty,
         "order_type": "market"},
        client_order_id,
    )
    node.drain()


# --- the migration is the deploy path, so it has to match the code ----------


def test_metadata_matches_the_migration(tmp_path) -> None:
    """`store.METADATA` and migration 0011 must describe the same tables.

    The code reads and writes through `METADATA`; the deploy creates the schema
    with Alembic. A column in one and not the other is a failure that cannot
    happen in a test using `create_all`, only on `.243`.
    """
    migrated = tmp_path / "migrated.db"
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{migrated}")
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")

    declared = sa.create_engine(f"sqlite:///{tmp_path / 'declared.db'}")
    METADATA.create_all(declared)

    from_migration = sa.inspect(sa.create_engine(f"sqlite:///{migrated}"))
    from_code = sa.inspect(declared)

    for table in GATEWAY_TABLES:
        assert from_migration.has_table(table), f"migration 0011 never created {table}"
        migration_cols = {c["name"]: c for c in from_migration.get_columns(table)}
        code_cols = {c["name"]: c for c in from_code.get_columns(table)}
        assert migration_cols.keys() == code_cols.keys(), (
            f"{table}: migration and store.METADATA disagree on columns"
        )
        for name, col in code_cols.items():
            assert str(col["type"]) == str(migration_cols[name]["type"]), (
                f"{table}.{name}: {col['type']} in code, "
                f"{migration_cols[name]['type']} in migration 0011"
            )

    # The dedupe key the sprint turns on, asserted against the real migration
    # rather than the declaration the code happens to use.
    uniques = from_migration.get_unique_constraints("gateway_fills")
    assert any(
        set(u["column_names"]) == {"client_order_id", "trade_id"} for u in uniques
    ), "gateway_fills must be UNIQUE (client_order_id, trade_id) — the replay guard"


# --- the "Done when" --------------------------------------------------------


def test_restarting_the_gateway_rebuilds_the_same_positions(engine) -> None:
    """ALG-3370's "Done when": restart, and the positions are still there.

    The second gateway is built from scratch over the same database. It shares
    no registry, no projection object and no process state with the first, so
    the only way it can answer `/positions` is from Postgres.
    """
    first, node, _, _ = gateway_over(engine)
    node.heartbeat()
    node.account_state("1000.00", free="997.80", locked="2.20")
    submit_and_fill(first, node, "order-restart-0001")

    before = positions_body(first)
    assert before["positions"], "the fixture fill should have opened a position"
    orders_before = orders_body(first)

    # The restart: everything the first gateway held in memory is gone.
    del first, node

    second, node2, _, _ = gateway_over(engine)
    node2.heartbeat()
    after = positions_body(second)

    assert after["positions"] == before["positions"]
    assert orders_body(second)["orders"] == orders_before["orders"]
    assert_schema("Position", after["positions"][0])

    # And the balances the node reported, which also only exist in the database.
    from algobots.gateway.app import get_account

    assert get_account(request(second), "laya")["balances"] == [
        {"currency": "USD", "total": "1000", "free": "997.80", "locked": "2.20"}
    ]


def test_restart_keeps_the_event_cursor_monotonic(engine) -> None:
    """`seq` comes from the database, so a restart continues the count.

    If it restarted at 0, a client reconnecting with `?since=` would be handed
    frames it had already processed under numbers it had already seen — and
    `Event.seq` is the only thing the contract gives it to dedupe with.
    """
    first, node, _, store = gateway_over(engine)
    node.heartbeat()
    submit_and_fill(first, node, "order-cursor-00001")
    head = store.head
    assert head > 0

    second, node2, _, store2 = gateway_over(engine)
    assert store2.head == head, "a restarted gateway must not re-issue seqs"

    node2.heartbeat()
    assert store2.head > head, "and it must keep counting from there"

    # Everything after the first gateway's head is exactly the new frames.
    resumed = store2.events_since(head, accounts=("laya",))
    assert [e["seq"] for e in resumed] == list(range(head + 1, store2.head + 1))
    for event in resumed:
        assert_schema("Event", event)


# --- at-least-once delivery -------------------------------------------------


def test_a_replayed_fill_is_folded_exactly_once(engine) -> None:
    """docs/bridge.md: a node restart can replay a fill. Fold it twice anyway.

    The quantity, the average price and the fill list all have to be unchanged,
    and no second `/events` frame may be produced — a duplicate frame would
    carry a genuinely new `seq`, so the consumer's documented dedupe on
    `(client_order_id, seq)` could not catch it.
    """
    app, node, _, store = gateway_over(engine)
    node.heartbeat()
    submit_and_fill(app, node, "order-replay-00001")

    once = store.order("order-replay-00001")
    assert once is not None
    assert once.filled_qty == Decimal("1000")
    assert len(once.fills) == 1
    head = store.head

    replayed = store.add_fill(
        "order-replay-00001",
        FillRow(
            trade_id=once.fills[0].trade_id,
            qty=once.fills[0].qty,
            px=once.fills[0].px,
            ts_event=once.fills[0].ts_event,
        ),
        updated_at=once.updated_at,
    )
    assert replayed is None, "the same (client_order_id, trade_id) must be refused"

    twice = store.order("order-replay-00001")
    assert twice == once, "a replayed fill changed the order"
    assert store.head == head, "a replayed fill must not append an event"


def test_the_whole_node_stream_is_idempotent_on_replay(engine) -> None:
    """Re-deliver every event the node ever sent; the state must not move.

    Stronger than the single-fill case: this is what a node restarting and
    re-emitting its stream from the beginning actually looks like.
    """
    from algobots.gateway import node_events as NE

    app, node, _, store = gateway_over(engine)
    node.heartbeat()
    node.account_state("1000.00", free="997.80")
    emitted: list[dict] = []
    original_emit = node._emit

    def record(payload):  # noqa: ANN001, ANN202
        emitted.append(payload)
        return original_emit(payload)

    node._emit = record  # type: ignore[method-assign]
    submit_and_fill(app, node, "order-idem-000001")
    assert emitted, "the fixture node should have emitted something to replay"

    positions = positions_body(app)
    order = store.order("order-idem-000001")

    for payload in emitted:
        NE.ingest(payload, registry=node.registry, projection=store)

    assert store.order("order-idem-000001") == order
    assert positions_body(app)["positions"] == positions["positions"]


# --- the stores agree, and both serve the contract --------------------------


def test_sql_and_memory_projections_fold_identically(engine) -> None:
    """The same node payloads through both stores give the same contract bodies.

    P1.1's conformance suite runs on the in-memory projection. That only proves
    anything about the deploy if the durable store folds the same way, so the
    two are driven side by side here.
    """
    sql_app, sql_node, _, _ = gateway_over(engine)
    mem_app, mem_node, _, _ = gateway_over(engine, projection=InMemoryProjection())
    # Both stores consume byte-for-byte equivalent node events. Their default
    # clocks are created a few microseconds apart, which is not a store
    # difference and would otherwise make the contract timestamps differ.
    mem_node.clock = sql_node.clock

    for app, node in ((sql_app, sql_node), (mem_app, mem_node)):
        node.heartbeat()
        node.account_state("1000.00", free="997.80", locked="2.20")
        submit_and_fill(app, node, "order-parity-00001")

    sql_orders = orders_body(sql_app)["orders"]
    mem_orders = orders_body(mem_app)["orders"]
    # Admission timestamps come from the gateway wall clock, not the node
    # stream. Compare every projected field while excluding that independent
    # request-time input.
    assert [{k: v for k, v in row.items() if k != "submitted_at"} for row in sql_orders] == [
        {k: v for k, v in row.items() if k != "submitted_at"} for row in mem_orders
    ]
    assert (
        positions_body(sql_app)["positions"] == positions_body(mem_app)["positions"]
    )


def test_decimals_survive_the_database_exactly(engine) -> None:
    """Money is stored as digits, not as a float.

    `0.1 + 0.2` through a float column is the classic wrong balance; the fill
    price here has five decimal places and a commission with two, and both have
    to come back as written.
    """
    app, node, _, store = gateway_over(engine)
    node.heartbeat()
    node.fill_px = Decimal("1.10005")
    node.commission = Decimal("2.20")
    submit_and_fill(app, node, "order-decimal-0001", qty="3")

    order = store.order("order-decimal-0001")
    assert order is not None
    fill = order.fills[0]
    assert fill.px == Decimal("1.10005")
    assert fill.commission == Decimal("2.20")
    # avg_px of a single fill is that fill's price, to the digit.
    assert order.avg_px == Decimal("1.10005")

    body = order.contract()
    assert body["avg_px"] == "1.10005"
    assert body["fills"][0]["commission"] == "2.20"
    assert_schema("Order", body)


def test_reads_are_scoped_to_the_callers_accounts(engine) -> None:
    """Another member's rows are excluded in SQL, not filtered after loading."""
    app, node, _, store = gateway_over(engine)
    node.heartbeat()
    submit_and_fill(app, node, "order-scope-000001")

    assert store.orders(accounts=("someone-else",)) == []
    assert store.positions(accounts=("someone-else",)) == []
    assert store.events_since(0, accounts=("someone-else",)) == []
    # The empty scope is not "no filter": it is no accounts.
    assert store.orders(accounts=()) == []
    assert store.positions(accounts=()) == []


# --- /health tells an operator the projection is the problem ----------------


def test_health_reports_the_projection_head(engine) -> None:
    app, node, _, store = gateway_over(engine)
    node.heartbeat()
    submit_and_fill(app, node, "order-health-00001")

    health = get_health(request(app))
    assert_schema("Health", health)
    assert health["projection"] == {"reachable": True, "head": store.head}
    assert health["status"] == "ok"


def test_health_is_degraded_when_the_projection_is_unreachable(engine) -> None:
    """Healthy nodes over a dead database is still a gateway that cannot read.

    The probe must answer, not raise: an operator needs to be told which half
    of the stack is down, and a 500 says only "something".
    """
    app, node, _, _ = gateway_over(engine)
    node.heartbeat()
    assert get_health(request(app))["status"] == "ok"

    # Point the projection at a database that is not there.
    broken = SqlProjection(sa.create_engine("postgresql+psycopg://127.0.0.1:1/none"))
    app.state.gateway.projection = broken

    health = get_health(request(app))
    assert_schema("Health", health)
    assert health["projection"] == {"reachable": False, "head": 0}
    assert health["status"] == "degraded", "node fitness alone must not read as ok"


# --- the deploy's wiring ----------------------------------------------------


def test_engine_from_env_prefers_the_gateways_own_url() -> None:
    engine = engine_from_env({"ALGOBOTS_GATEWAY_DATABASE_URL": "sqlite://", "DATABASE_URL": "x"})
    assert engine.url.get_backend_name() == "sqlite"


def test_engine_from_env_names_the_variable_and_never_the_url() -> None:
    """Roadmap rule 3: the URL carries a password, so it stays out of logs."""
    with pytest.raises(RuntimeError) as err:
        engine_from_env({})
    assert "ALGOBOTS_GATEWAY_DATABASE_URL" in str(err.value)


def test_stored_events_round_trip_as_contract_frames(engine) -> None:
    """A resumed stream replays the frame that was sent, not a re-render.

    The event payload is stored as sent so that a client catching up with
    `?since=` sees the order as it was at that `seq`, which is what makes the
    cursor meaningful rather than just a counter.
    """
    app, node, _, store = gateway_over(engine)
    node.heartbeat()
    submit_and_fill(app, node, "order-frames-00001")

    frames = store.events_since(0, accounts=("laya",))
    assert [f["type"] for f in frames][0] == "heartbeat"
    assert "fill" in {f["type"] for f in frames}
    for frame in frames:
        assert_schema("Event", frame)
        # `additionalProperties: false` on Event: a stored key the contract does
        # not declare would fail the schema above, which is the point.
        assert json.dumps(frame)  # JSON-serialisable as delivered
