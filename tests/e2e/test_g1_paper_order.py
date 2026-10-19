"""GATE G1 (ALG-3373): a market order placed in NoFX fills within two seconds.

This is the Phase 1 gate. It is not a demo — it runs in CI on every merge
against the Phase 0 sandbox stack, and the roadmap hangs Phase 2 and the P6.2
signal service off its passing.

What the budget is measured over is the whole path, not a slice of it:

    POST /v1/orders            the request `clients/gateway/client.gen.go`
                               makes, which NoFX's `nautilus` exchange calls
      -> admission             account scope, shape, PAPER-only, node fitness
      -> algobots:cmd:<node>   Redis stream, XADD           [real Redis]
      -> CommandStream         consumer group, at-least-once
      -> CommandActor          idempotency key = client order id
      -> the venue             sandbox; emits the P0.3 event shapes
      -> trader-*:algobots:events.*   Redis streams, XADD   [real Redis]
      -> NodeEventIngest       XREAD, decode, fold
      -> node_events.ingest    the only wire-shape module
      -> SqlProjection         orders, fills, positions      [real Postgres]
      -> GET /v1/orders/{id}   what NoFX reads back
      -> ws /v1/events         and what it is pushed

The clock starts when ``POST /orders`` returns and stops when ``GET
/orders/{id}`` first says ``filled``. Starting it before the POST would be
measuring the gateway's own admission twice over; what the gate promises is
that the member sees the fill, and the member sees it on the read.

The one file on that path this does not execute is
``algobots.node.nautilus_actor`` — ``SubmitOrder`` into an engine order —
because CI installs ``dev`` and ``nautilus_trader`` is in ``workers``. It is
covered by ``tests/node`` against the engine's API and by
``scripts/phase0_redis_egress.py`` against a real node, and the event shapes
this gate carries are that node's own (``artifacts/ALG-3350/``).
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, RefResolver

from algobots.node.sandbox import FILLED
from tests.e2e.stack import FILL_PX, SYMBOL, TOKEN, g1_stack

#: The gate. Two seconds, end to end, as ALG-3373 states it.
BUDGET_S = 2.0

#: How long to wait before declaring the fill lost rather than slow. Larger
#: than the budget on purpose: "it arrived in 3.4s" is a useful failure and
#: "it never arrived" is a different bug, so the test distinguishes them.
PATIENCE_S = 20.0

QTY = "100000"

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = yaml.safe_load((REPO_ROOT / "contracts" / "gateway.openapi.yaml").read_text())

#: Where the measurement is written for the issue's evidence.
EVIDENCE = REPO_ROOT / "artifacts" / "ALG-3373" / "g1-latency.json"


def assert_schema(name: str, body: object) -> None:
    """The body NoFX's generated client will decode, against the contract."""
    validator = Draft202012Validator(
        SPEC["components"]["schemas"][name], resolver=RefResolver.from_schema(SPEC)
    )
    errors = sorted(validator.iter_errors(body), key=lambda error: list(error.path))
    assert not errors, "\n".join(error.message for error in errors)


def market_order(account_id: str) -> dict[str, object]:
    """The ``OrderRequest`` NoFX sends to open a position at market."""
    return {
        "account_id": account_id,
        "symbol": SYMBOL,
        "side": "buy",
        "qty": QTY,
        "order_type": "market",
        "time_in_force": "gtc",
    }


def test_market_order_placed_in_nofx_fills_and_is_visible_within_two_seconds(
    pg_engine, redis_client, run_id
):  # noqa: ANN001, ANN201
    """The gate. Everything else in this file supports this one assertion."""
    with g1_stack(engine=pg_engine, redis_client=redis_client, run_id=run_id) as stack:
        stack.await_fit()
        stack.node.account_state("100000.00")

        key = f"g1-{run_id}-market-1"
        submitted = stack.submit_order(key, market_order(stack.account_id))
        assert submitted.status_code == 201, submitted.text
        admitted = submitted.json()
        assert_schema("Order", admitted)
        # `admitted` is a gateway state: the command is on the stream and no
        # venue has seen it. If this were already `filled` the measurement
        # below would be meaningless.
        assert admitted["status"] == "admitted"
        assert admitted["client_order_id"] == key

        # --- the measurement ---------------------------------------------------
        started = time.monotonic()
        filled = stack.await_order(key, "filled", timeout=PATIENCE_S)
        latency_s = time.monotonic() - started

        assert_schema("Order", filled)
        assert latency_s < BUDGET_S, (
            f"the fill took {latency_s:.3f}s to become visible — GATE G1 allows {BUDGET_S}s"
        )

        # --- and it is a real fill, not an empty one ---------------------------
        assert filled["filled_qty"] == QTY
        assert Decimal(filled["avg_px"]) == FILL_PX
        assert filled["venue_order_id"], "the venue's own id never reached the projection"
        assert filled["mode"] == "PAPER"  # rule 2, observed at the far end
        fills = filled["fills"]
        assert len(fills) == 1, fills
        assert fills[0]["trade_id"] == f"T-{key}"
        assert Decimal(fills[0]["qty"]) == Decimal(QTY)
        assert Decimal(fills[0]["px"]) == FILL_PX
        assert fills[0]["commission_currency"] == "USD"

        # --- the position and the balance NoFX renders beside it ---------------
        # Outside the measured window: the position arrives on its own stream
        # (see `G1Stack.await_positions`), and the gate's claim is about the
        # fill. It still has to arrive, and quickly, so the patience is the
        # same.
        opened = stack.await_positions(1, timeout=PATIENCE_S)
        assert len(opened) == 1, opened
        assert_schema("Position", opened[0])
        assert opened[0]["symbol"] == SYMBOL
        assert opened[0]["side"] == "buy"
        assert Decimal(opened[0]["qty"]) == Decimal(QTY)

        accounts = stack.list_accounts().json()["accounts"]
        assert len(accounts) == 1
        assert_schema("Account", accounts[0])
        # The node reported ``"100000.00 USD"``; the gateway renders decimals
        # through ``dec_str``, which normalises an integral value. Compared as
        # a number, because that is what the balance *is* — asserting the
        # string would pin a rendering the contract does not promise.
        assert Decimal(accounts[0]["balances"][0]["total"]) == Decimal("100000.00")
        assert accounts[0]["balances"][0]["currency"] == "USD"

        _write_evidence(latency_s, filled, stack.node_name)


