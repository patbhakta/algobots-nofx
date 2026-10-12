# A02 — Atomic task queue, leases and integration receipts: demo & limitations

Issue: ALG-3098 · Slice: sprint-1 (transactional claims + leases over task-graph.json)
Commit: see `git log` for this file · Environment: development (Python 3.12, stdlib only)

## What was implemented

`tools/agent_queue/` — one task authority (exclusive shared resource
`task-authority`) over acceptance-based packet work:

- **`graph.py`** — loads `task-graph.json` as the specification (deps,
  `budget_attempts`, exclusive `resources`). Load-time checks: non-empty task
  list, unique ids, deps resolve, no self-deps, no cycles. Every task loads
  as BACKLOG regardless of file contents.
- **`authority.py`** — transactional state machine: dependency-gated claims,
  attempt epochs, heartbeats (lease renewal), cancellation, budgets, bounded
  retries. Every mutation is one flock-guarded read-modify-write of a JSON
  state file (tmp + fsync + os.replace). Output contracts: `TaskClaim`,
  `CompletionReceipt`, `BlockedRecord`.
- **`__main__.py`** — operator CLI (`claim|heartbeat|complete|integrate|
  integration-failed|cancel|status|report`), one JSON object per command,
  distinct exit codes (ok 0, usage 1, denied 2, stale 3, invalid 4).
- **`report.py`** — coordinator compatibility report (output contract #3):
  graph shape, lease policy, caps, the A06-reuse decision, statuses, blocked
  reasons.

DONE requires all three: a passing branch receipt (`complete ... passed`),
an exact-commit independent review (`--review-commit` must equal
`--commit`), and an accepted integration (`integrate`). A failed
integration (`integration-failed`) burns the attempt and leaves every
dependent ineligible however green the branch was (AC3).

## Demo (reproducible)

    make verify-A02   # 46 tests: tests/agent_queue + tests/packets/A02 -> AC1-4 PASS
    make demo-A02     # artifacts/A02/demo-run.json + compatibility-report.json

The demo (`tests/packets/A02/demo.py`) uses only deterministic fixtures
(injected clock, `tests/packets/A02/fixtures/task-graph.json`):

1. **Feature**: the reconciled 38-packet queue from `docs/repository-map.json`
   loads as the graph (all BACKLOG; root `A00`); on the fixture graph ROOT
   runs claim → heartbeat → complete(passed) → integrate@`f4c1e2a`
   (review commit == integration commit) → DONE, which makes dependent A
   claimable.
2. **Failure path**: TIGHT (budget 2) fails twice; the authority checkpoints
   it BLOCKED with reason "budget exhausted: 2/2 attempts" and a handoff
   record, and the worker loop provably stops after 2 rounds instead of
   retrying forever.

## Limitations

- **Worktrees are bookkeeping, not git operations.** A claim reserves and
  records an isolated worktree path (`.wt-<task-id>`, matching the harness's
  existing `.wt-alg-*` convention); creating/removing the git worktree is
  the runner's job. The authority enforces exclusivity of named resources,
  not filesystem isolation.
- **Single-host coordinator.** flock guards one state file on one host;
  multi-host deployment would need the same state machine over a
  transactional store (SQLite/Postgres). Within one host, any number of
  processes/threads share the authority safely (AC1 races both ways).
- **Lease expiry uses wall-clock time** (`clock` is injectable; the CLI uses
  real time). `--lease-ttl` bounds it; there is no automatic revoke daemon —
  a lapsed lease is reclaimed lazily by the next claimant.
- **Review is verified, not performed.** `integrate` enforces that the
  review receipt names the exact integration commit; the review itself is
  an out-of-band human/agent act (per the A02 spec's independent-review
  requirement).
- **State-file compatibility**: opening a state file with a different graph
  is rejected (fingerprint); there is no migration path — a new graph gets a
  new state file.

## Recovery

The queue is additive tooling: nothing imports it at runtime. Disable by
removing/not running `tools/agent_queue` (or reverting this commit); state
files are self-contained JSON durable records and can be archived as
evidence. No production, capital, or `/demo` paths are touched.

## Known pre-existing main drift (not A02's to fix)

`make verify-A02` and the full suite were run at this commit: A02 slices are
green, but main at `28a6f41` already fails
`tests/packets/A01/test_a01_repository_map.py::test_every_tracked_file_has_an_owner`
(`docs/research/alg-3309-...md`, `tests/api/test_fleet_breaker_tenancy.py`
lack scope revisions) and 9 `tests/demo/test_accounts.py` tests. Reported on
ALG-3098; owner of `docs/repository-map.json` (A01 integration) owns the fix.
