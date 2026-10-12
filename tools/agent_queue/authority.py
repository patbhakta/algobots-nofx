"""Transactional task authority: one claim per task, lease-bound attempts.

Every mutating call runs inside one ``flock``-guarded read-modify-write of
the JSON state file (tmp + fsync + ``os.replace``), so two processes — or
two threads — can never both win a claim (AC1). An attempt is identified by
``(owner, epoch)`` where ``epoch`` is the per-task monotonic attempt number;
once a lease expires and someone reclaims, the epoch bumps and every later
write from the old attempt is rejected as stale (AC2). ``complete`` records
the branch-level receipt; only ``integrate`` — exact-commit independent
review plus accepted integration — moves a task to DONE, so a failed
integration leaves every dependent ineligible however green the branch was
(AC3). Budgets are consumed per claim; exhaustion checkpoints the task as
BLOCKED with a published reason and handoff instead of another retry (AC4).

Stdlib only; the flock + atomic-replace technique mirrors the verified A06
worker lease (``algobots.engine.workers.lease``), which stays the authority
for long-lived account workers — different domain, deliberately not reused
as a module (see report.compatibility_report).
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from tools.agent_queue.contracts import BlockedRecord, CompletionReceipt, TaskClaim
from tools.agent_queue.graph import MAX_SAME_FAILURE_REPAIRS, TaskGraph

STATE_SCHEMA = "agent-queue-state/1.0"
DEFAULT_LEASE_TTL_S = 900.0

BACKLOG = "BACKLOG"
ACTIVE = "ACTIVE"
WAITING_INTEGRATION = "WAITING_INTEGRATION"
DONE = "DONE"
BLOCKED = "BLOCKED"
CANCELLED = "CANCELLED"
_TERMINAL = {DONE, BLOCKED, CANCELLED}


class ClaimDenied(RuntimeError):
    """``claim`` refused; the task is not claimable right now."""

    def __init__(self, task_id: str, reason: str) -> None:
        super().__init__(f"{task_id}: {reason}")
        self.task_id, self.reason = task_id, reason


class StaleAttemptError(RuntimeError):
    """A write against an attempt that is expired, revoked or superseded."""

    def __init__(self, task_id: str, reason: str) -> None:
        super().__init__(f"{task_id}: {reason}")
        self.task_id, self.reason = task_id, reason


class InvalidTransition(RuntimeError):
    """The write does not apply to the task's current state."""

    def __init__(self, task_id: str, reason: str) -> None:
        super().__init__(f"{task_id}: {reason}")
        self.task_id, self.reason = task_id, reason


def graph_fingerprint(graph: TaskGraph) -> str:
    payload = [
        {"id": s.id, "deps": list(s.deps), "budget_attempts": s.budget_attempts,
         "resources": list(s.resources)}
        for s in graph.tasks
    ]
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


