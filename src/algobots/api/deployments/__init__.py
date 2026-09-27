"""Frozen strategy deployments (S4.2 — ALG-3091): (strategy x symbol x account)
with freeze-at-deploy semantics, per-deployment risk envelopes, and
fleet-level breakers.

Public surface:
- `models` — `Deployment` (frozen spec + envelope + breaker) / `FleetBreaker`
- `schemas` — create/read/list + risk-report + breaker payloads
- `service` — freeze/dedupe/breaker domain logic (structured events)
- `router` — tenant-scoped `/api/deployments` routes
"""

from algobots.api.deployments.models import BreakerState, Deployment, DeploymentStatus, FleetBreaker
from algobots.api.deployments.schemas import (
    DailyLossReport,
    DailyLossReportOut,
    DeploymentCreate,
    DeploymentOut,
    DeploymentUpdate,
    FleetBreakerAction,
    FleetBreakerOut,
)

__all__ = [
    "BreakerState",
    "DailyLossReport",
    "DailyLossReportOut",
    "Deployment",
    "DeploymentCreate",
    "DeploymentOut",
    "DeploymentStatus",
    "DeploymentUpdate",
    "FleetBreaker",
    "FleetBreakerAction",
    "FleetBreakerOut",
]
