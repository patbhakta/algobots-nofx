"""P1.3's done-when, and the rules that make it hold.

    *Sending the same command twice creates one order.*

``test_the_same_command_twice_creates_one_order`` is that sentence, asserted
against the venue's order count rather than against the actor's return value —
the claim is about what exists at the venue, so that is what is counted.

These run in CI with no ``nautilus_trader`` and no Redis, by design: the dedupe
rule is in ``CommandActor`` and the engine binding is a thin translation layer
(``tests/node/test_nautilus_binding.py`` covers that against the real engine
where the ``workers`` extra is installed). A guarantee only asserted where the
engine happens to be present is not a guarantee CI can keep.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from algobots.node.command_actor import (
    CANCEL_NOOP,
    CANCEL_SENT,
    CANCEL_UNKNOWN,
    DUPLICATE,
    REFUSED,
    SUBMITTED,
    CommandActor,
)

KEY = "nofx-7f3a9c21-0001"


def submit_command(**overrides) -> dict:
    """The gateway's ``SubmitOrderCommand``, as ``OrderIntent.command`` writes it."""
    command = {
        "command": "submit_order",
        "client_order_id": KEY,
        "account_id": "laya",
        "symbol": "EUR/USD.SIM",
        "side": "buy",
        "qty": "1000",
        "order_type": "market",
        "time_in_force": "gtc",
        "reduce_only": False,
        "mode": "PAPER",
        "admitted_ts": 1_760_000_000.0,
    }
    command.update(overrides)
    return command


def cancel_command(**overrides) -> dict:
    command = {
        "command": "cancel_order",
        "client_order_id": KEY,
        "account_id": "laya",
        "idempotency_key": "nofx-cancel-0001",
        "requested_ts": 1_760_000_100.0,
    }
    command.update(overrides)
    return command


@pytest.fixture
def actor(venue) -> CommandActor:
    return CommandActor(execution=venue, node="nautilus-laya")


# --- the done-when -----------------------------------------------------------


def test_the_same_command_twice_creates_one_order(actor, venue) -> None:
    """ALG-3371's 'Done when', asserted at the venue."""
    first = actor.handle(submit_command())
    second = actor.handle(submit_command())

    assert venue.order_count == 1, "the same command twice created more than one order"
    assert venue.submits_of(KEY) == 1

    assert first.action == SUBMITTED
    assert second.action == DUPLICATE
    # The duplicate is a successful outcome, not an error: the caller asked for
    # an order with this key and there is one.
    assert second.client_order_id == KEY


def test_a_duplicate_is_caught_however_late_it_arrives(actor, venue) -> None:
    """Redelivery after the order has moved on is still a duplicate.

    The dedupe question is "does the venue know this id", not "is it still
    working" — an order that already filled must not be submitted again.
    """
    actor.handle(submit_command())
    venue.fill(KEY)

    assert actor.handle(submit_command()).action == DUPLICATE
    assert venue.order_count == 1


def test_dedupe_survives_a_new_actor(venue) -> None:
    """A restarted node still dedupes, because the state is not in the actor.

    This is the restart case the consumer group creates: the entry is still
    pending, so it is redelivered to a process that has no memory of it. The
    venue (Nautilus' reconciled cache, in production) is what remembers.
    """
    CommandActor(execution=venue).handle(submit_command())
    restarted = CommandActor(execution=venue)

    assert restarted.handle(submit_command()).action == DUPLICATE
    assert venue.order_count == 1


def test_different_keys_are_different_orders(actor, venue) -> None:
    """Dedupe may not be so eager that two real orders collapse into one."""
    actor.handle(submit_command())
    actor.handle(submit_command(client_order_id="nofx-7f3a9c21-0002"))

    assert venue.order_count == 2


def test_the_key_reaches_the_venue_verbatim(actor, venue) -> None:
    """The point of the sprint: no prefixing, no regeneration, no normalising."""
    actor.handle(submit_command())
    assert list(venue.orders) == [KEY]
    assert venue.orders[KEY].client_order_id == KEY


# --- cancelling twice cancels once -------------------------------------------


def test_cancelling_twice_cancels_once(actor, venue) -> None:
    actor.handle(submit_command())

    first = actor.handle(cancel_command())
    second = actor.handle(cancel_command())

    assert venue.cancels_of(KEY) == 1, "the venue was asked to cancel twice"
    assert first.action == CANCEL_SENT
    assert second.action == CANCEL_NOOP


def test_two_cancel_keys_for_one_order_still_cancel_once(actor, venue) -> None:
    """Idempotency is on the order, not only on the cancel request's key.

    The gateway dedupes cancels by key; two retries that generated two keys
    would both reach the node, and the venue must still see one cancel.
    """
    actor.handle(submit_command())
    actor.handle(cancel_command(idempotency_key="nofx-cancel-0001"))
    actor.handle(cancel_command(idempotency_key="nofx-cancel-0002"))

    assert venue.cancels_of(KEY) == 1


