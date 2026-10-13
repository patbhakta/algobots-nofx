"""Order/intent state machines: full transition matrix, UNKNOWN discipline,
pending cancel/replace, rollups, and contract-literal alignment."""

from __future__ import annotations

import pytest

from algobots.contracts.outbox import ChildOrderStateValue, IntentStatusValue
from algobots.execution.ledger import states
from algobots.execution.ledger.states import (
    IllegalTransition,
    IntentState,
    OrderState,
    intent_rollup,
)

ALL = list(OrderState)
TERMINAL = states.ORDER_TERMINAL_STATES


def test_contract_literals_match_state_enums():
    """The /intents/{id} contract literals cannot drift from the ledger enums."""
    import typing

    order_literals = set(typing.get_args(ChildOrderStateValue))
    assert order_literals == {s.value for s in OrderState}
    intent_literals = set(typing.get_args(IntentStatusValue))
    assert intent_literals == {s.value for s in IntentState}


def test_self_edges_are_legal_everywhere():
    for current in ALL:
        assert states.transition(current, current) is current


def test_terminal_states_have_no_exits():
    for current in TERMINAL:
        for target in ALL:
            if target is current:
                continue
            with pytest.raises(IllegalTransition):
                states.transition(current, target)


def test_unknown_exit_requires_reconciliation():
    with pytest.raises(IllegalTransition, match="reconciliation"):
        states.transition(OrderState.UNKNOWN, OrderState.ACKNOWLEDGED)
    assert (
        states.transition(OrderState.UNKNOWN, OrderState.ACKNOWLEDGED, reconciliation=True)
        is OrderState.ACKNOWLEDGED
    )


def test_every_live_state_can_reach_unknown_and_every_terminal_is_reachable():
    live = [s for s in ALL if s not in TERMINAL and s is not OrderState.UNKNOWN]
    for source in live:
        assert OrderState.UNKNOWN in states._LEGAL[source]
    for target in TERMINAL:
        assert any(target in edges for edges in states._LEGAL.values())


def test_pending_cancel_and_replace_edges():
    assert (
        states.transition(OrderState.ACKNOWLEDGED, OrderState.PENDING_CANCEL)
        is OrderState.PENDING_CANCEL
    )
    assert states.transition(OrderState.PENDING_CANCEL, OrderState.CANCELED) is OrderState.CANCELED
    # a fill can race the cancel
    assert states.transition(OrderState.PENDING_CANCEL, OrderState.FILLED) is OrderState.FILLED
    # cancel rejected: back to live
    assert (
        states.transition(OrderState.PENDING_CANCEL, OrderState.ACKNOWLEDGED)
        is OrderState.ACKNOWLEDGED
    )
    assert (
        states.transition(OrderState.ACKNOWLEDGED, OrderState.PENDING_REPLACE)
        is OrderState.PENDING_REPLACE
    )
    # replaced: the original is cancelled, the successor is a NEW child order
    assert states.transition(OrderState.PENDING_REPLACE, OrderState.CANCELED) is OrderState.CANCELED


def test_illegal_edges_raise():
    with pytest.raises(IllegalTransition):
        states.transition(OrderState.SUBMITTED, OrderState.PENDING_CANCEL)
    with pytest.raises(IllegalTransition):
        states.transition(OrderState.REJECTED, OrderState.UNKNOWN)


def test_intent_rollup():
    assert intent_rollup([], planned=False) is IntentState.ACCEPTED
    assert intent_rollup([], planned=True) is IntentState.PLANNED
    assert intent_rollup([OrderState.FILLED], planned=True) is IntentState.FILLED
    assert intent_rollup([OrderState.FILLED, OrderState.PARTIALLY_FILLED], planned=True) is (
        IntentState.PARTIALLY_FILLED
    )
    assert (
        intent_rollup([OrderState.FILLED, OrderState.UNKNOWN], planned=True) is IntentState.UNKNOWN
    )
    assert intent_rollup([OrderState.CANCELED], planned=True) is IntentState.CANCELED
    assert (
        intent_rollup([OrderState.FILLED, OrderState.CANCELED], planned=True) is IntentState.FAILED
    )
    assert intent_rollup([OrderState.ACKNOWLEDGED, OrderState.SUBMITTED], planned=True) is (
        IntentState.SUBMITTED
    )
