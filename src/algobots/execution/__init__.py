"""algobots.execution — dry-run order planning + execution discipline.

Public surface:

- ``planner``:    TargetWeights + current holdings → OrderPlan
                  (``plan_orders``); sell-to-zero, market-closed
                  plan-only policy, serializable artifacts
- ``governor``:   turnover governor that scales down and never rejects
                  (``TurnoverGovernor``)
- ``discipline``: jev-trade mechanics port (``ExecutionDiscipline``,
                  ``OrderInstruction``)
- ``quantity``:   shared quantity precision + Decimal coercion
- ``ledger``:     A07 durable intent ledger — intent → plan → reservation →
                  command route with dedup, outbox, order state machine and
                  exactly-once fill settlement (execution-contract resource)
"""

from algobots.execution.discipline import ExecutionDiscipline, OrderInstruction
from algobots.execution.governor import GovernorResult, TurnoverGovernor
from algobots.execution.ledger import (
    AmbiguousSubmit,
    commit_intent,
    dispatch_pending,
    get_intent,
    replay_outbox,
    stage_commands,
)
from algobots.execution.planner import (
    AccountState,
    ClampAnnotation,
    DisciplineAnnotations,
    GatedOut,
    MarketState,
    OrderPlan,
    PlannedOrder,
    PlannerConfig,
    Position,
    plan_orders,
)

__all__ = [
    "AccountState",
    "AmbiguousSubmit",
    "ClampAnnotation",
    "DisciplineAnnotations",
    "ExecutionDiscipline",
    "GatedOut",
    "GovernorResult",
    "MarketState",
    "OrderInstruction",
    "OrderPlan",
    "PlannedOrder",
    "PlannerConfig",
    "Position",
    "TurnoverGovernor",
    "commit_intent",
    "dispatch_pending",
    "get_intent",
    "plan_orders",
    "replay_outbox",
    "stage_commands",
]
