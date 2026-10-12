"""A02 — atomic task queue, leases and integration receipts.

One task authority over acceptance-based work: task-graph.json is the
specification (all packets start BACKLOG); claims are transactional,
lease-bound and epoch-stamped; DONE requires both passing branch tests
(`complete`) and a successful integration (`integrate`) — so a failed
integration leaves every dependent ineligible even though the branch was
green. Budgets bound retries; exhaustion checkpoints as BLOCKED with a
published reason instead of looping.
"""

from tools.agent_queue.authority import StaleAttemptError, TaskAuthority
from tools.agent_queue.contracts import BlockedRecord, CompletionReceipt, TaskClaim
from tools.agent_queue.graph import TaskGraph, TaskSpec

__all__ = [
    "BlockedRecord",
    "CompletionReceipt",
    "StaleAttemptError",
    "TaskAuthority",
    "TaskClaim",
    "TaskGraph",
    "TaskSpec",
]
