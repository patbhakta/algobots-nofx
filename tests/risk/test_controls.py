"""A08 account controls: pause/cancel/reduce-only/flatten + protective validation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from algobots.contracts.account import Capabilities, CapabilityEntry
from algobots.contracts.enums import OrderSide, OrderType, ProductClass
from algobots.risk.controls import (
    AccountControls,
    ControlAction,
    ProtectionOrder,
    check_action,
    protection_status,
    validate_protective_order,
)

D = Decimal
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


# -- entries paused: stops stay, exits stay -----------------------------------


def test_entry_pause_blocks_entries_only():
    paused = AccountControls(entries_paused=True)
    assert not check_action(paused, ControlAction.ENTRY).allowed
    assert check_action(paused, ControlAction.EXIT).allowed
    assert check_action(paused, ControlAction.REDUCE).allowed
    assert check_action(paused, ControlAction.PROTECTIVE).allowed


def test_reduce_only_blocks_entries_only():
    reduce_only = AccountControls(reduce_only=True)
    assert not check_action(reduce_only, ControlAction.ENTRY).allowed
    assert check_action(reduce_only, ControlAction.REDUCE).allowed


def test_flatten_requires_separate_authorization():
    controls = AccountControls(entries_paused=True)  # a pause never implies flatten
    assert not check_action(controls, ControlAction.FLATTEN).allowed
    authorized = AccountControls(
        flatten_authorized_by="ops-alice",
        flatten_authorized_at=NOW - timedelta(minutes=1),
        flatten_valid_until=NOW + timedelta(minutes=5),
    )
    assert check_action(authorized, ControlAction.FLATTEN, now=NOW).allowed
    expired = authorized.model_copy(
        update={"flatten_valid_until": NOW - timedelta(seconds=1)}
    )
    assert not check_action(expired, ControlAction.FLATTEN, now=NOW).allowed, "grant expired"


def test_cancel_entries_needs_explicit_request():
    controls = AccountControls(cancel_entries_requested=True)
    assert check_action(controls, ControlAction.CANCEL_ENTRIES).allowed
    assert not check_action(AccountControls(), ControlAction.CANCEL_ENTRIES).allowed


# -- protection status: pause never removes stops ------------------------------


def test_protection_status_lists_working_and_paused_stops():
    protections = (
        ProtectionOrder(
            instrument_id="KXA8.DEMO",
            order_type=OrderType.STOP,
            protection="stop",
            side=OrderSide.SELL,
            quantity=D("10"),
            working=True,
        ),
        ProtectionOrder(
            instrument_id="KXB8.DEMO",
            order_type=OrderType.STOP_LIMIT,
            protection="stop-limit",
            side=OrderSide.SELL,
            quantity=D("5"),
            working=False,
        ),
    )
    status = protection_status(AccountControls(entries_paused=True), protections)
    assert status.entries_paused
    assert status.new_risk_blocked
    assert len(status.protections) == 2, "pause must not remove stops"
    assert status.working_protections == 1
    assert status.paused_protections == 1


# -- protective-order validation ------------------------------------------------


def _capabilities(protection: str = "stop", supported: str = "native") -> Capabilities:
    return Capabilities(
        schema_version="1.0",
        account_id="acct-main",
        capability_revision=1,
        observed_at=NOW,
        entries=(
            CapabilityEntry(
                product=ProductClass.EQUITY,
                order_type=OrderType.STOP,
                support=supported,  # type: ignore[arg-type]
                price_decimals=2,
                quantity_decimals=0,
                min_order={"value": "1", "unit": "shares"},
                client_order_id_reusable=False,
                protection_options=(protection,),  # type: ignore[arg-type]
                cancel_semantics="sync",
                market_data_entitled=True,
                test_environment_fidelity="high",
            ),
        ),
    )


def _stop(side: OrderSide = OrderSide.SELL, qty: str = "10") -> ProtectionOrder:
    return ProtectionOrder(
        instrument_id="KXA8.DEMO",
        order_type=OrderType.STOP,
        protection="stop",
        side=side,
        quantity=D(qty),
    )


def test_valid_long_protective_sell_stop():
    result = validate_protective_order(
        _stop(),
        position_quantity=D("10"),
        capabilities=_capabilities(),
        product=ProductClass.EQUITY,
    )
    assert result.valid


def test_wrong_direction_is_invalid():
    result = validate_protective_order(
        _stop(side=OrderSide.BUY),  # a BUY stop "protecting" a long adds risk
        position_quantity=D("10"),
        capabilities=_capabilities(),
        product=ProductClass.EQUITY,
    )
    assert not result.valid and "SELL" in result.reason


def test_oversized_protective_is_new_risk():
    result = validate_protective_order(
        _stop(qty="15"),
        position_quantity=D("10"),
        capabilities=_capabilities(),
        product=ProductClass.EQUITY,
    )
    assert not result.valid and "exceeds" in result.reason


def test_no_position_cannot_be_protected():
    result = validate_protective_order(
        _stop(), position_quantity=D("0"), capabilities=_capabilities(), product=ProductClass.EQUITY
    )
    assert not result.valid


def test_unsupported_broker_capability_is_invalid():
    unsupported = _capabilities(supported="unsupported")
    result = validate_protective_order(
        _stop(), position_quantity=D("10"), capabilities=unsupported, product=ProductClass.EQUITY
    )
    assert not result.valid and "does not support" in result.reason


def test_missing_protection_option_is_invalid():
    caps = _capabilities(protection="trailing-stop")  # has stop entry, but not "stop" option
    result = validate_protective_order(
        _stop(), position_quantity=D("10"), capabilities=caps, product=ProductClass.EQUITY
    )
    assert not result.valid and "protection option" in result.reason