class TaskAuthority:
    """Single-writer coordinator over one task-graph.json specification."""

    def __init__(
        self,
        state_path: str | Path,
        graph: TaskGraph,
        *,
        lease_ttl_s: float = DEFAULT_LEASE_TTL_S,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._path = Path(state_path)
        self._graph = graph
        self._lease_ttl_s = lease_ttl_s
        self._clock = clock
        self._lock_path = self._path.with_name(self._path.name + ".lock")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # One transaction at init: initializes fresh state or validates the
        # existing file (schema + graph fingerprint) before any use.
        with self._transaction():
            pass

    # -- state plumbing -------------------------------------------------

    def _fresh_state(self) -> dict[str, Any]:
        return {
            "schema": STATE_SCHEMA,
            "graph_fingerprint": graph_fingerprint(self._graph),
            "lease_ttl_s": self._lease_ttl_s,
            "tasks": {
                spec.id: {
                    "status": BACKLOG,
                    "epoch": 0,
                    "owner": None,
                    "lease_expires_at": None,
                    "attempts_used": 0,
                    "same_failure_streak": 0,
                    "last_failure": None,
                    "blocked": None,
                    "worktree": f".wt-{spec.id.lower()}",
                    "resources": list(spec.resources),
                    "receipts": [],
                    "integrated_commit": None,
                }
                for spec in self._graph.tasks
            },
            "resource_holders": {},
        }

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            state = self._fresh_state()
            self._write(state)
            return state
        state = json.loads(self._path.read_text(encoding="utf-8"))
        if state.get("schema") != STATE_SCHEMA:
            raise ValueError(f"unsupported state schema: {state.get('schema')!r}")
        if state.get("graph_fingerprint") != graph_fingerprint(self._graph):
            raise ValueError("state was built for a different task graph")
        return state

    def _write(self, state: dict[str, Any]) -> None:
        tmp = self._path.with_name(self._path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self._path)

    @contextmanager
    def _transaction(self) -> Iterator[dict[str, Any]]:
        with open(self._lock_path, "a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                state = self._load()
                yield state
                self._write(state)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def _read(self) -> Iterator[dict[str, Any]]:
        with open(self._lock_path, "a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield self._load()
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _row(self, state: dict[str, Any], task_id: str) -> dict[str, Any]:
        try:
            return state["tasks"][task_id]
        except KeyError:
            raise ValueError(f"unknown task: {task_id}") from None

    # -- queries --------------------------------------------------------

    def status(self, task_id: str) -> dict[str, Any]:
        with self._read() as state:
            row = self._row(state, task_id)
            return {
                "task_id": task_id,
                "status": row["status"],
                "epoch": row["epoch"],
                "owner": row["owner"],
                "attempts_used": row["attempts_used"],
                "same_failure_streak": row["same_failure_streak"],
                "last_failure": row["last_failure"],
                "blocked": row["blocked"],
                "receipts": list(row["receipts"]),
                "integrated_commit": row["integrated_commit"],
            }

    def snapshot(self) -> dict[str, Any]:
        with self._read() as state:
            return json.loads(json.dumps(state))

    def blocked_record(self, task_id: str) -> BlockedRecord | None:
        with self._read() as state:
            row = self._row(state, task_id)
            return BlockedRecord(**row["blocked"]) if row["blocked"] else None

    def ineligible_deps(self, state: dict[str, Any], task_id: str) -> list[str]:
        spec = self._graph.by_id()[task_id]
        return [d for d in spec.deps if state["tasks"][d]["status"] != DONE]

    # -- mutation -------------------------------------------------------

    def claim(self, task_id: str, owner: str, *, now: float | None = None) -> TaskClaim:
        now = self._clock() if now is None else now
        with self._transaction() as state:
            row = self._row(state, task_id)
            if row["status"] in _TERMINAL or row["status"] == BLOCKED:
                reason = (
                    f"blocked: {row['blocked']['reason']}" if row["status"] == BLOCKED
                    else f"task is {row['status']}"
                )
                raise ClaimDenied(task_id, reason)
            if row["status"] == ACTIVE and row["lease_expires_at"] is not None \
                    and now < row["lease_expires_at"]:
                raise ClaimDenied(
                    task_id,
                    f"active lease held by {row['owner']} (epoch {row['epoch']}), "
                    f"expires at {row['lease_expires_at']:.3f}",
                )
            if row["status"] == WAITING_INTEGRATION and row["lease_expires_at"] is not None \
                    and now < row["lease_expires_at"]:
                raise ClaimDenied(
                    task_id,
                    f"attempt epoch {row['epoch']} by {row['owner']} passed branch tests "
                    "and awaits integration; heartbeat and integrate it",
                )
            if (pending := self.ineligible_deps(state, task_id)):
                raise ClaimDenied(task_id, f"dependencies not DONE: {', '.join(pending)}")
            budget = self._graph.by_id()[task_id].budget_attempts
            if row["attempts_used"] >= budget:
                row["status"] = BLOCKED
                row["blocked"] = {
                    "task_id": task_id,
                    "reason": f"budget exhausted: {row['attempts_used']}/{budget} attempts",
                    "attempts": row["attempts_used"],
                    "epoch": row["epoch"],
                    "created_at": now,
                }
                raise ClaimDenied(task_id, f"blocked: {row['blocked']['reason']}")
            spec = self._graph.by_id()[task_id]
            for resource in spec.resources:
                holder = state["resource_holders"].get(resource)
                if holder is not None and holder != task_id:
                    raise ClaimDenied(task_id, f"resource {resource} held by {holder}")
            for resource in spec.resources:
                state["resource_holders"][resource] = task_id
            row["status"] = ACTIVE
            row["epoch"] += 1
            row["attempts_used"] += 1
            row["owner"] = owner
            row["lease_expires_at"] = now + self._lease_ttl_s
            row["blocked"] = None
            return TaskClaim(
                task_id=task_id,
                epoch=row["epoch"],
                owner=owner,
                lease_expires_at=row["lease_expires_at"],
                worktree=row["worktree"],
                resources=tuple(spec.resources),
            )

    def heartbeat(
        self, task_id: str, owner: str, epoch: int, *, now: float | None = None
    ) -> TaskClaim:
        now = self._clock() if now is None else now
        with self._transaction() as state:
            row = self._require_live_attempt(state, task_id, owner, epoch, now)
            row["lease_expires_at"] = now + self._lease_ttl_s
            return TaskClaim(
                task_id=task_id,
                epoch=epoch,
                owner=owner,
                lease_expires_at=row["lease_expires_at"],
                worktree=row["worktree"],
                resources=tuple(row["resources"]),
            )

    def complete(
        self,
        task_id: str,
        owner: str,
        epoch: int,
        result: str,
        *,
        now: float | None = None,
        note: str = "",
    ) -> CompletionReceipt:
        if result not in ("passed", "failed"):
            raise ValueError(f"result must be 'passed' or 'failed', got {result!r}")
        now = self._clock() if now is None else now
        with self._transaction() as state:
            row = self._require_live_attempt(state, task_id, owner, epoch, now)
            if row["status"] == WAITING_INTEGRATION:
                raise InvalidTransition(
                    task_id, f"epoch {epoch} already published a passing receipt"
                )
            receipt = CompletionReceipt(
                task_id=task_id, epoch=epoch, owner=owner,
                result=result, created_at=now, note=note,
            )
            row["receipts"].append(_receipt_dict(receipt))
            if result == "passed":
                row["status"] = WAITING_INTEGRATION
                return receipt
            self._record_failure(state, row, task_id, "tests", now, note)
            return receipt

    def integrate(
        self,
        task_id: str,
        owner: str,
        epoch: int,
        *,
        commit: str,
        review_commit: str,
        now: float | None = None,
    ) -> CompletionReceipt:
        now = self._clock() if now is None else now
        with self._transaction() as state:
            row = self._require_live_attempt(state, task_id, owner, epoch, now)
            if row["status"] != WAITING_INTEGRATION:
                raise InvalidTransition(
                    task_id,
                    f"integration requires a passing receipt first; status is {row['status']}",
                )
            if not commit or not review_commit:
                raise InvalidTransition(task_id, "integration needs a commit and a review commit")
            if review_commit != commit:
                raise InvalidTransition(
                    task_id,
                    f"exact-commit review required: review {review_commit!r} != commit {commit!r}",
                )
            receipt = CompletionReceipt(
                task_id=task_id, epoch=epoch, owner=owner,
                result="integrated", created_at=now,
                note=f"reviewed+integrated at {commit}",
            )
            row["receipts"].append(_receipt_dict(receipt))
            row["status"] = DONE
            row["owner"] = None
            row["lease_expires_at"] = None
            row["integrated_commit"] = commit
            for resource in row["resources"]:
                if state["resource_holders"].get(resource) == task_id:
                    del state["resource_holders"][resource]
            return receipt

    def integration_failed(
        self, task_id: str, owner: str, epoch: int, *, now: float | None = None, note: str = ""
    ) -> CompletionReceipt:
        now = self._clock() if now is None else now
        with self._transaction() as state:
            row = self._require_live_attempt(state, task_id, owner, epoch, now)
            if row["status"] != WAITING_INTEGRATION:
                raise InvalidTransition(
                    task_id,
                    f"no passing receipt to fail integration for; status is {row['status']}",
                )
            receipt = CompletionReceipt(
                task_id=task_id, epoch=epoch, owner=owner,
                result="failed", created_at=now,
                note=f"integration: {note}" if note else "integration",
            )
            row["receipts"].append(_receipt_dict(receipt))
            self._record_failure(state, row, task_id, "integration", now, note)
            return receipt

    def cancel(self, task_id: str, *, now: float | None = None, reason: str = "") -> None:
        now = self._clock() if now is None else now
        with self._transaction() as state:
            row = self._row(state, task_id)
            if row["status"] in (DONE, CANCELLED):
                raise InvalidTransition(task_id, f"task is already {row['status']}")
            row["status"] = CANCELLED
            row["owner"] = None
            row["lease_expires_at"] = None
            for resource in row["resources"]:
                if state["resource_holders"].get(resource) == task_id:
                    del state["resource_holders"][resource]
            if reason:
                row["last_failure"] = {"kind": "cancelled", "note": reason}

    # -- internals ------------------------------------------------------

    def _require_live_attempt(
        self, state: dict[str, Any], task_id: str, owner: str, epoch: int, now: float
    ) -> dict[str, Any]:
        row = self._row(state, task_id)
        if row["status"] not in (ACTIVE, WAITING_INTEGRATION):
            raise StaleAttemptError(
                task_id, f"attempt epoch {epoch} is not live; task is {row['status']}"
            )
        if row["epoch"] != epoch or row["owner"] != owner:
            raise StaleAttemptError(
                task_id,
                f"attempt epoch {epoch} by {owner} was superseded by epoch "
                f"{row['epoch']} by {row['owner']}",
            )
        if row["lease_expires_at"] is None or now >= row["lease_expires_at"]:
            raise StaleAttemptError(
                task_id,
                f"attempt epoch {epoch} lease expired at {row['lease_expires_at']}",
            )
        return row

    def _record_failure(
        self,
        state: dict[str, Any],
        row: dict[str, Any],
        task_id: str,
        kind: str,
        now: float,
        note: str,
    ) -> None:
        last = row["last_failure"]
        streak = row["same_failure_streak"] + 1 if last and last.get("kind") == kind else 1
        row["same_failure_streak"] = streak
        row["last_failure"] = {"kind": kind, "note": note}
        row["owner"] = None
        row["lease_expires_at"] = None
        for resource in row["resources"]:
            if state["resource_holders"].get(resource) == task_id:
                del state["resource_holders"][resource]
        budget = self._graph.by_id()[task_id].budget_attempts
        reason = None
        if streak >= MAX_SAME_FAILURE_REPAIRS:
            reason = (
                f"same-failure repair cap: {streak} consecutive '{kind}' failures "
                f"(max {MAX_SAME_FAILURE_REPAIRS})"
            )
        elif row["attempts_used"] >= budget:
            reason = f"budget exhausted: {row['attempts_used']}/{budget} attempts"
        if reason is not None:
            row["status"] = BLOCKED
            row["blocked"] = {
                "task_id": task_id,
                "reason": reason,
                "attempts": row["attempts_used"],
                "epoch": row["epoch"],
                "created_at": now,
            }
        else:
            row["status"] = BACKLOG  # deps were DONE to be claimed; stays eligible


def _receipt_dict(receipt: CompletionReceipt) -> dict[str, Any]:
    return {
        "task_id": receipt.task_id,
        "epoch": receipt.epoch,
        "owner": receipt.owner,
        "result": receipt.result,
        "created_at": receipt.created_at,
        "note": receipt.note,
    }
