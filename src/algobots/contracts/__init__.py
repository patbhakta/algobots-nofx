"""Shared typed contracts (DTOs, enums, event schemas) exchanged between engine components.

Frozen by packet A01. Every top-level contract is registered in
:mod:`algobots.contracts.registry` as ``name@version`` and fingerprinted in
``schema-lock.json``; see that module for the revision rules.
"""

from . import registry
from .account import BrokerAccount, Capabilities, CapabilityEntry
from .approval import ApprovalEnvelope
from .base import ContractModel, Money, Quantity, VersionedContract
from .decision import DecisionRequest, DecisionResponse, EvidencePacket, Signal, TargetPortfolio
from .envelope import Envelope
from .events import FillEvent, OrderEvent
from .identity import Grant, IdentityKind, Principal
from .memory import MemoryRecord, MemoryScope, MemoryStore, namespace_permits
from .outbox import ChildOrderStatusView, IntentStatusResponse, OutboxEvent
from .plan import ExecutionCommand, IntentRequest, OrderPlan, Reservation, canonical_hash
from .risk import RiskDecision, RiskPolicyVersion
from .strategy import Deployment, StrategyVersion

__all__ = [
    "ApprovalEnvelope",
    "BrokerAccount",
    "Capabilities",
    "CapabilityEntry",
    "ChildOrderStatusView",
    "ContractModel",
    "DecisionRequest",
    "DecisionResponse",
    "Deployment",
    "Envelope",
    "EvidencePacket",
    "ExecutionCommand",
    "FillEvent",
    "Grant",
    "IdentityKind",
    "IntentRequest",
    "IntentStatusResponse",
    "MemoryRecord",
    "MemoryScope",
    "MemoryStore",
    "Money",
    "OrderEvent",
    "OrderPlan",
    "OutboxEvent",
    "Principal",
    "Quantity",
    "Reservation",
    "RiskDecision",
    "RiskPolicyVersion",
    "Signal",
    "StrategyVersion",
    "TargetPortfolio",
    "VersionedContract",
    "canonical_hash",
    "namespace_permits",
    "registry",
]
