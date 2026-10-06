"""Strategy version and deployment contracts (roadmap §3).

The executable rule language lives in :mod:`algobots.strategies.dsl`; these
contracts reference rules by content hash and never embed code.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import Field, model_validator

from . import registry
from .base import ContractModel, DecimalStr, Identifier, Money, Sha256Hex, VersionedContract
from .enums import AuthorityMode, EvidenceClass

__all__ = ["Deployment", "StrategyParameter", "StrategyVersion"]


class StrategyParameter(ContractModel):
    name: Identifier
    value: DecimalStr
    unit: Annotated[str, Field(min_length=1, max_length=16)]
    minimum: DecimalStr
    maximum: DecimalStr

    @model_validator(mode="after")
    def _in_range(self) -> StrategyParameter:
        if not self.minimum <= self.value <= self.maximum:
            raise ValueError(
                f"parameter {self.name}={self.value} outside [{self.minimum}, {self.maximum}]"
            )
        return self


@registry.register
class StrategyVersion(VersionedContract):
    """An immutable strategy revision, identified by version and content hash."""

    contract_name: ClassVar[str] = "StrategyVersion"
    contract_version: ClassVar[str] = "1.0"

    strategy_id: Identifier
    version: Annotated[int, Field(ge=1)]
    content_hash: Sha256Hex
    artifact_hash: Sha256Hex
    rule_schema_version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    approved_operators: tuple[Identifier, ...]
    parameters: tuple[StrategyParameter, ...]
    instrument_constraints: tuple[Identifier, ...]
    feature_dependencies: tuple[Identifier, ...]
    cadence: Annotated[str, Field(pattern=r"^\d+(s|m|h|d|w)$")]
    freshness_limit_seconds: Annotated[int, Field(gt=0)]
    entry_rule_hash: Sha256Hex
    exit_rule_hash: Sha256Hex
    semantic_filters: tuple[Identifier, ...] = ()
    evidence_ids: tuple[Identifier, ...] = ()
    evidence_class: EvidenceClass
    verification_status: Literal["UNVERIFIED", "SCHEMA_VALID", "SEMANTIC_VALID", "REJECTED"]

    @model_validator(mode="after")
    def _unique_parameters(self) -> StrategyVersion:
        names = [p.name for p in self.parameters]
        if len(set(names)) != len(names):
            raise ValueError("duplicate strategy parameter names")
        return self


@registry.register
class Deployment(VersionedContract):
    """Binds one immutable strategy version to one account and its owned positions."""

    contract_name: ClassVar[str] = "Deployment"
    contract_version: ClassVar[str] = "1.0"

    deployment_id: Identifier
    tenant_id: Identifier
    account_id: Identifier
    strategy_id: Identifier
    strategy_version: Annotated[int, Field(ge=1)]
    strategy_content_hash: Sha256Hex
    universe: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    parameter_snapshot_hash: Sha256Hex
    capital_budget: Money
    risk_policy_revision: Identifier
    authority_mode: AuthorityMode
    worker_generation: Annotated[int, Field(ge=0)]
    owned_position_ids: tuple[Identifier, ...] = ()
