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
"""

from algobots.execution.discipline import ExecutionDiscipline, OrderInstruction
from algobots.execution.governor import GovernorResult, TurnoverGovernor
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
    "plan_orders",
]