def test_cancelling_a_filled_order_is_a_noop(actor, venue) -> None:
    actor.handle(submit_command())
    venue.fill(KEY)

    assert actor.handle(cancel_command()).action == CANCEL_NOOP
    assert venue.cancels_of(KEY) == 0


def test_cancelling_an_unknown_order_does_not_create_one(actor, venue) -> None:
    outcome = actor.handle(cancel_command())

    assert outcome.action == CANCEL_UNKNOWN
    assert venue.order_count == 0
    assert venue.calls == []


def test_a_confirmed_cancel_is_terminal(actor, venue) -> None:
    """Once the node confirms, a further cancel is still one cancel."""
    actor.handle(submit_command())
    actor.handle(cancel_command())
    venue.confirm_cancel(KEY)

    assert actor.handle(cancel_command()).action == CANCEL_NOOP
    assert venue.cancels_of(KEY) == 1


# --- refusals: the node does not trust that the gateway checked --------------


def test_a_non_paper_command_is_refused_at_the_node(actor, venue) -> None:
    """Rule 3, enforced by the process that would place the order.

    The gateway checks it too. This is the check that still holds when the
    command came from an older gateway or was replayed out of the stream.
    """
    outcome = actor.handle(submit_command(mode="LIVE"))

    assert outcome.action == REFUSED
    assert outcome.code == "live_disabled"
    assert venue.calls == [], "a live command reached the venue"


def test_a_command_with_no_mode_is_refused(actor, venue) -> None:
    command = submit_command()
    del command["mode"]

    assert actor.handle(command).code == "live_disabled"
    assert venue.calls == []


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"side": "long"}, "invalid_side"),
        ({"qty": "0"}, "invalid_qty"),
        ({"qty": "-5"}, "invalid_qty"),
        ({"qty": 1000}, "invalid_qty"),  # a JSON number, not a decimal string
        ({"symbol": ""}, "invalid_symbol"),
        ({"order_type": "stop"}, "invalid_order_type"),
        ({"order_type": "limit"}, "invalid_limit_px"),  # limit with no price
        ({"limit_px": "1.10"}, "invalid_limit_px"),  # market with a price
        ({"time_in_force": "forever"}, "invalid_time_in_force"),
        ({"reduce_only": "yes"}, "invalid_reduce_only"),
        ({"client_order_id": "short"}, "invalid_client_order_id"),
        ({"client_order_id": "has spaces in it"}, "invalid_client_order_id"),
    ],
)
def test_a_malformed_command_is_refused_and_never_executed(
    actor, venue, overrides, code
) -> None:
    outcome = actor.handle(submit_command(**overrides))

    assert outcome.action == REFUSED
    assert outcome.code == code
    assert venue.calls == []


def test_an_unknown_field_is_refused_rather_than_ignored(actor, venue) -> None:
    """``additionalProperties: false`` on the reading side.

    Ignoring it would mean executing an order the gateway thinks it qualified.
    """
    outcome = actor.handle(submit_command(stop_px="1.05"))

    assert outcome.code == "unknown_field"
    assert venue.calls == []


@pytest.mark.parametrize("body", [None, "not json", 42, [], {"command": "drop_table"}, {}])
def test_junk_never_raises_and_never_executes(actor, venue, body) -> None:
    """The stream must keep moving: a bad entry is a refusal, not a crash."""
    outcome = actor.handle(body)

    assert outcome.action == REFUSED
    assert venue.calls == []


def test_a_limit_order_carries_its_price(actor, venue) -> None:
    actor.handle(submit_command(order_type="limit", limit_px="1.0950"))

    assert venue.orders[KEY].limit_px == Decimal("1.0950")
    assert venue.orders[KEY].order_type == "limit"


def test_outcomes_say_whether_the_venue_was_touched(actor, venue) -> None:
    """``executed`` is what P1.4's event log and the node's metrics count."""
    assert actor.handle(submit_command()).executed is True
    assert actor.handle(submit_command()).executed is False
    assert actor.handle(cancel_command()).executed is True
    assert actor.handle(submit_command(mode="LIVE")).executed is False


def test_refusals_and_duplicates_are_logged(venue) -> None:
    """A dropped command must leave a trace, or a node looks idle when it isn't."""
    seen: list[tuple[str, dict]] = []
    actor = CommandActor(
        execution=venue,
        node="nautilus-laya",
        log=lambda e, f: seen.append((e, f)),
    )

    actor.handle(submit_command())
    actor.handle(submit_command())
    actor.handle(submit_command(mode="LIVE"))

    events = [event for event, _ in seen]
    assert events == ["command.submitted", "command.duplicate", "command.refused"]
    assert all(fields["node"] == "nautilus-laya" for _, fields in seen)
