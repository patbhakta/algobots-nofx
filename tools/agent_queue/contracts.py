"""Output contracts of the task authority: TaskClaim, CompletionReceipt, BlockedRecord."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TaskClaim:
    """A granted lease on one task attempt.

    `epoch` is the authority's monotonic attempt number; every later
    write (heartbeat, completion, integration) must carry the same epoch
    or the authority rejects it as stale. `worktree` is the isolated
    worktree path reserved for the attempt; `resources` are the exclusive
    shared-resource locks the claim holds until the attempt ends.
    """

    task_id: str
    epoch: int
    owner: str
    lease_expires_at: float
    worktree: str = ""
    resources: tuple[str, ...] = ()

    def is_expired(self, now: float) -> bool:
        return now >= self.lease_expires_at


@dataclass(frozen=True, slots=True)
class CompletionReceipt:
    """Durable record of one attempt's outcome.

    result is "passed" (branch tests green, awaiting integration),
    "failed" (attempt consumed; task returns to eligible if budget
    remains) or "integrated" (exact-commit review + accepted integration;
    the only transition to DONE).
    """

    task_id: str
    epoch: int
    owner: str
    result: str
    created_at: float
    note: str = ""


@dataclass(frozen=True, slots=True)
class BlockedRecord:
    """Published blocked reason and minimal handoff checkpoint.

    A BLOCKED task carries everything the next owner needs to resume:
    why it stopped, how many attempts were burned, and the last epoch.
    """

    task_id: str
    reason: str
    attempts: int
    epoch: int
    created_at: float
