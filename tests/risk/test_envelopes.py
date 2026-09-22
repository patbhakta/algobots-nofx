"""RiskEnvelope — required Decimal money caps, clamp/check semantics."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from algobots.risk.envelopes import RiskEnvelope

ENV = RiskEnvelope(max_order_value=Decimal("1000"), max_daily_loss=Decimal("500"))


def test_money_caps_are_required():
    with pytest.raises(ValidationError):
        RiskEnvelope(max_order_value=Decimal("1000"))  # missing max_daily_loss
    with pytest.raises(ValidationError):
        RiskEnvelope(max_daily_loss=Decimal("500"))  # missing max_order_value
    with pytest.raises(ValidationError):
        RiskEnvelope()


def test_money_caps_must_be_positive():
    for bad in (0, -1):
        with pytest.raises(ValidationError):
            RiskEnvelope(max_order_value=Decimal(bad), max_daily_loss=Decimal("500"))
        with pytest.raises(ValidationError):
            RiskEnvelope(max_order_value=Decimal("1000"), max_daily_loss=Decimal(bad))


def test_caps_are_decimal():
    env = RiskEnvelope(max_order_value="1000.5", max_daily_loss="500.25")
    assert isinstance(env.max_order_value, Decimal)
    assert isinstance(env.max_daily_loss, Decimal)
    assert env.max_order_value == Decimal("1000.5")
    assert env.max_daily_loss == Decimal("500.25")


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        RiskEnvelope(
            max_order_value=Decimal("1"),
            max_daily_loss=Decimal("1"),
            surprise=True,
        )


def test_order_value_within_cap_not_fired():
    check = ENV.clamp_order_value(Decimal("999.99"))
    assert check.fired is False
    assert check.approved == Decimal("999.99")


def test_order_value_at_cap_boundary_not_fired():
    check = ENV.clamp_order_value(Decimal("1000"))
    assert check.fired is False
    assert check.approved == Decimal("1000")


def test_order_value_above_cap_clamped_preserving_sign():
    check = ENV.clamp_order_value(Decimal("1500"))
    assert check.fired is True
    assert check.approved == Decimal("1000")
    short = ENV.clamp_order_value(Decimal("-2500"))
    assert short.fired is True
    assert short.approved == Decimal("-1000")


def test_daily_loss_trips_at_or_beyond_cap():
    assert ENV.check_daily_loss(Decimal("100")).tripped is False  # gain
    assert ENV.check_daily_loss(Decimal("0")).tripped is False
    assert ENV.check_daily_loss(Decimal("-499.99")).tripped is False
    assert ENV.check_daily_loss(Decimal("-500")).tripped is True  # at cap
    assert ENV.check_daily_loss(Decimal("-500.01")).tripped is True
