"""Process ownership for frozen Studio deployments (paper only).

This is the lifecycle component, not an order generator. A caller supplies
fresh deployment/account/fleet rows on every reconciliation. The production
adapter must run in the rc6 node image and hold a singleton lease; importing
this module in the API does not import Nautilus or start a process.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select

from algobots.api.deployments.models import Deployment, FleetBreaker
from algobots.api.deployments.service import effective_state
from algobots.api.models import Account
from algobots.strategies.studio import compile_studio_strategy, parse_draft


def node_identity(deployment_id: Any) -> tuple[str, str]:
    """``(node, venue)`` for one deployment; the gateway registers the same pair."""
    tag = UUID(str(deployment_id)).hex
    return f"deployment-{tag}", f"DEP{tag.upper()}"


def deployment_rows_statement() -> Any:
    """Every deployment with its account and (tenant, user) fleet breaker."""
    return (
        select(Deployment, Account, FleetBreaker)
        .join(Account, Account.id == Deployment.account_id)
        .outerjoin(
            FleetBreaker,
            and_(
                FleetBreaker.tenant_id == Account.tenant_id,
                FleetBreaker.user_id == Deployment.user_id,
            ),
        )
    )


@dataclass(frozen=True)
class LaunchSpec:
    deployment_id: str
    node: str
    environment: dict[str, str]


def launch_spec(deployment: Any, account: Any) -> LaunchSpec:
    """Validate a frozen snapshot; never fetch the editable Strategy row."""
    if account.id != deployment.account_id or account.user_id != deployment.user_id:
        raise ValueError("deployment account ownership mismatch")
    if account.mode != "paper" or account.status != "active":
        raise ValueError("only active paper accounts can execute deployments")
    if account.approval_mode != "auto":
        raise ValueError("semi-auto accounts require the approval dispatch path")
    frozen = deployment.frozen_spec
    artifact = frozen.get("artifact") or {}
    if (
        frozen.get("kind") != "studio-artifact"
        or artifact.get("implementation") != "kalshi_momentum.v1"
    ):
        raise ValueError("runtime supports kalshi_momentum.v1 Studio artifacts only")
    # Recompile the canonical source and compare the execution-bearing fields.
    # Checking only the recorded hash would allow tampering with min_edge/risk.
    try:
        expected = compile_studio_strategy(
            parse_draft(json.loads(artifact["canonical_draft"]))
        ).model_dump(mode="json")
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("invalid frozen artifact") from exc
    for key in ("artifact_hash", "compiler_version", "implementation", "nautilus", "spec"):
        if artifact.get(key) != expected.get(key):
            raise ValueError(f"frozen artifact mismatch: {key}")
    digest = expected["artifact_hash"]
    if deployment.artifact_hash != digest:
        raise ValueError("deployment artifact hash mismatch")
    evidence = frozen.get("studio_evidence") or {}
    if evidence.get("artifact_hash") != digest:
        raise ValueError("frozen evidence does not identify this artifact")
    instruments = expected["nautilus"]["instrument_ids"]
    if instruments != ["KXBTC15M.KALSHI"] or deployment.symbol != "KXBTC15M":
        raise ValueError("runtime only supports KXBTC15M")
    for value in (deployment.max_order_value, deployment.max_daily_loss):
        from decimal import Decimal

        cap = Decimal(value)
        if not cap.is_finite() or cap <= 0:
            raise ValueError("deployment risk caps must be positive and finite")
    node, venue = node_identity(deployment.id)
    snapshot = {
        "deployment_id": str(deployment.id),
        "account_id": str(account.id),
        "artifact": artifact,
        "studio_evidence": evidence,
        "max_order_value": deployment.max_order_value,
        "max_daily_loss": deployment.max_daily_loss,
    }
    return LaunchSpec(
        str(deployment.id),
        node,
        {
            "ALGOBOTS_NODE": node,
            "ALGOBOTS_NODE_VENUE": venue,
            "ALGOBOTS_NODE_ACCOUNT": f"{venue}-001",
            "ALGOBOTS_NODE_SYMBOL": f"KXBTC15M/USD.{venue}",
            "ALGOBOTS_NODE_CURRENCY": "USD",
            "ALGOBOTS_FEED": "kalshi",
            "ALGOBOTS_DEPLOYMENT_SNAPSHOT": json.dumps(snapshot, sort_keys=True),
        },
    )


def spawn_node(spec: LaunchSpec) -> subprocess.Popen:
    """Launch the installed paper-node module without shell or broker secrets."""
    allowed = {"PATH", "LANG", "TZ", "REDIS_HOST", "REDIS_PORT", "ALGOBOTS_KALSHI_PATH"}
    env = {key: value for key, value in os.environ.items() if key in allowed}
    env.update(spec.environment)
    return subprocess.Popen(
        [sys.executable, "-m", "algobots.node.paper_node"],
        env=env,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def stop_node(child: Any) -> None:
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)


@dataclass
class DeploymentRuntime:
    spawn: Callable[[LaunchSpec], Any] = spawn_node
    children: dict[str, Any] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)

    def reconcile(self, rows: list[tuple[Any, Any, Any]]) -> None:
        desired = {}
        for deployment, account, fleet in rows:
            did = str(deployment.id)
            if effective_state(deployment, fleet)[0] != "running":
                # An explicit pause/stop permits a later intentional restart.
                self.failures.pop(did, None)
                continue
            try:
                desired[did] = launch_spec(deployment, account)
            except ValueError as exc:
                self.failures[did] = str(exc)
        for did, child in list(self.children.items()):
            if did not in desired:
                stop_node(child)
                del self.children[did]
            elif child.poll() is not None:
                self.failures[did] = f"worker exited: {child.poll()}"
                del self.children[did]
        for did, spec in desired.items():
            if did not in self.children and did not in self.failures:
                try:
                    self.children[did] = self.spawn(spec)
                except OSError as exc:
                    self.failures[did] = f"worker launch failed: {exc}"

    def close(self) -> None:
        for did, child in list(self.children.items()):
            stop_node(child)
            del self.children[did]
