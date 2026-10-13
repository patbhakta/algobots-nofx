"""algobots.risk — the hard rail between conviction and money.

Public surface:

- ``limits``:     vendored ai-hedge-fund weight clamps (``RiskLimits``,
                  ``apply_limits``, ``ClampEvent``, ``RiskResult``)
- ``envelopes``:  per-deployment money caps (``RiskEnvelope``)
- ``breakers``:   Fincept manual Algo §19 rate breakers with privileged
                  exits (``RateBreakers``, ``BreakerConfig``)
- ``audit``:      ``ClampEventRow`` + sinks + ``RiskGate`` wiring — every
                  firing writes exactly one audit row
- ``policy``:     A08 deterministic account policy evaluation against
                  ``RiskPolicyVersion`` (``evaluate_proposal``)
- ``daily``:      A08 daily loss with account timezone, equity reference,
                  realized/unrealized components and transfer adjustments
- ``controls``:   A08 account controls (pause entries / cancel entries /
                  reduce-only / separately authorized flatten) and
                  protective-order validation
"""

from algobots.risk.audit import (
    ClampEventRow,
    ClampEventSink,
    InMemorySink,
    JsonlSink,
    OrderDecision,
    RiskGate,
    row_from_clamp,
)
from algobots.risk.breakers import (
    BreakerConfig,
    BreakerDecision,
    OrderKind,
    RateBreakers,
)
from algobots.risk.controls import (
    AccountControls,
    ControlAction,
    ProtectionOrder,
    ProtectionStatus,
    check_action,
    protection_status,
    validate_protective_order,
)
from algobots.risk.daily import (
    DailyLossInput,
    DailyLossReport,
    MarkedPosition,
    daily_loss_report,
    trading_day_bounds,
)
from algobots.risk.envelopes import (
    DailyLossCheck,
    OrderValueCheck,
    RiskEnvelope,
)
from algobots.risk.limits import (
    ClampEvent,
    RiskLimits,
    RiskResult,
    apply_limits,
)
from algobots.risk.policy import (
    AccountRiskState,
    InstrumentMark,
    RiskProposal,
    buffered_reservation,
    evaluate_proposal,
)

__all__ = [
    "AccountControls",
    "AccountRiskState",
    "BreakerConfig",
    "BreakerDecision",
    "ClampEvent",
    "ClampEventRow",
    "ClampEventSink",
    "ControlAction",
    "DailyLossCheck",
    "DailyLossInput",
    "DailyLossReport",
    "InMemorySink",
    "InstrumentMark",
    "JsonlSink",
    "MarkedPosition",
    "OrderDecision",
    "OrderValueCheck",
    "OrderKind",
    "ProtectionOrder",
    "ProtectionStatus",
    "RateBreakers",
    "RiskEnvelope",
    "RiskGate",
    "RiskLimits",
    "RiskProposal",
    "RiskResult",
    "apply_limits",
    "buffered_reservation",
    "check_action",
    "daily_loss_report",
    "evaluate_proposal",
    "protection_status",
    "row_from_clamp",
    "trading_day_bounds",
    "validate_protective_order",
]
