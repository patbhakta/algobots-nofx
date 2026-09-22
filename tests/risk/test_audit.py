"""Audit sinks + RiskGate wiring — exactly one ClampEventRow per firing."""

import json
from decimal import Decimal

from algobots.risk.audit import (
    ClampEventRow,
    InMemorySink,
    JsonlSink,
    RiskGate,
    row_from_clamp,
)
from algobots.risk.breakers import RateBreakers
from algobots.risk.envelopes import RiskEnvelope
from algobots.risk.limits import ClampEvent, RiskLimits

LIMITS = RiskLimits(max_position_pct=0.25, max_gross_exposure=1.0)
ENVELOPE = RiskEnvelope(max_order_value=Decimal("1000"), max_daily_loss=Decimal("500"))


class FakeClock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def make_gate(sink, breakers=None):
    return RiskGate(
        limits=LIMITS,
        envelope=ENVELOPE,
        breakers=breakers if breakers is not None else RateBreakers(clock=FakeClock()),
        sink=sink,
        now=lambda: "2026-09-22T00:00:00+00:00",
    )


def test_row_from_clamp_maps_vendored_event():
    ev = ClampEvent(limit="max_position_pct", ticker="AAPL", before=0.6, after=0.25)
    row = row_from_clamp(ev, deployment_id="dep", ts="2026-09-22T00:00:00+00:00")
    assert row.source == "limits"
    assert row.limit == "max_position_pct"
    assert row.ticker == "AAPL"
    assert row.deployment_id == "dep"
    assert row.before == 0.6
    assert row.after == 0.25


def test_in_memory_sink_collects_rows():
    sink = InMemorySink()
    sink.write(ClampEventRow(ts="T0", source="limits", limit="x"))
    assert len(sink.rows) == 1


def test_jsonl_sink_one_json_line_per_row(tmp_path):
    path = tmp_path / "clamp.jsonl"
    sink = JsonlSink(path)
    for i in range(3):
        sink.write(ClampEventRow(ts=f"T{i}", source="limits", limit="x", before=float(i)))
    lines = path.read_text().splitlines()
    assert len(lines) == 3
    parsed = [json.loads(line) for line in lines]
    assert [p["before"] for p in parsed] == [0.0, 1.0, 2.0]


def test_apply_weights_writes_one_row_per_clamp():
    sink = InMemorySink()
    gate = make_gate(sink)
    result = gate.apply_weights({t: 0.5 for t in "ABCDEF"}, deployment_id="dep")
    assert len(result.clamps) == 7  # 6 position clamps + 1 gross clamp
    assert len(sink.rows) == 7
    assert all(r.source == "limits" for r in sink.rows)
    assert all(r.deployment_id == "dep" for r in sink.rows)
    assert [r.limit for r in sink.rows].count("max_gross_exposure") == 1


def test_apply_weights_within_limits_writes_nothing():
    sink = InMemorySink()
    gate = make_gate(sink)
    result = gate.apply_weights({"AAPL": 0.2, "MSFT": -0.1})
    assert result.clamps == []
    assert sink.rows == []


def test_entry_clamped_by_order_value_writes_one_row():
    sink = InMemorySink()
    gate = make_gate(sink)
    decision = gate.approve_order(
        kind="entry", value=Decimal("2500"), deployment_id="dep", ticker="AAPL"
    )
    assert decision.allowed is True
    assert decision.approved_value == Decimal("1000")
    assert len(sink.rows) == 1
    row = sink.rows[0]
    assert row.source == "envelope"
    assert row.limit == "max_order_value"
    assert row.ticker == "AAPL"
    assert row.before == 2500.0
    assert row.after == 1000.0


def test_entry_denied_by_daily_loss_writes_one_row():
    sink = InMemorySink()
    gate = make_gate(sink)
    decision = gate.approve_order(
        kind="entry", value=Decimal("10"), daily_pnl=Decimal("-600")
    )
    assert decision.allowed is False
    assert decision.reason == "max_daily_loss"
    assert len(sink.rows) == 1
    assert sink.rows[0].source == "envelope"
    assert sink.rows[0].limit == "max_daily_loss"


def test_entry_denied_by_breaker_writes_one_row():
    sink = InMemorySink()
    gate = make_gate(sink)
    for _ in range(10):
        assert gate.approve_order(
            kind="entry", value=Decimal("1"), deployment_id="dep"
        ).allowed
    decision = gate.approve_order(kind="entry", value=Decimal("1"), deployment_id="dep")
    assert decision.allowed is False
    assert decision.reason == "per_deployment_orders_per_minute"
    assert len(sink.rows) == 1
    assert sink.rows[0].source == "breaker"


def test_exit_privileged_while_everything_tripped_and_exhausted():
    sink = InMemorySink()
    rb = RateBreakers(clock=FakeClock())
    gate = make_gate(sink, breakers=rb)

    # exhaust the daily-loss envelope
    denied = gate.approve_order(
        kind="entry", value=Decimal("10"), daily_pnl=Decimal("-500"), deployment_id="dep"
    )
    assert denied.allowed is False
    assert denied.reason == "max_daily_loss"

    # trip per-deployment minute + day, fleet minute + day, arm the cooldown
    t = 0.0
    for _ in range(200):
        rb.record("entry", "dep", now=t)
        t += 7.0
    for i in range(500):
        rb.record("entry", f"fleet{i % 8}", now=t)
        t += 61.0
    for _ in range(10):
        rb.record("entry", "dep", now=t)
        t += 0.1
    rb.record("exit", "dep", now=t)

    # the exit: oversized, envelope exhausted, every breaker tripped/cooldown armed
    decision = gate.approve_order(
        kind="exit",
        value=Decimal("9999999"),
        daily_pnl=Decimal("-500"),
        deployment_id="dep",
        ticker="AAPL",
        now=t + 0.1,
    )
    assert decision.allowed is True
    assert decision.approved_value == Decimal("9999999")  # not clamped either
    assert len(sink.rows) == 1  # only the earlier entry denial; the exit fired nothing
    assert sink.rows[0].limit == "max_daily_loss"
