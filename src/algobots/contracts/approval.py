"""Approval envelope (roadmap §5). Dispatch revalidates; exceeding bounds needs a new plan."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, ClassVar, Literal

from pydantic import Field, model_validator

from . import registry
from .base import DecimalStr, Identifier, Money, Quantity, Sha256Hex, UtcDatetime, VersionedContract
from .enums import IntentAction, ProductClass
from .plan import OrderPlan

__all__ = ["ApprovalEnvelope"]


@registry.register
class ApprovalEnvelope(VersionedContract):
    contract_name: ClassVar[str] = "ApprovalEnvelope"
    contract_version: ClassVar[str] = "1.0"

    approval_id: Identifier
    approver_id: Identifier
    approver_kind: Literal["USER", "SERVICE"]
    grant_revision: Annotated[int, Field(ge=0)]
    plan_hash: Sha256Hex
    permitted_account_ids: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    permitted_products: Annotated[tuple[ProductClass, ...], Field(min_length=1)]
    permitted_actions: Annotated[tuple[IntentAction, ...], Field(min_length=1)]
    max_quantity: Quantity
    max_notional: Money
    price_tolerance_bps: DecimalStr
    policy_revision: Identifier
    expires_at: UtcDatetime
    required_approvals: Annotated[int, Field(ge=1)]
    approvals_received: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _bounds(self) -> ApprovalEnvelope:
        if self.max_quantity.value <= 0 or self.max_notional.amount <= 0:
            raise ValueError("approval maxima must be > 0")
        if self.price_tolerance_bps < 0:
            raise ValueError("price_tolerance_bps must be >= 0")
        return self

    def violations(self, plan: OrderPlan, now: datetime) -> list[str]:
        """Reasons this approval does not cover ``plan`` at ``now`` (empty = covered)."""
        reasons: list[str] = []
        if plan.content_hash() != plan.plan_hash:
            reasons.append("plan content does not match its plan_hash")
        if plan.plan_hash != self.plan_hash:
            reasons.append("plan hash differs from the approved hash")
        if now >= self.expires_at:
            reasons.append("approval expired")
        if self.approvals_received < self.required_approvals:
            reasons.append(
                f"{self.approvals_received}/{self.required_approvals} approvals received"
            )
        if plan.account_id not in self.permitted_account_ids:
            reasons.append(f"account {plan.account_id} not permitted")
        if plan.action not in self.permitted_actions:
            reasons.append(f"action {plan.action} not permitted")
        for child in plan.children:
            if child.product not in self.permitted_products:
                reasons.append(f"{child.child_id}: product {child.product} not permitted")
            if child.quantity.unit != self.max_quantity.unit:
                reasons.append(
                    f"{child.child_id}: quantity unit {child.quantity.unit} not approved"
                )
            elif child.quantity.value > self.max_quantity.value:
                reasons.append(f"{child.child_id}: quantity exceeds approved maximum")
            if child.max_notional.currency != self.max_notional.currency:
                reasons.append(f"{child.child_id}: notional currency not approved")
            elif child.max_notional.amount > self.max_notional.amount:
                reasons.append(f"{child.child_id}: notional exceeds approved maximum")
        return reasons
