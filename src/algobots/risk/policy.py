"""Deterministic account risk policy evaluation (A08).

``evaluate_proposal`` is a PURE function: same policy, same proposal, same
state snapshot, same clock → same :class:`RiskDecision`. The LLM's influence
over the book ends at the proposal: when an AI proposal requests greater
leverage or size than the policy allows, the policy clamps it to the largest
admissible size (or denies it) with an explicit audit reason naming the rule
— never silently, never non-deterministically.

Precedence is frozen in ``contracts.risk.RISK_RULE_PRECEDENCE``: the first
rule that fires is the decision; later rules are not evaluated. Denials that
need no account state (permission) come first; the funds check comes last so
a clamped proposal is checked against funds at its CLAMPED size.

Risk-reducing proposals (exits, reduce-only, protective) are exempt from the
stale-state, daily-loss, pause and funds denials — an exit is never hostage
to a data outage or a breached loss cap — but never exempt from instrument
permission or venue-constraint validation (``controls.validate_protective``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from algobots.contracts.base import Money
from algobots.contracts.enums import OrderSide, ProductClass
from algobots.contracts.risk import (
    MarkQuality,
    RiskDecision,
    RiskPolicyVersion,
)

__all__ = [
    "AccountRiskState",
    "InstrumentMark",
    "ProposalKind",
    "RiskProposal",
    "buffered_reservation",
    "evaluate_proposal",
]

ProposalKind = Literal["ENTRY", "EXIT", "REDUCE", "PROTECTIVE"]

BPS = Decimal("10000")


class RiskProposal(BaseModel):
    """What a strategy (human or AI) wants to do. Not a contract: it is an
    internal input the policy disposes of, never a wire shape."""

    model_config = ConfigDict(extra="forbid")

    account_id: str
    deployment_id: str = "default"
    instrument_id: str
    product: ProductClass | None = None
    side: OrderSide
    kind: ProposalKind
    quantity: Decimal = Field(gt=0)
    reference_price: Decimal = Field(gt=0)
    currency: str
    orders_last_minute: int = 0
    entries_today: int = 0

    @property
    def is_entry(self) -> bool:
        return self.kind == "ENTRY"

    @property
    def notional(self) -> Decimal:
        return self.quantity * self.reference_price

    @property
    def increases_risk(self) -> bool:
        """ENTRY increases exposure; EXIT/REDUCE/PROTECTIVE reduce or cap it."""
        return self.kind == "ENTRY"


class InstrumentMark(BaseModel):
    """One instrument's last known mark for policy evaluation."""

    model_config = ConfigDict(extra="forbid")

    instrument_id: str
    price: Decimal = Field(gt=0)
    quality: MarkQuality = "STALE_CACHE"
    observed_at: datetime


class AccountRiskState(BaseModel):
    """Snapshot of the account state the policy evaluates against. Values are
    what the ADMISSION STORE reports — funds figures already net of active
    reservations, so the funds rule sees committed, not free-looking, cash."""

    model_config = ConfigDict(extra="forbid")

    cash_available: Decimal
    cash_reserved: Decimal = Decimal(0)
    gross_exposure: Decimal = Decimal(0)
    equity_reference: Decimal = Field(gt=0)
    instrument_exposure: Decimal = Decimal(0)
    instrument_position: Decimal = Decimal(0)
    instrument_mark: InstrumentMark | None = None
    deployment_gross_notional: Decimal = Decimal(0)
    daily_pnl: Decimal = Decimal(0)
    connected: bool = True
    reconciled_within_seconds: int | None = None

    @property
    def unreserved_cash(self) -> Decimal:
        return self.cash_available - self.cash_reserved


def buffered_reservation(policy: RiskPolicyVersion, notional: Decimal) -> Decimal:
    """Cash a notional requires once fee + slippage buffers are added."""
    c = policy.constraints
    bps = c.fee_buffer_bps + c.slippage_buffer_bps
    return (notional * (BPS + bps) / BPS).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class _Ctx:
    policy: RiskPolicyVersion
    proposal: RiskProposal
    state: AccountRiskState
    now: datetime


def evaluate_proposal(
    policy: RiskPolicyVersion,
    proposal: RiskProposal,
    state: AccountRiskState,
    *,
    now: datetime | None = None,
) -> RiskDecision:
    """Evaluate one proposal; the first rule that fires decides (frozen
    precedence). Pure: no I/O, no clocks beyond ``now``, no store access."""
    now = now or datetime.now(UTC)
    ctx = _Ctx(policy, proposal, state, now)
    for rule in (
        _permission,
        _stale_state,
        _account_controls_placeholder,
        _daily_loss,
        _rate_limit,
        _deployment_budget,
        _concentration,
        _gross_exposure,
        _max_order,
        _funds,
    ):
        decision = rule(ctx)
        if decision is not None:
            return decision
    return _approve(ctx, proposal.notional)


