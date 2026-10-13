"""Operator CLI: one process per command, all against the same state file.

    python -m tools.agent_queue --graph g.json --state s.json claim A01 owner-1
    python -m tools.agent_queue ... heartbeat A01 owner-1 <epoch>
    python -m tools.agent_queue ... complete A01 owner-1 <epoch> passed|failed [--note n]
    python -m tools.agent_queue ... integrate A01 owner-1 <epoch> --commit C --review-commit C
    python -m tools.agent_queue ... integration-failed A01 owner-1 <epoch> [--note n]
    python -m tools.agent_queue ... cancel A01 [--reason n]
    python -m tools.agent_queue ... status [A01]
    python -m tools.agent_queue ... report [--out file.json]

Exit codes: 0 ok; 1 usage/state error; 2 denied (ClaimDenied); 3 stale
attempt (StaleAttemptError); 4 invalid transition. Every command prints one
JSON object so scripts can consume the outcome.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.agent_queue.authority import (
    DEFAULT_LEASE_TTL_S,
    ClaimDenied,
    InvalidTransition,
    StaleAttemptError,
    TaskAuthority,
)
from tools.agent_queue.graph import TaskGraph

EXIT_USAGE = 1
EXIT_DENIED = 2
EXIT_STALE = 3
EXIT_INVALID = 4


def _emit(payload: dict) -> None:
    print(json.dumps(payload, sort_keys=True, default=str))


def _authority(args: argparse.Namespace) -> TaskAuthority:
    return TaskAuthority(args.state, TaskGraph.load(args.graph), lease_ttl_s=args.lease_ttl)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tools.agent_queue", description=__doc__.splitlines()[0])
    parser.add_argument("--graph", required=True, help="task-graph.json specification")
    parser.add_argument("--state", required=True, help="authority state file (JSON)")
    parser.add_argument("--lease-ttl", type=float, default=DEFAULT_LEASE_TTL_S,
                        help="lease time-to-live in seconds (default 900)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("claim")
    p.add_argument("task_id")
    p.add_argument("owner")
    p = sub.add_parser("heartbeat")
    p.add_argument("task_id")
    p.add_argument("owner")
    p.add_argument("epoch", type=int)
    p = sub.add_parser("complete")
    p.add_argument("task_id")
    p.add_argument("owner")
    p.add_argument("epoch", type=int)
    p.add_argument("result", choices=["passed", "failed"])
    p.add_argument("--note", default="")
    p = sub.add_parser("integrate")
    p.add_argument("task_id")
    p.add_argument("owner")
    p.add_argument("epoch", type=int)
    p.add_argument("--commit", required=True)
    p.add_argument("--review-commit", required=True)
    p = sub.add_parser("integration-failed")
    p.add_argument("task_id")
    p.add_argument("owner")
    p.add_argument("epoch", type=int)
    p.add_argument("--note", default="")
    p = sub.add_parser("cancel")
    p.add_argument("task_id")
    p.add_argument("--reason", default="")
    p = sub.add_parser("status")
    p.add_argument("task_id", nargs="?")
    p = sub.add_parser("report")
    p.add_argument("--out", default="")

    args = parser.parse_args(argv)
    try:
        authority = _authority(args)
        if args.cmd == "claim":
            claim = authority.claim(args.task_id, args.owner)
            _emit({"event": "claim", **_claim_dict(claim)})
        elif args.cmd == "heartbeat":
            claim = authority.heartbeat(args.task_id, args.owner, args.epoch)
            _emit({"event": "heartbeat", **_claim_dict(claim)})
        elif args.cmd == "complete":
            receipt = authority.complete(
                args.task_id, args.owner, args.epoch, args.result, note=args.note
            )
            _emit({"event": "complete", **vars(receipt)})
        elif args.cmd == "integrate":
            receipt = authority.integrate(
                args.task_id, args.owner, args.epoch,
                commit=args.commit, review_commit=args.review_commit,
            )
            _emit({"event": "integrate", **vars(receipt)})
        elif args.cmd == "integration-failed":
            receipt = authority.integration_failed(
                args.task_id, args.owner, args.epoch, note=args.note
            )
            _emit({"event": "integration-failed", **vars(receipt)})
        elif args.cmd == "cancel":
            authority.cancel(args.task_id, reason=args.reason)
            _emit({"event": "cancel", "task_id": args.task_id})
        elif args.cmd == "status":
            if args.task_id:
                _emit({"event": "status", **authority.status(args.task_id)})
            else:
                _emit({"event": "snapshot", **authority.snapshot()})
        elif args.cmd == "report":
            from tools.agent_queue.report import compatibility_report

            report = compatibility_report(authority)
            if args.out:
                Path(args.out).parent.mkdir(parents=True, exist_ok=True)
                Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
            _emit({"event": "report", "tasks": report["graph"]["tasks"],
                   "blocked": report["blocked"], "out": args.out})
        return 0
    except ClaimDenied as exc:
        _emit({"event": args.cmd, "error": "ClaimDenied", "reason": exc.reason})
        return EXIT_DENIED
    except StaleAttemptError as exc:
        _emit({"event": args.cmd, "error": "StaleAttemptError", "reason": exc.reason})
        return EXIT_STALE
    except InvalidTransition as exc:
        _emit({"event": args.cmd, "error": "InvalidTransition", "reason": exc.reason})
        return EXIT_INVALID
    except (ValueError, OSError) as exc:
        _emit({"event": args.cmd, "error": type(exc).__name__, "reason": str(exc)})
        return EXIT_USAGE


def _claim_dict(claim) -> dict:
    return {
        "task_id": claim.task_id,
        "epoch": claim.epoch,
        "owner": claim.owner,
        "lease_expires_at": claim.lease_expires_at,
        "worktree": claim.worktree,
        "resources": list(claim.resources),
    }


if __name__ == "__main__":
    sys.exit(main())
