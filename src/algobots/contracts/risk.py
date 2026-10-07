"""Account risk policy contracts (A08, resource ``execution-contract``).

``RiskPolicyVersion`` is the versioned, immutable policy document an account
admits against: budgets, hard constraints, instrument permissions and
stale-state rules, with a FROZEN evaluation precedence. ``RiskDecision`` is
the deterministic outcome of evaluating one proposal against one policy —
approve, clamp (with the clamped size), or deny (with the rule that fired).

Money rails never get silent defaults: every cap the operator wants enforced
must be present in the policy; absent means unconstrained, and the decision
says which rule fired.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import Field, model_validator

from . import registry
from .base import ContractModel, DecimalStr, Identifier, Money, UtcDatetime, VersionedContract
from .enums import ProductClass

__all__ = [
    "ConcentrationLimit",
    "DeploymentBudget",
    "InstrumentPermission",
    "MarkQuality",
    "PolicyConstraints",
    "RateLimits",
    "RiskDecision",
    "RiskPolicyVersion",
    "StaleStateRules",
]


MarkQuality = Literal["REALTIME", "DELAYED", "STALE_CACHE", "INDICATIVE"]

#: Deterministic evaluation order (frozen): first rule that fires wins and is
#: the ONLY rule reported. Denials come before clamps; cheap denials that need
#: no state come first so a decision can never depend on evaluation order
#: beyond this list.
RISK_RULE_PRECEDENCE: tuple[str, ...] = (
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


class InstrumentPermission(ContractModel):
    """One instrument's permission. ``permitted=False`` is an explicit ban."""

    instrument_id: Identifier
    product: ProductClass | None = None
    permitted: bool = True

    @model_validator(mode="after")
    def _key(self) -> InstrumentPermission:
        if not self.permitted and self.product is not None:
            raise ValueError("a ban may not widen into a product-wide statement")
        return self


class DeploymentBudget(ContractModel):
    """Caps scoped to one deployment on the account."""

    deployment_id: Identifier
    max_gross_notional: Money | None = None
    max_daily_loss: Money | None = None


class ConcentrationLimit(ContractModel):
    """Cap on one instrument's share of account equity."""

    instrument_id: Identifier | None = None  # None = every instrument
    max_percent_of_equity: DecimalStr = Field(gt=0, le=100)


class RateLimits(ContractModel):
    """Order-rate caps per account (deterministic sliding windows)."""

    max_orders_per_minute: int = Field(gt=0)
    max_entries_per_day: int = Field(gt=0)


class StaleStateRules(ContractModel):
    """How fresh account state must be before NEW risk is admitted.

    Risk-reducing actions are exempt from the stale-state denial (an exit must
    never be hostage to a market-data outage) but protective-order validation
    still applies venue constraints.
    """

    max_mark_age_seconds: int = Field(ge=0)
    accepted_mark_qualities: tuple[MarkQuality, ...] = ()
    require_connected: bool = True


class PolicyConstraints(ContractModel):
    """Hard money/rate constraints. Absent means unconstrained (explicitly)."""

    max_order_notional: Money | None = None
    max_gross_exposure: Money | None = None
    max_concentration: tuple[ConcentrationLimit, ...] = ()
    max_daily_loss: Money | None = None
    rate_limits: RateLimits | None = None
    #: Buffer headroom required on every cash reservation: fee bps and
    #: slippage bps of the reserved notional (admission adds both).
    fee_buffer_bps: DecimalStr = Field(default="0", ge=0)
    slippage_buffer_bps: DecimalStr = Field(default="0", ge=0)


@registry.register
class RiskPolicyVersion(VersionedContract):
    """An immutable, revisioned account risk policy."""

    contract_name: ClassVar[str] = "RiskPolicyVersion"
    contract_version: ClassVar[str] = "1.0"

    policy_revision: Identifier
    account_id: Identifier
    base_currency: Annotated[str, Field(pattern=r"^[A-Z0-9]{3,10}$")]
    timezone: str  # IANA name; the daily-loss trading day boundary
    permissions: tuple[InstrumentPermission, ...] = ()
    deployment_budgets: tuple[DeploymentBudget, ...] = ()
    constraints: PolicyConstraints
    stale_state: StaleStateRules
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _unique_and_currency(self) -> RiskPolicyVersion:
        seen: set[str] = set()
        for perm in self.permissions:
            if perm.instrument_id in seen:
                raise ValueError(f"duplicate permission for {perm.instrument_id}")
            seen.add(perm.instrument_id)
        budgets = [b.deployment_id for b in self.deployment_budgets]
        if len(set(budgets)) != len(budgets):
            raise ValueError("duplicate deployment budget")
        instruments = [b for b in self.deployment_budgets if b.max_gross_notional is not None]
        for budget in instruments:
            if budget.max_gross_notional.currency != self.base_currency:
                raise ValueError("deployment budgets must be in the base currency")
        money_caps = (
            self.constraints.max_order_notional,
            self.constraints.max_gross_exposure,
            self.constraints.max_daily_loss,
        )
        for cap in money_caps:
            if cap is not None and cap.currency != self.base_currency:
                raise ValueError("constraint caps must be in the base currency")
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown IANA timezone {self.timezone!r}") from exc
        return self


@registry.register
class RiskDecision(VersionedContract):
    """Outcome of evaluating one proposal: APPROVE / CLAMP / DENY.

    ``rule`` names the FIRST rule that fired per :data:`RISK_RULE_PRECEDENCE`
    (empty on a clean approve). ``reason`` is the explicit audit reason — a
    clamp or denial without a reason cannot be constructed.
    """

    contract_name: ClassVar[str] = "RiskDecision"
    contract_version: ClassVar[str] = "1.0"

    decision: Literal["APPROVE", "CLAMP", "DENY"]
    rule: str = ""
    reason: str = ""
    policy_revision: Identifier
    requested_notional: Money | None = None
    approved_notional: Money | None = None
    #: Cash the account must reserve for the approved size (amount + buffers).
    required_reservation: Money | None = None

    @model_validator(mode="after")
    def _explainable(self) -> RiskDecision:
        if self.decision == "APPROVE":
            if self.rule or self.reason:
                raise ValueError("a clean approve carries no rule or reason")
        elif not self.rule or not self.reason:
            raise ValueError(f"{self.decision} must name the rule and carry a reason")
        if self.decision == "CLAMP":
            for attr in ("requested_notional", "approved_notional", "required_reservation"):
                if getattr(self, attr) is None:
                    raise ValueError(f"CLAMP requires {attr}")
            if self.approved_notional.amount <= 0:
                raise ValueError("a clamp must approve a positive size")
            if self.approved_notional.amount >= self.requested_notional.amount:
                raise ValueError("a clamp must shrink the requested size")
        if self.decision == "DENY" and self.approved_notional is not None:
            raise ValueError("a denial approves nothing")
        return self
