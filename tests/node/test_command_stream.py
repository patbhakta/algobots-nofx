"""The stream half: at-least-once delivery, and what it must not cause.

``CommandStream`` is where the duplicate P1.3 defends against actually comes
from. A consumer group redelivers any entry that was handed out and never
acknowledged, so the crash-mid-submit case is not hypothetical — it is the
documented behaviour of the transport.

``test_a_crash_before_the_ack_does_not_create_a_second_order`` is that case,
driven through the real reader against a fake Redis with real pending-list
semantics. The last test runs the whole seam the roadmap describes: the gateway
admits an intent, writes it with its own ``RedisCommandBus``, and the node
reads it back and submits — with the caller's key arriving at the venue
unchanged.
"""

from __future__ import annotations

import json

import pytest

from algobots.gateway.admission import AllowAll, admit
from algobots.gateway.auth import Caller
from algobots.gateway.fixture_node import fixture_stack
from algobots.gateway.nodes import RedisCommandBus
from algobots.node.command_actor import DUPLICATE, SUBMITTED, CommandActor
from algobots.node.command_stream import GROUP, CommandStream, decode, stream_key
from tests.node.test_command_actor import KEY, cancel_command, submit_command

NODE = "nautilus-laya"


@pytest.fixture
def stream(redis, venue) -> CommandStream:
    reader = CommandStream(
        client=redis, actor=CommandActor(execution=venue, node=NODE), node=NODE
    )
    reader.ensure_group()
    return reader


def publish(redis, command: dict) -> str:
    """What ``RedisCommandBus.publish`` writes: the JSON in one field."""
    return redis.xadd(stream_key(NODE), {"command": json.dumps(command)})


def test_stream_key_is_the_contracts_channel() -> None:
    assert stream_key(NODE) == "algobots:cmd:nautilus-laya"


def test_ensure_group_is_idempotent(redis, stream) -> None:
    """Called on every node start, including the ones after the first."""
    stream.ensure_group()  # BUSYGROUP is swallowed; anything else is not
    assert (stream_key(NODE), GROUP) in redis.groups


def test_a_command_is_read_and_executed(redis, stream, venue) -> None:
    publish(redis, submit_command())

    outcomes = stream.poll()

    assert [o.action for o in outcomes] == [SUBMITTED]
    assert venue.order_count == 1


def test_an_executed_entry_is_acknowledged(redis, stream) -> None:
    publish(redis, submit_command())
    stream.poll()

    assert redis.pending_count(stream_key(NODE), GROUP) == 0


def test_a_crash_before_the_ack_does_not_create_a_second_order(
    redis, venue
) -> None:
    """The restart path, end to end.

    The first node submits and then dies before acknowledging, so the entry is
    still pending. A second node starts, drains that pending list, and is
    handed the identical command — and the venue still has one order.
    """
    publish(redis, submit_command())

    crashed = CommandStream(client=redis, actor=CommandActor(execution=venue), node=NODE)
    crashed.ensure_group()
    # Deliver and execute, but never ack: exactly what a crash looks like.
    entries = crashed._read(">")
    for _key, batch in entries:
        for _entry_id, fields in batch:
            crashed.actor.handle(decode(fields))
    assert venue.order_count == 1
    assert redis.pending_count(stream_key(NODE), GROUP) == 1

    restarted = CommandStream(client=redis, actor=CommandActor(execution=venue), node=NODE)
    redelivered = restarted.drain_pending()

    assert [o.action for o in redelivered] == [DUPLICATE]
    assert venue.order_count == 1, "redelivery created a second order"
    assert redis.pending_count(stream_key(NODE), GROUP) == 0


def test_drain_pending_runs_before_new_entries(redis, venue) -> None:
    """Order matters: a command queued before the crash is the older intent."""
    publish(redis, submit_command())
    first = CommandStream(client=redis, actor=CommandActor(execution=venue), node=NODE)
    first.ensure_group()
    for _key, batch in first._read(">"):
        for _entry_id, fields in batch:
            first.actor.handle(decode(fields))

    publish(redis, submit_command(client_order_id="nofx-7f3a9c21-0002"))

    restarted = CommandStream(client=redis, actor=CommandActor(execution=venue), node=NODE)
    restarted.run(until=lambda: True)  # ensure_group + drain_pending, then stop

    # The pending (older) entry was handled; the new one was not yet read.
    assert redis.pending_count(stream_key(NODE), GROUP) == 0
    assert venue.order_count == 1


def test_a_malformed_entry_is_acked_and_does_not_block_the_stream(
    redis, stream, venue
) -> None:
    """A poison entry would stall every command behind it."""
    redis.xadd(stream_key(NODE), {"command": "{not json"})
    publish(redis, submit_command())

    outcomes = stream.poll()

    assert [o.action for o in outcomes] == ["refused", SUBMITTED]
    assert redis.pending_count(stream_key(NODE), GROUP) == 0
    assert venue.order_count == 1


