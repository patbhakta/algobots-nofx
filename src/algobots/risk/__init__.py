"""algobots.risk — the hard rail between conviction and money.

Public surface:

- ``limits``:     vendored ai-hedge-fund weight clamps (``RiskLimits``,
                  ``apply_limits``, ``ClampEvent``, ``RiskResult``)
- ``envelopes``:  per-deployment money caps (``RiskEnvelope``)
- ``breakers``:   Fincept manual Algo §19 rate breakers with privileged
                  exits (``RateBreakers``, ``BreakerConfig``)
- ``audit``:      ``ClampEventRow`` + sinks + ``RiskGate`` wiring — every
                  firing writes exactly one audit row
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

__all__ = [
    "BreakerConfig",
    "BreakerDecision",
    "ClampEvent",
    "ClampEventRow",
    "ClampEventSink",
    "DailyLossCheck",
    "InMemorySink",
    "JsonlSink",
    "OrderDecision",
    "OrderKind",
    "OrderValueCheck",
    "RateBreakers",
    "RiskEnvelope",
    "RiskGate",
    "RiskLimits",
    "RiskResult",
    "apply_limits",
    "row_from_clamp",
]
