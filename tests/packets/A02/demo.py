"""A02 demo (ALG-3098): the implemented feature and one failure path.

Feature: the reconciled 38-packet queue from docs/repository-map.json loads
as the task-graph specification (all BACKLOG), and one task runs the full
claim -> heartbeat -> complete(passed) -> integrate(exact-commit review)
path to DONE, which makes its dependent eligible.

Failure path: TIGHT (budget 2) burns its attempts; the authority
checkpoints it as BLOCKED with a published reason and handoff, and a
worker loop provably stops instead of retrying forever.

Everything is driven through reproducible fixtures (deterministic injected
clock, fixture task graph) and lands in artifacts/A02/demo-run.json plus
the coordinator compatibility report for the 38-packet graph.

    PYTHONPATH=. python tests/packets/A02/demo.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "artifacts" / "A02"
FIXTURE_GRAPH = Path(__file__).resolve().parent / "fixtures" / "task-graph.json"
REPOSITORY_MAP = ROOT / "docs" / "repository-map.json"

sys.path.insert(0, str(ROOT))

from tools.agent_queue.authority import ClaimDenied, TaskAuthority  # noqa: E402
from tools.agent_queue.graph import MAX_SAME_FAILURE_REPAIRS, TaskGraph  # noqa: E402
from tools.agent_queue.report import compatibility_report  # noqa: E402


def packet_graph() -> TaskGraph:
    """The reconciled 38-packet queue as a task graph specification."""
    packets = json.loads(REPOSITORY_MAP.read_text(encoding="utf-8"))["packets"]
    return TaskGraph.from_mapping(
        {
            "tasks": [
                {
                    "id": packet_id,
                    "deps": sorted(spec.get("dependencies", [])),
                    "budget_attempts": 3,
                }
                for packet_id, spec in sorted(packets.items())
            ]
        }
    )


def feature_walkthrough(state_path: Path) -> dict:
    graph = TaskGraph.load(FIXTURE_GRAPH)
    clock = {"t": 1_000_000.0}
    authority = TaskAuthority(state_path, graph, lease_ttl_s=900.0,
                              clock=lambda: clock["t"])
    steps: list[dict] = []

    claim = authority.claim("ROOT", "tech-lead")
    steps.append({"step": "claim", "task": "ROOT", "epoch": claim.epoch,
                  "owner": claim.owner, "worktree": claim.worktree,
                  "resources": list(claim.resources)})

    clock["t"] += 300
    renewed = authority.heartbeat("ROOT", "tech-lead", claim.epoch)
    steps.append({"step": "heartbeat", "task": "ROOT", "epoch": renewed.epoch,
                  "lease_expires_at": renewed.lease_expires_at})

    authority.complete("ROOT", "tech-lead", claim.epoch, "passed",
                       note="branch tests green")
    steps.append({"step": "complete", "task": "ROOT", "epoch": claim.epoch,
                  "result": "passed", "status": authority.status("ROOT")["status"]})

    authority.integrate("ROOT", "tech-lead", claim.epoch,
                        commit="f4c1e2a", review_commit="f4c1e2a")
    steps.append({"step": "integrate", "task": "ROOT", "commit": "f4c1e2a",
                  "review_commit": "f4c1e2a",
                  "status": authority.status("ROOT")["status"]})

    dependent = authority.claim("A", "owner-2")  # only possible because ROOT is DONE
    steps.append({"step": "claim", "task": "A", "epoch": dependent.epoch,
                  "note": "eligible because ROOT integrated (not just passed)"})
    return {"steps": steps}


def failure_path(state_path: Path) -> dict:
    graph = TaskGraph.load(FIXTURE_GRAPH)
    clock = {"t": 2_000_000.0}
    authority = TaskAuthority(state_path, graph, lease_ttl_s=900.0,
                              clock=lambda: clock["t"])
    rounds = 0
    while True:  # the worker loop the authority must be able to stop
        rounds += 1
        try:
            claim = authority.claim("TIGHT", "worker")
        except ClaimDenied as exc:
            stop_reason = exc.reason
            break
        authority.complete("TIGHT", "worker", claim.epoch, "failed",
                           note="same defect")
        if authority.status("TIGHT")["status"] == "BLOCKED":
            stop_reason = authority.blocked_record("TIGHT").reason
            break
    blocked = authority.blocked_record("TIGHT")
    return {
        "task": "TIGHT",
        "budget_attempts": 2,
        "same_failure_cap": MAX_SAME_FAILURE_REPAIRS,
        "worker_loop_rounds": rounds,
        "stopped_on": stop_reason,
        "blocked_record": {
            "reason": blocked.reason,
            "attempts": blocked.attempts,
            "epoch": blocked.epoch,
        },
    }


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="a02-demo-") as tmp:
        tmpdir = Path(tmp)
        demo_state = tmpdir / "demo-state.json"
        graph = packet_graph()
        report = compatibility_report(
            TaskAuthority(tmpdir / "queue-state.json", graph)
        )
        (ARTIFACTS / "compatibility-report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        run = {
            "packet": "A02",
            "issue": "ALG-3098",
            "graph_fixture": "tests/packets/A02/fixtures/task-graph.json",
            "queue": {
                "source": "docs/repository-map.json",
                "tasks": report["graph"]["tasks"],
                "roots": report["graph"]["roots"],
                "initial_status": "BACKLOG for all packets",
            },
            "feature": feature_walkthrough(demo_state),
            "failure_path": failure_path(demo_state),
        }
    (ARTIFACTS / "demo-run.json").write_text(
        json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"queue: {run['queue']['tasks']} packets from repository-map, all BACKLOG; "
          f"roots {', '.join(run['queue']['roots'])}")
    print(f"feature: ROOT claimed->passed->integrated@f4c1e2a; A claimable (epoch "
          f"{run['feature']['steps'][-1]['epoch']})")
    fp = run["failure_path"]
    print(f"failure path: TIGHT blocked after {fp['worker_loop_rounds']} rounds — "
          f"{fp['blocked_record']['reason']}")
    print("artifacts: artifacts/A02/demo-run.json, artifacts/A02/compatibility-report.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