def test_the_fill_is_pushed_on_the_events_stream_too(
    pg_engine, redis_client, run_id
):  # noqa: ANN001, ANN201
    """The same fill, on the socket NoFX tails instead of the read it polls.

    Separate from the gate because it proves a different thing: the gate is
    about the read being current, this is about the push being delivered — and
    a page that is open when the fill happens learns about it here.
    """
    websockets = pytest.importorskip("websockets.sync.client")

    with g1_stack(engine=pg_engine, redis_client=redis_client, run_id=run_id) as stack:
        stack.await_fit()
        # Subscribe from the current head *before* submitting, which is what a
        # NoFX page that is already open has done.
        since = stack.projection.head
        key = f"g1-{run_id}-ws-1"

        with websockets.connect(
            stack.events_url(since=since),
            additional_headers={"Authorization": f"Bearer {TOKEN}"},
        ) as socket:
            assert stack.submit_order(key, market_order(stack.account_id)).status_code == 201

            # One market order produces admitted/submitted/accepted, the fill,
            # and the position — a handful of frames. The bound is a guard
            # against waiting forever on a stream that is delivering the wrong
            # events, not a real expectation.
            seen: list[dict] = []
            while len(seen) < 40:
                frame = json.loads(socket.recv(timeout=PATIENCE_S))
                assert_schema("Event", frame)
                seen.append(frame)
                if frame["type"] == "fill" and frame["order"]["client_order_id"] == key:
                    break
            else:  # pragma: no cover — only on a genuinely broken stream
                raise AssertionError(f"no fill frame for {key} in {len(seen)} frames")

        fill_frames = [f for f in seen if f["type"] == "fill"]
        assert len(fill_frames) == 1, "a fill must not be delivered twice to one subscriber"
        frame = fill_frames[0]
        assert frame["account_id"] == stack.account_id
        assert frame["order"]["status"] == "filled"
        assert Decimal(frame["fill"]["px"]) == FILL_PX
        # The resume cursor the contract promises: strictly after what the
        # subscriber already had.
        assert frame["seq"] > since


def test_the_same_order_submitted_twice_fills_once(
    pg_engine, redis_client, run_id
):  # noqa: ANN001, ANN201
    """P1.3's law, observed from the client end rather than at the actor.

    Two identical ``POST /orders`` with one ``Idempotency-Key``: the second is
    answered ``200`` with the first order, no second command is executed, and
    the venue holds exactly one order. This is the leg that makes a NoFX retry
    (a double click, a dropped response, a redeployed pod) safe.
    """
    with g1_stack(engine=pg_engine, redis_client=redis_client, run_id=run_id) as stack:
        stack.await_fit()
        key = f"g1-{run_id}-dup-1"
        body = market_order(stack.account_id)

        first = stack.submit_order(key, body)
        assert first.status_code == 201
        filled = stack.await_order(key, "filled", timeout=PATIENCE_S)

        replay = stack.submit_order(key, body)
        assert replay.status_code == 200, "a replayed key must not create a second order"
        assert replay.json()["client_order_id"] == key

        # Give a second command every chance to be read and executed before
        # asserting that none was.
        time.sleep(0.5)

        # One order at the venue, one fill in the projection, one position.
        assert stack.node.execution.statuses == {key: FILLED}
        assert stack.get_order(key).json()["fills"] == filled["fills"]
        assert len(stack.list_positions().json()["positions"]) == 1


def _write_evidence(latency_s: float, order: dict, node_name: str) -> None:
    """The measurement ALG-3373 closes on, as a file rather than a log line."""
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(
        json.dumps(
            {
                "gate": "G1",
                "issue": "ALG-3373",
                "budget_s": BUDGET_S,
                "measured_s": round(latency_s, 4),
                "node": node_name,
                "client_order_id": order["client_order_id"],
                "venue_order_id": order["venue_order_id"],
                "filled_qty": order["filled_qty"],
                "avg_px": order["avg_px"],
                "path": [
                    "POST /v1/orders",
                    "algobots:cmd:<node> (redis)",
                    "CommandStream -> CommandActor",
                    "sandbox venue",
                    "trader-*:algobots:events.* (redis)",
                    "NodeEventIngest -> node_events.ingest",
                    "SqlProjection (postgres)",
                    "GET /v1/orders/{clientOrderId}",
                ],
            },
            indent=2,
        )
        + "\n"
    )