def _deny(ctx: _Ctx, rule: str, reason: str) -> RiskDecision:
    return RiskDecision(
        schema_version="1.0",
        decision="DENY",
        rule=rule,
        reason=reason,
        policy_revision=ctx.policy.policy_revision,
    )


def _clamp(ctx: _Ctx, rule: str, reason: str, approved: Decimal) -> RiskDecision:
    approved = approved.quantize(Decimal("0.01"))
    money = lambda amount: Money(  # noqa: E731 - local shorthand
        amount=format(amount, "f"), currency=ctx.policy.base_currency
    )
    return RiskDecision(
        schema_version="1.0",
        decision="CLAMP",
        rule=rule,
        reason=reason,
        policy_revision=ctx.policy.policy_revision,
        requested_notional=money(ctx.proposal.notional),
        approved_notional=money(approved),
        required_reservation=money(buffered_reservation(ctx.policy, approved)),
    )


def _approve(ctx: _Ctx, notional: Decimal) -> RiskDecision:
    value = Money(amount=format(notional, "f"), currency=ctx.policy.base_currency)
    reservation = Money(
        amount=format(buffered_reservation(ctx.policy, notional), "f"),
        currency=ctx.policy.base_currency,
    )
    return RiskDecision(
        schema_version="1.0",
        decision="APPROVE",
        policy_revision=ctx.policy.policy_revision,
        requested_notional=value,
        approved_notional=value,
        required_reservation=reservation,
    )


# -- precedence 1: instrument permission (stateless) -------------------------

def _permission(ctx: _Ctx) -> RiskDecision | None:
    for perm in ctx.policy.permissions:
        if perm.instrument_id == ctx.proposal.instrument_id:
            if not perm.permitted:
                return _deny(
                    ctx,
                    "instrument_permission",
                    f"instrument {ctx.proposal.instrument_id} is not permitted "
                    "on this account",
                )
            return None
    return None


# -- precedence 2: stale state (entries only) ---------------------------------

def _stale_state(ctx: _Ctx) -> RiskDecision | None:
    if not ctx.proposal.increases_risk:
        return None
    rules = ctx.policy.stale_state
    if rules.require_connected and not ctx.state.connected:
        return _deny(ctx, "stale_state", "account connection is down; new risk blocked")
    mark = ctx.state.instrument_mark
    if mark is None or mark.instrument_id != ctx.proposal.instrument_id:
        return _deny(
            ctx,
            "stale_state",
            f"no mark for {ctx.proposal.instrument_id}; new risk blocked",
        )
    if rules.accepted_mark_qualities and mark.quality not in rules.accepted_mark_qualities:
        return _deny(
            ctx,
            "stale_state",
            f"mark quality {mark.quality} not in {list(rules.accepted_mark_qualities)}",
        )
    age = (ctx.now - mark.observed_at).total_seconds()
    if age > rules.max_mark_age_seconds:
        return _deny(
            ctx,
            "stale_state",
            f"mark age {age:.0f}s exceeds max_mark_age_seconds "
            f"{rules.max_mark_age_seconds}",
        )
    if ctx.state.reconciled_within_seconds is not None:
        if ctx.state.reconciled_within_seconds > rules.max_mark_age_seconds:
            return _deny(
                ctx,
                "stale_state",
                f"reconciliation watermark is {ctx.state.reconciled_within_seconds}s old",
            )
    return None


def _account_controls_placeholder(ctx: _Ctx) -> RiskDecision | None:
    #: The admission service enforces live account controls (pause/reduce-only/
    #: flatten) because they are mutable operator state, not policy; the rule
    #: name is reserved here so decisions stay unambiguous.
    return None


# -- precedence 4: daily loss (entries only) ----------------------------------

def _daily_loss(ctx: _Ctx) -> RiskDecision | None:
    if not ctx.proposal.increases_risk:
        return None
    cap = ctx.policy.constraints.max_daily_loss
    if cap is None:
        return None
    loss = -ctx.state.daily_pnl
    if loss >= cap.amount:
        return _deny(
            ctx,
            "daily_loss",
            f"daily loss {loss} at/over cap {cap.amount}; entries blocked, "
            "risk-reducing actions remain possible",
        )
    return None


# -- precedence 5: rate limits (entries only) ---------------------------------

