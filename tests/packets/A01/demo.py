"""A01 demo: one golden contract round-trip plus four failure paths (``make demo-A01``)."""

import json
from pathlib import Path

from pydantic import ValidationError

from algobots.contracts import registry

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = ROOT / "tests" / "contracts" / "golden"
PINS = {
    pid: p["contract_pins"]
    for pid, p in json.loads((ROOT / "docs" / "repository-map.json").read_text())["packets"].items()
}

print(
    f"registry: {len(registry.registered())} contracts; lock drift: "
    f"{registry.verify_lock(registry.load_lock()) or 'none'}"
)

plan_data = json.loads((GOLDEN / "valid" / "OrderPlan@1.0.json").read_text())
plan = registry.parse("OrderPlan", plan_data)
child = plan.children[0]
print(
    f"[ok] OrderPlan@1.0 child {child.child_id}: {child.quantity.value} {child.quantity.unit} "
    f"x {child.limit_price.amount} = {child.quantity.value * child.limit_price.amount} "
    f"<= max_notional {child.max_notional.amount} {child.max_notional.currency}; "
    f"round-trip exact: {plan.model_dump(mode='json') == plan_data}"
)

bad = {**plan_data, "max_fee": {"amount": 1.0, "currency": "USD"}}
try:
    registry.parse("OrderPlan", bad)
except ValidationError as exc:
    print(f"[rejected] float amount: {exc.errors()[0]['msg']}")

swapped = json.loads(json.dumps(plan_data))
swapped["children"][0]["instrument_id"] = "XNAS:TSLA"  # approved plan_hash kept
try:
    registry.parse("OrderPlan", swapped)
except ValidationError as exc:
    print(f"[rejected] edited plan under an approved hash: {exc.errors()[0]['msg']}")

lock = registry.load_lock()
stranded = {name: dict(v) for name, v in lock.items()}
del stranded["OrderPlan"]["1.0"]
try:
    registry.check_lock_transition(lock, stranded, PINS)
except registry.SchemaRevisionError as exc:
    print(f"[rejected] schema revision: {exc}")

rewritten = {name: dict(v) for name, v in lock.items()}
rewritten["Signal"]["1.0"] = "0" * 64  # e.g. a validator tightened, then --write-lock
try:
    registry.check_lock_transition(lock, rewritten, PINS)
except registry.SchemaRevisionError as exc:
    print(f"[rejected] in-place lock rewrite: {exc}")
