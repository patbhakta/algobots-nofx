"""A08 policy engine: deterministic precedence, clamps, denials."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from algobots.contracts.risk import RISK_RULE_PRECEDENCE, RiskPolicyVersion
from algobots.risk.policy import (
    AccountRiskState,
    InstrumentMark,
    RiskProposal,
    buffered_reservation,
    evaluate_proposal,
)

T0 = datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC)
USD = "USD"


def make_policy(**overrides) -> RiskPolicyVersion:
    from algobots.contracts.risk import (
        PolicyConstraints,
        StaleStateRules,
    )

    kwargs = dict(
        schema_version="1.0",
        policy_revision="risk-a08-r1",
        account_id="acct-main",
        base_currency=USD,
        timezone="UTC",
        permissions=(),
        deployment_budgets=(),
        constraints=PolicyConstraints(
            fee_buffer_bps=Decimal("10"),
            slippage_buffer_bps=Decimal("5"),
        ),
        stale_state=StaleStateRules(
            max_mark_age_seconds=30,
            accepted_mark_qualities=("REALTIME", "DELAYED"),
        ),
        created_at=T0,
    )
    kwargs.update(overrides)
    return RiskPolicyVersion(**kwargs)


def make_proposal(**overrides) -> RiskProposal:
    kwargs = dict(
        account_id="acct-main",
        deployment_id="dep-1",
        instrument_id="KXA8.DEMO",
        side="BUY",
        kind="ENTRY",
        quantity=Decimal("7"),
        reference_price=Decimal("100"),
        currency=USD,
    )
    kwargs.update(overrides)
    return RiskProposal(**kwargs)


def make_state(**overrides) -> AccountRiskState:
    mark = overrides.pop(
        "mark",
        InstrumentMark(
            instrument_id="KXA8.DEMO",
            price=Decimal("100"),
            quality="REALTIME",
            observed_at=T0,
        ),
    )
    kwargs = dict(
        cash_available=Decimal("10000"),
        equity_reference=Decimal("10000"),
        instrument_mark=mark,
        connected=True,
    )
    kwargs.update(overrides)
    return AccountRiskState(**kwargs)


# -- determinism (the AC4 backbone) ------------------------------------------


def test_same_inputs_same_decision_always():
    policy, proposal, state = make_policy(), make_proposal(), make_state()
    decisions = {
        evaluate_proposal(policy, proposal, state, now=T0).model_dump_json()
        for _ in range(25)
    }
    assert len(decisions) == 1


def test_precedence_is_frozen_and_complete():
    assert RISK_RULE_PRECEDENCE == (
        "instrument_permission",
        "stale_state",
        "account_control",
        "daily_loss",
        "rate_limit",
        "deployment_budget",
        "max_concentration",
        "max_gross_exposure",
        "max_order_notional",
        "insufficient_funds",
    )


def test_first_rule_wins_permission_beats_everything():
    from algobots.contracts.risk import InstrumentPermission

    policy = make_policy(
        permissions=(InstrumentPermission(instrument_id="KXA8.DEMO", permitted=False),)
    )
    # everything else is ALSO breached; only the permission may be reported
    state = make_state(
        cash_available=Decimal("1"),  # insufficient funds
        daily_pnl=Decimal("-999999"),  # loss cap (if set) breached
        connected=False,  # stale state
    )
    decision = evaluate_proposal(policy, make_proposal(), state, now=T0)
    assert decision.decision == "DENY" and decision.rule == "instrument_permission"


# -- clean approve ------------------------------------------------------------


def test_approve_and_buffers():
    policy, proposal, state = make_policy(), make_proposal(), make_state()
    decision = evaluate_proposal(policy, proposal, state, now=T0)
    assert decision.decision == "APPROVE"
    assert not decision.rule and not decision.reason
    # 700 notional + 10bps fee + 5bps slippage = 700 * 1.0015
    assert decision.required_reservation.amount == Decimal("701.05")
    assert buffered_reservation(policy, Decimal("700")) == Decimal("701.05")


# -- AC4: AI asks for more than allowed → deterministic clamp + audit reason --


def test_ai_oversize_request_is_clamped_with_explicit_reason():
    from algobots.contracts.base import Money

    policy = make_policy(
        constraints=make_policy().constraints.model_copy(
            update={"max_order_notional": Money(amount="500.00", currency=USD)}
        ),
    )
    decision = evaluate_proposal(policy, make_proposal(), make_state(), now=T0)
    assert decision.decision == "CLAMP"
    assert decision.rule == "max_order_notional"
    assert "clamped" in decision.reason
    assert decision.requested_notional.amount == Decimal("700")
    assert decision.approved_notional.amount == Decimal("500.00")
    assert decision.required_reservation.amount == Decimal("500.75")


def test_gross_exposure_headroom_clamp_and_deny():
    from algobots.contracts.base import Money

    constraints = make_policy().constraints.model_copy(
        update={"max_gross_exposure": Money(amount="900.00", currency=USD)}
    )
    policy = make_policy(constraints=constraints)
    clamped = evaluate_proposal(
        policy, make_proposal(), make_state(gross_exposure=Decimal("400")), now=T0
    )
    assert clamped.decision == "CLAMP" and clamped.rule == "max_gross_exposure"
    denied = evaluate_proposal(
        policy, make_proposal(), make_state(gross_exposure=Decimal("900")), now=T0
    )
    assert denied.decision == "DENY" and denied.rule == "max_gross_exposure"


def test_concentration_clamp_and_deny():
    from algobots.contracts.risk import ConcentrationLimit

    constraints = make_policy().constraints.model_copy(
        update={
            "max_concentration": (
                ConcentrationLimit(max_percent_of_equity=Decimal("5")),
            )
        }
    )
    policy = make_policy(constraints=constraints)  # 5% of 10k = 500
    clamped = evaluate_proposal(
        policy, make_proposal(), make_state(instrument_exposure=Decimal("100")), now=T0
    )
    assert clamped.decision == "CLAMP" and clamped.rule == "max_concentration"
    denied = evaluate_proposal(
        policy, make_proposal(), make_state(instrument_exposure=Decimal("500")), now=T0
    )
    assert denied.decision == "DENY" and denied.rule == "max_concentration"


# -- AC3: daily loss denies entries, never risk-reducing actions --------------


def test_daily_loss_denies_entry_but_exit_passes_uncapped():
    from algobots.contracts.base import Money

    constraints = make_policy().constraints.model_copy(
        update={"max_daily_loss": Money(amount="100.00", currency=USD)}
    )
    policy = make_policy(constraints=constraints)
    breached = make_state(daily_pnl=Decimal("-100.00"))  # loss == cap trips
    entry = evaluate_proposal(policy, make_proposal(), breached, now=T0)
    assert entry.decision == "DENY" and entry.rule == "daily_loss"
    exit_ = evaluate_proposal(
        policy, make_proposal(kind="EXIT", side="SELL"), breached, now=T0
    )
    assert exit_.decision == "APPROVE"


# -- rate limits ---------------------------------------------------------------


def test_rate_limits_deny_entries_only():
    from algobots.contracts.risk import RateLimits

    constraints = make_policy().constraints.model_copy(
        update={"rate_limits": RateLimits(max_orders_per_minute=5, max_entries_per_day=10)}
    )
    policy = make_policy(constraints=constraints)
    denied = evaluate_proposal(
        policy, make_proposal(orders_last_minute=5), make_state(), now=T0
    )
    assert denied.decision == "DENY" and denied.rule == "rate_limit"
    ok = evaluate_proposal(
        policy, make_proposal(orders_last_minute=4, entries_today=9), make_state(), now=T0
    )
    assert ok.decision == "APPROVE"


def test_deployment_budget_deny_and_clamp():
    from algobots.contracts.base import Money
    from algobots.contracts.risk import DeploymentBudget

    policy = make_policy(
        deployment_budgets=(
            DeploymentBudget(
                deployment_id="dep-1",
                max_gross_notional=Money(amount="600.00", currency=USD),
            ),
        )
    )
    denied = evaluate_proposal(
        policy,
        make_proposal(),
        make_state(deployment_gross_notional=Decimal("600")),
        now=T0,
    )
    assert denied.decision == "DENY" and denied.rule == "deployment_budget"
    clamped = evaluate_proposal(
        policy,
        make_proposal(),
        make_state(deployment_gross_notional=Decimal("200")),
        now=T0,
    )
    assert clamped.decision == "CLAMP" and clamped.rule == "deployment_budget"
    assert clamped.approved_notional.amount == Decimal("400.00")


# -- AC5: stale state blocks new risk, not risk-reducing ----------------------


def test_stale_mark_blocks_entry_but_not_exit():
    policy = make_policy()
    stale = make_state(
        mark=InstrumentMark(
            instrument_id="KXA8.DEMO",
            price=Decimal("100"),
            quality="REALTIME",
            observed_at=T0 - timedelta(seconds=31),
        )
    )
    entry = evaluate_proposal(policy, make_proposal(), stale, now=T0)
    assert entry.decision == "DENY" and entry.rule == "stale_state"
    exit_ = evaluate_proposal(policy, make_proposal(kind="EXIT", side="SELL"), stale, now=T0)
    assert exit_.decision == "APPROVE"


def test_mark_quality_below_accepted_blocks_entry():
    policy = make_policy()
    indicative = make_state(
        mark=InstrumentMark(
            instrument_id="KXA8.DEMO",
            price=Decimal("100"),
            quality="INDICATIVE",
            observed_at=T0,
        )
    )
    decision = evaluate_proposal(policy, make_proposal(), indicative, now=T0)
    assert decision.decision == "DENY" and decision.rule == "stale_state"
    assert "INDICATIVE" in decision.reason


def test_disconnect_blocks_entry():
    decision = evaluate_proposal(
        make_policy(), make_proposal(), make_state(connected=False), now=T0
    )
    assert decision.decision == "DENY" and decision.rule == "stale_state"
    assert "connection" in decision.reason


def test_stale_reconciliation_watermark_blocks_entry():
    decision = evaluate_proposal(
        make_policy(),
        make_proposal(),
        make_state(reconciled_within_seconds=45),
        now=T0,
    )
    assert decision.decision == "DENY" and decision.rule == "stale_state"
    assert "reconciliation" in decision.reason


# -- funds (with reservations already counted) --------------------------------


def test_funds_check_counts_active_reservations():
    policy, proposal = make_policy(), make_proposal()
    # 1000 available, 350 already reserved (an active reservation) → only 650
    state = make_state(cash_available=Decimal("1000"), cash_reserved=Decimal("350"))
    decision = evaluate_proposal(policy, proposal, state, now=T0)
    assert decision.decision == "DENY" and decision.rule == "insufficient_funds"
    assert "reservations retain" in decision.reason