def _rate_limit(ctx: _Ctx) -> RiskDecision | None:
    if not ctx.proposal.increases_risk:
        return None
    limits = ctx.policy.constraints.rate_limits
    if limits is None:
        return None
    if ctx.proposal.orders_last_minute >= limits.max_orders_per_minute:
        return _deny(
            ctx,
            "rate_limit",
            f"{ctx.proposal.orders_last_minute} orders in the last minute "
            f">= cap {limits.max_orders_per_minute}",
        )
    if ctx.proposal.entries_today >= limits.max_entries_per_day:
        return _deny(
            ctx,
            "rate_limit",
            f"{ctx.proposal.entries_today} entries today "
            f">= cap {limits.max_entries_per_day}",
        )
    return None


# -- precedence 6: deployment budget (entries only) ---------------------------

def _deployment_budget(ctx: _Ctx) -> RiskDecision | None:
    if not ctx.proposal.increases_risk:
        return None
    for budget in ctx.policy.deployment_budgets:
        if budget.deployment_id != ctx.proposal.deployment_id:
            continue
        if budget.max_daily_loss is not None:
            loss = -ctx.state.daily_pnl
            if loss >= budget.max_daily_loss.amount:
                return _deny(
                    ctx,
                    "deployment_budget",
                    f"deployment {ctx.proposal.deployment_id} daily loss {loss} "
                    f"at/over its cap {budget.max_daily_loss.amount}",
                )
        if budget.max_gross_notional is not None:
            headroom = budget.max_gross_notional.amount - ctx.state.deployment_gross_notional
            if headroom <= 0:
                return _deny(
                    ctx,
                    "deployment_budget",
                    f"deployment {ctx.proposal.deployment_id} gross notional cap "
                    f"{budget.max_gross_notional.amount} exhausted",
                )
            if ctx.proposal.notional > headroom:
                return _clamp(
                    ctx,
                    "deployment_budget",
                    f"deployment {ctx.proposal.deployment_id} notional clamped to "
                    f"remaining budget headroom {headroom}",
                    headroom,
                )
    return None


# -- precedence 7: concentration (entries only) -------------------------------

def _concentration(ctx: _Ctx) -> RiskDecision | None:
    if not ctx.proposal.increases_risk:
        return None
    for limit in ctx.policy.constraints.max_concentration:
        if limit.instrument_id is not None and limit.instrument_id != ctx.proposal.instrument_id:
            continue
        allowed_value = ctx.state.equity_reference * limit.max_percent_of_equity / Decimal(100)
        headroom = allowed_value - ctx.state.instrument_exposure
        if headroom <= 0:
            return _deny(
                ctx,
                "max_concentration",
                f"instrument {ctx.proposal.instrument_id} at concentration cap "
                f"({ctx.state.instrument_exposure} of allowed {allowed_value})",
            )
        if ctx.proposal.notional > headroom:
            return _clamp(
                ctx,
                "max_concentration",
                f"instrument {ctx.proposal.instrument_id} notional clamped to "
                f"concentration headroom {headroom}",
                headroom,
            )
    return None


# -- precedence 8: gross exposure (entries only) -------------------------------

def _gross_exposure(ctx: _Ctx) -> RiskDecision | None:
    if not ctx.proposal.increases_risk:
        return None
    cap = ctx.policy.constraints.max_gross_exposure
    if cap is None:
        return None
    headroom = cap.amount - ctx.state.gross_exposure
    if headroom <= 0:
        return _deny(
            ctx,
            "max_gross_exposure",
            f"account gross exposure {ctx.state.gross_exposure} at cap {cap.amount}",
        )
    if ctx.proposal.notional > headroom:
        return _clamp(
            ctx,
            "max_gross_exposure",
            f"notional clamped to gross-exposure headroom {headroom}",
            headroom,
        )
    return None


# -- precedence 9: max order notional (entries only) ---------------------------

def _max_order(ctx: _Ctx) -> RiskDecision | None:
    if not ctx.proposal.increases_risk:
        return None
    cap = ctx.policy.constraints.max_order_notional
    if cap is not None and ctx.proposal.notional > cap.amount:
        return _clamp(
            ctx,
            "max_order_notional",
            f"order notional {ctx.proposal.notional} clamped to policy cap "
            f"{cap.amount}",
            cap.amount,
        )
    return None


# -- precedence 10: funds (entries only) ---------------------------------------

def _funds(ctx: _Ctx) -> RiskDecision | None:
    if not ctx.proposal.increases_risk:
        return None
    required = buffered_reservation(ctx.policy, ctx.proposal.notional)
    unreserved = ctx.state.unreserved_cash
    if required > unreserved:
        return _deny(
            ctx,
            "insufficient_funds",
            f"required reservation {required} (with buffers) exceeds unreserved "
            f"cash {unreserved}; active reservations retain their obligations",
        )
    return None


def mark_age(mark: InstrumentMark, now: datetime) -> timedelta:
    return now - mark.observed_at