def test_an_entry_with_no_command_field_is_refused(redis, stream) -> None:
    redis.xadd(stream_key(NODE), {"other": "x"})

    assert [o.action for o in stream.poll()] == ["refused"]


def test_decode_tolerates_bytes(redis) -> None:
    """The client may or may not be built with decode_responses=True."""
    command = submit_command()
    assert decode({b"command": json.dumps(command).encode()}) == command
    assert decode({}) is None


def test_recent_outcomes_are_bounded(redis, stream) -> None:
    """A long-running node may not grow this list without limit."""
    stream._recent_max = 4
    for n in range(8):
        publish(redis, submit_command(client_order_id=f"nofx-key-{n:08d}"))
    stream.poll()

    assert len(stream.recent) == 4


def test_a_submit_and_its_cancel_both_travel_the_stream(redis, stream, venue) -> None:
    publish(redis, submit_command())
    publish(redis, cancel_command())
    publish(redis, cancel_command())

    outcomes = stream.poll()

    assert [o.action for o in outcomes] == [SUBMITTED, "cancel_sent", "cancel_noop"]
    assert venue.cancels_of(KEY) == 1


# --- the full seam: gateway admission -> stream -> node ----------------------


def test_the_gateway_s_own_command_is_what_the_node_reads(redis, venue) -> None:
    """One wire shape, written by the gateway and read by the node.

    Both halves of the contract's ``SubmitOrderCommand`` run here: the
    gateway's ``RedisCommandBus`` writes the entry and the node's reader parses
    it. A field renamed on one side fails this test rather than production.
    """
    registry, projection, _bus, node = fixture_stack(node_name=NODE)
    node.heartbeat(reconciled=True)
    bus = RedisCommandBus(client=redis)

    caller = Caller(principal_id="m-1", accounts=("laya",))
    body = {
        "account_id": "laya",
        "symbol": "EUR/USD.SIM",
        "side": "buy",
        "qty": "1000",
        "order_type": "limit",
        "limit_px": "1.0950",
    }
    admission, intent = admit(
        body,
        caller=caller,
        idempotency_key=KEY,
        registry=registry,
        projection=projection,
        gate=AllowAll(),
        now=node.clock,
    )
    assert intent is not None
    bus.publish(intent.node, intent.command(now=node.clock))

    reader = CommandStream(client=redis, actor=CommandActor(execution=venue), node=NODE)
    reader.ensure_group()
    outcomes = reader.poll()

    assert [o.action for o in outcomes] == [SUBMITTED]
    # The caller's Idempotency-Key is the id the venue sees, and the gateway's
    # own record of the order agrees with it.
    assert admission.order.client_order_id == KEY
    assert list(venue.orders) == [KEY]
    assert str(venue.orders[KEY].limit_px) == "1.0950"


def test_a_replayed_http_request_never_reaches_the_stream(redis, venue) -> None:
    """The gateway's layer of the guarantee, shown next to the node's.

    A retried POST is answered from the projection and writes no second
    command — so the node's dedupe is a backstop for transport redelivery,
    not the only thing standing between a retry and a double order.
    """
    registry, projection, _bus, node = fixture_stack(node_name=NODE)
    node.heartbeat(reconciled=True)
    bus = RedisCommandBus(client=redis)
    caller = Caller(principal_id="m-1", accounts=("laya",))
    body = {
        "account_id": "laya",
        "symbol": "EUR/USD.SIM",
        "side": "buy",
        "qty": "1000",
        "order_type": "market",
    }

    for _attempt in range(3):
        admission, intent = admit(
            body,
            caller=caller,
            idempotency_key=KEY,
            registry=registry,
            projection=projection,
            gate=AllowAll(),
            now=node.clock,
        )
        if intent is not None:
            bus.publish(intent.node, intent.command(now=node.clock))

    assert len(redis.streams[stream_key(NODE)]) == 1, "a replay wrote a second command"

    reader = CommandStream(client=redis, actor=CommandActor(execution=venue), node=NODE)
    reader.ensure_group()
    reader.poll()
    assert venue.order_count == 1


def test_engine_queue_and_egress_failures_leave_entry_pending(redis, stream, venue):
    publish(redis, submit_command())

    def waiting(outcome):
        raise RuntimeError("engine has only queued the command")

    stream.before_ack = waiting
    with pytest.raises(RuntimeError, match="only queued"):
        stream.poll()
    assert venue.order_count == 1
    # A restart must replay the unacknowledged entry without submitting twice.
    restarted = CommandStream(client=redis, actor=CommandActor(execution=venue), node=NODE)
    assert [o.action for o in restarted.drain_pending()] == [DUPLICATE]
    assert venue.order_count == 1
