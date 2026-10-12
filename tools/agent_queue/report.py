"""Coordinator compatibility report (A02 output contract #3).

States whether — and why — this coordinator can run a given task graph:
graph shape, lease policy, retry caps, the reuse decision against the
verified A06 worker lease, per-task statuses and published blocked
reasons. Pure function over an authority snapshot so it is reproducible
in tests and the demo.
"""

from __future__ import annotations

from typing import Any

from tools.agent_queue.authority import (
    BLOCKED,
    DEFAULT_LEASE_TTL_S,
    DONE,
    TaskAuthority,
)
from tools.agent_queue.graph import DEFAULT_BUDGET_ATTEMPTS, MAX_SAME_FAILURE_REPAIRS, TaskGraph

REUSE_NOTE = (
    "A06's verified worker lease (algobots.engine.workers.lease) governs "
    "long-lived account workers via PID liveness; packet attempts need "
    "epoch-stamped transactional claims instead, so this authority reuses "
    "the flock + atomic-replace technique, not the module."
)


def graph_summary(graph: TaskGraph) -> dict[str, Any]:
    specs = graph.by_id()
    roots = sorted(s.id for s in graph.tasks if not s.deps)
    resources: dict[str, list[str]] = {}
    for spec in graph.tasks:
        for resource in spec.resources:
            resources.setdefault(resource, []).append(spec.id)
    return {
        "tasks": len(specs),
        "edges": sum(len(s.deps) for s in graph.tasks),
        "roots": roots,
        "default_budget_attempts": DEFAULT_BUDGET_ATTEMPTS,
        "shared_resources": {
            name: {"tasks": sorted(ids)} for name, ids in sorted(resources.items())
        },
        "load_time_checks": [
            "non-empty tasks list",
            "unique ids",
            "deps resolve to known ids",
            "no self-dependency",
            "no dependency cycles",
        ],
        "initial_status": "BACKLOG for every task regardless of file contents",
    }


def compatibility_report(authority: TaskAuthority) -> dict[str, Any]:
    state = authority.snapshot()
    statuses = {tid: row["status"] for tid, row in state["tasks"].items()}
    blocked = {
        tid: row["blocked"]["reason"]
        for tid, row in state["tasks"].items()
        if row["status"] == BLOCKED and row["blocked"]
    }
    done = sorted(tid for tid, s in statuses.items() if s == DONE)
    return {
        "schema": "agent-queue-compat/1.0",
        "coordinator": "tools/agent_queue.TaskAuthority",
        "compatible": True,
        "mechanism": {
            "transaction": "flock-guarded read-modify-write; tmp + fsync + os.replace",
            "claim_exclusivity": "one ACTIVE lease per task; epoch bumps on reclaim",
            "done_requires": [
                "completion receipt (branch tests passed)",
                "exact-commit independent review (review commit == integration commit)",
                "accepted integration",
            ],
            "lease_ttl_s": state.get("lease_ttl_s", DEFAULT_LEASE_TTL_S),
            "budget_attempts_default": DEFAULT_BUDGET_ATTEMPTS,
            "max_same_failure_repairs": MAX_SAME_FAILURE_REPAIRS,
            "worktrees": "one reserved path per task (.wt-<id>); created/removed by the runner",
            "resource_locks": "exclusive per named shared resource; held only by an ACTIVE attempt",
        },
        "reuse_decision": REUSE_NOTE,
        "graph": graph_summary(authority._graph),
        "statuses": statuses,
        "done": done,
        "blocked": blocked,
        "single_authority": {
            "state_file": str(authority._path),
            "lock": str(authority._path) + ".lock",
            "rule": "one coordinator per state file; no second claimant of the same work",
        },
    }
