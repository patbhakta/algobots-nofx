"""A01 acceptance case 1: golden contracts round-trip; incompatible fields fail clearly."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from algobots.contracts import registry

GOLDEN = Path(__file__).parent / "golden"
VALID = sorted((GOLDEN / "valid").glob("*.json"))
INVALID = sorted((GOLDEN / "invalid").glob("*.json"))


def test_every_registered_contract_has_a_valid_golden():
    covered = {tuple(p.stem.split("@")) for p in VALID}
    assert covered == set(registry.registered())


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.stem)
def test_valid_golden_round_trips_exactly(path):
    data = json.loads(path.read_text())
    name = path.stem.split("@")[0]
    model = registry.parse(name, data)
    assert model.model_dump(mode="json") == data
    assert registry.parse(name, json.loads(model.model_dump_json())) == model


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.stem)
def test_invalid_golden_fails_with_clear_message(path):
    case = json.loads(path.read_text())
    with pytest.raises((ValidationError, registry.UnknownContractError)) as exc:
        registry.parse(case["contract"], case["data"])
    assert case["error_contains"] in str(exc.value)


def test_decimals_stay_exact_strings_with_units():
    data = json.loads((GOLDEN / "valid" / "OrderPlan@1.0.json").read_text())
    plan = registry.parse("OrderPlan", data)
    child = plan.children[0]
    assert child.max_notional.amount == Decimal("1872.50")
    assert child.max_notional.currency == "USD"
    assert child.quantity.unit == "shares"
    dumped = plan.model_dump(mode="json")["children"][0]
    assert dumped["max_notional"] == {"amount": "1872.50", "currency": "USD"}


@pytest.mark.parametrize(
    "bad", [10, 10.5, True, "1e", "Infinity", "1_000", " 5 ", "1E+3", "-0", "+5", "05", "1."]
)
def test_non_string_or_non_finite_amounts_rejected(bad):
    from algobots.contracts import Money

    with pytest.raises(ValidationError):
        Money(amount=bad, currency="USD")
