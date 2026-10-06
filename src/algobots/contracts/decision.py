"""Decision and portfolio contracts (roadmap §4).

Provider-specific serialization belongs to adapters; these are the platform
shapes. A confidence value is never invented: it stays ``None`` when the
provider does not supply one.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, ClassVar, Literal

from pydantic import Field, model_validator

from . import registry
from .base import (
    BoundedScore,
    ContractModel,
    DecimalStr,
    Identifier,
    Money,
    Probability,
    Quantity,
    Sha256Hex,
    UtcDatetime,
    VersionedContract,
)

__all__ = [
    "Answer",
    "DecisionRequest",
    "DecisionResponse",
    "DecisionStatus",
    "EvidenceExcerpt",
    "EvidencePacket",
    "Signal",
    "SignalDirection",
    "SourceVersion",
    "TargetEntry",
    "TargetPortfolio",
    "Usage",
]


class SourceVersion(ContractModel):
    source_id: Identifier
    version: Identifier
    content_hash: Sha256Hex


class EvidenceExcerpt(ContractModel):
    """Source text is data, never instructions."""

    anchor: Identifier
    stance: Literal["supporting", "contradicting", "neutral"]
    text: Annotated[str, Field(min_length=1, max_length=4000)]


@registry.register
class EvidencePacket(VersionedContract):
    contract_name: ClassVar[str] = "EvidencePacket"
    contract_version: ClassVar[str] = "1.0"

    packet_id: Identifier
    tenant_id: Identifier
    acl_revision: Annotated[int, Field(ge=0)]
    query_hash: Sha256Hex
    as_of: UtcDatetime
    available_at_cutoff: UtcDatetime
    sources: tuple[SourceVersion, ...]
    excerpts: tuple[EvidenceExcerpt, ...]
    missing_data: tuple[str, ...] = ()
    token_budget: Annotated[int, Field(gt=0)]
    tokens_used: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _point_in_time(self) -> EvidencePacket:
        if self.available_at_cutoff > self.as_of:
            raise ValueError("available_at_cutoff cannot be later than as_of (future leakage)")
        if self.tokens_used > self.token_budget:
            raise ValueError("tokens_used exceeds token_budget")
        return self


@registry.register
class DecisionRequest(VersionedContract):
    contract_name: ClassVar[str] = "DecisionRequest"
    contract_version: ClassVar[str] = "1.0"

    request_id: Identifier
    tenant_id: Identifier
    state_snapshot_hash: Sha256Hex
    instrument_id: Identifier
    horizon: Annotated[str, Field(pattern=r"^\d+(m|h|d|w)$")]
    question_set_revision: Identifier
    provider: Identifier
    model_revision: Identifier
    deadline: UtcDatetime
    max_budget: Money
    evidence_packet_id: Identifier
    output_schema_version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]


class DecisionStatus(StrEnum):
    VALID = "VALID"
    ABSTAIN = "ABSTAIN"
    REVIEW = "REVIEW"
    EXPIRED = "EXPIRED"
    UNAVAILABLE = "UNAVAILABLE"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


class Answer(ContractModel):
    question_id: Identifier
    value: Annotated[str, Field(min_length=1, max_length=256)]
    probability: Probability | None = None


class Usage(ContractModel):
    """Estimated and billed units stay distinct."""

    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    estimated_cost: Money | None = None
    billed_cost: Money | None = None


@registry.register
class DecisionResponse(VersionedContract):
    contract_name: ClassVar[str] = "DecisionResponse"
    contract_version: ClassVar[str] = "1.0"

    request_id: Identifier
    status: DecisionStatus
    answers: tuple[Answer, ...] = ()
    confidence: Probability | None = None
    source_refs: tuple[Identifier, ...] = ()
    provider: Identifier
    model_revision: Identifier
    usage: Usage
    started_at: UtcDatetime
    completed_at: UtcDatetime
    receipt_ref: Identifier

    @model_validator(mode="after")
    def _status_consistency(self) -> DecisionResponse:
        if self.status is DecisionStatus.VALID and not self.answers:
            raise ValueError("a VALID decision requires typed answers")
        if self.status is not DecisionStatus.VALID and (
            self.answers or self.confidence is not None
        ):
            raise ValueError(f"a {self.status} decision carries no answers or confidence")
        if self.completed_at < self.started_at:
            raise ValueError("completed_at precedes started_at")
        return self


class SignalDirection(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNSPECIFIED = "unspecified"


@registry.register
class Signal(VersionedContract):
    """A score is an input feature, not permission or an allocation percentage."""

    contract_name: ClassVar[str] = "Signal"
    contract_version: ClassVar[str] = "1.0"

    signal_id: Identifier
    instrument_id: Identifier
    direction: SignalDirection
    score: BoundedScore | None = None
    abstained: bool
    reason_codes: tuple[Identifier, ...] = ()
    as_of: UtcDatetime
    valid_until: UtcDatetime
    horizon: Annotated[str, Field(pattern=r"^\d+(m|h|d|w)$")]
    strategy_id: Identifier
    strategy_version: Annotated[int, Field(ge=1)]
    evidence_refs: tuple[Identifier, ...] = ()
    decision_refs: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def _abstain_is_not_a_target(self) -> Signal:
        if self.abstained and (
            self.direction is not SignalDirection.UNSPECIFIED or self.score is not None
        ):
            raise ValueError("an abstained signal has direction 'unspecified' and no score")
        if self.valid_until <= self.as_of:
            raise ValueError("valid_until must be after as_of")
        return self


class TargetEntry(ContractModel):
    """Exactly one of ``weight`` (fraction of allocated capital) or ``quantity``."""

    instrument_id: Identifier
    weight: DecimalStr | None = None
    quantity: Quantity | None = None

    @model_validator(mode="after")
    def _one_target(self) -> TargetEntry:
        if (self.weight is None) == (self.quantity is None):
            raise ValueError(f"{self.instrument_id}: set exactly one of weight or quantity")
        return self


@registry.register
class TargetPortfolio(VersionedContract):
    """PARTIAL leaves omitted instruments unchanged; FULL_OWNED_SCOPE zeroes them
    only inside the deployment's owned scope. Manual positions never liquidate by omission.
    """

    contract_name: ClassVar[str] = "TargetPortfolio"
    contract_version: ClassVar[str] = "1.0"

    portfolio_id: Identifier
    account_id: Identifier
    deployment_id: Identifier
    snapshot_version: Annotated[int, Field(ge=0)]
    update_mode: Literal["FULL_OWNED_SCOPE", "PARTIAL"]
    entries: tuple[TargetEntry, ...]
    cash_policy: Literal["RESIDUAL_CASH"]
    long_only_unlevered: bool = True
    as_of: UtcDatetime
    expires_at: UtcDatetime
    source_signal_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def _weights(self) -> TargetPortfolio:
        ids = [e.instrument_id for e in self.entries]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate instrument in target entries")
        if self.expires_at <= self.as_of:
            raise ValueError("expires_at must be after as_of")
        if self.long_only_unlevered:
            weights = [e.weight for e in self.entries if e.weight is not None]
            if any(w < 0 for w in weights):
                raise ValueError("long-only targets require weights >= 0")
            total = sum(weights, Decimal(0))
            if total > 1:
                raise ValueError(f"long-only unlevered weights sum to {total} > 1")
        return self
