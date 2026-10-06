# A01 — Demo and limitations

Packet A01 (ALG-3097) freezes the shared contracts and the repository ownership map.
Baseline is algobots `main` @ `b340c99`. The ALG-3086 harness consolidation merge is also `b340c99`.

## Demo (`make demo-A01`)

Output captured in `demo-output.txt`:

```
registry: 19 contracts; lock drift: none
[ok] OrderPlan@1.0 child child-1: 10 shares <= 1872.50 USD; round-trip exact: True
[rejected] float amount: Value error, decimal amounts must be strings, got float 1.0
[rejected] schema revision: OrderPlan@1.0 removed while queued packets pin it: A07, A08, A20, A21, A32
```

1. **Feature:** a golden `OrderPlan@1.0` parses through the registry. It keeps decimal strings with explicit units and currencies, and its JSON round-trip is exact.
2. **Failure path (contract):** a float amount is rejected with a clear message.
3. **Failure path (revision safety):** removing a locked version is rejected while queued packets pin it, and the error names the stranded packets.

## What shipped

- **Contracts** (`src/algobots/contracts/`): 19 registered `name@1.0` contracts plus the `MemoryStore` protocol.
  - Each contract is frozen, rejects unknown fields and carries an explicit `schema_version`.
  - Amounts are decimal strings. Floats, ints and non-finite values are rejected.
  - Money always carries a currency and quantities always carry a unit.
  - Timestamps must be RFC3339 with an offset and are normalized to UTC.
  - Probabilities are finite and bounded.
- **Identities** (`identity.py`, `memory.py`): USER, EXECUTION_SERVICE, MEMORY_SERVICE, RESEARCH_AGENT and BUILD_AGENT have disjoint grant sets.
  - Build agents reach only `engineering/project`.
  - Research and model identities can never hold a trading grant.
  - Tenant scope is derived from the principal.
- **Schema registry and lock** (`registry.py`, `schema-lock.json`):
  - The lock holds a JSON-schema fingerprint for each registered version.
  - A shape change without a version bump is drift.
  - Rewriting a locked fingerprint, or removing a version that a queued packet pins, raises `SchemaRevisionError`.
- **Repository map** (`docs/repository-map.json`):
  - All 38 packets resolve to repo plus path entries marked real or proposed.
  - 12 scope revisions are recorded (revision 1 → 2).
  - 9 shared resources each have exactly one integration owner.
  - The harness freeze is recorded.
  - Every file tracked at baseline has an owner.
- **Resource locks:** `schema-registry`, `dependency-lockfiles`, `generated-clients` and `make-targets` are owned by A01. `db-migrations` and `auth-contract` are owned by A03, `execution-contract` by A07, `task-authority` by A02 and `infrastructure-state` by A25.

## Scope revisions recorded in the map

Revisions were needed because roadmap paths are proposals (A00/A01 resolve them):

- **Single Alembic tree:** `db/migrations/{auth,execution}` resolve to the existing `src/algobots/api/migrations/`, held under the `db-migrations` lock.
- **Existing S-card code is inherited by its natural packet:**
  - A03: control-plane core (ALG-3078)
  - A04: `api/accounts/` (S4.1)
  - A11: `api/deployments/` (S4.2)
  - A21: `api/approvals/` (S4.3)
  - A20: the S1.3 `execution/planner.py`. A20's proposed `planner/` package would shadow that module.
- **A19** is narrowed to `evals/outcomes/` so it cannot overlap the frozen harness or A28 `prospective/`.
- **Invalid package names fixed:** A29 `tests/live_preflight/` and A37 `dashboard/build_activity/`.
- **A01 additions:** `Makefile`, `pyproject.toml` and `uv.lock`, which hold the `make-targets` and `dependency-lockfiles` resources.

## Harness freeze

- Paths: `src/algobots/evals/harness/` and `tests/evals/harness/`.
- Home: the algobots monorepo, head `b340c99` (ALG-3086 consolidation merge, CI run 37396961518).
- No packet writes these paths. A12, A18 and A28 read them. Any change needs a PM dispatch change recorded on ALG-3086.

## Limitations

- **Contracts are platform shapes, not vendor schemas.**
  - Nautilus, Jev, broker and TencentDB adapters (A06, A18, A23, A15) map to and from these shapes.
  - Nothing here claims a vendor capability, and no external service was contacted.
- **The `MemoryStore` protocol has no implementation.** The A15 adapter must pass conformance against a deterministic fixture and, separately, the real deployment.
- **No fan-out parent contract yet.** Per-account plans link through `parent_plan_id`. A07 may propose a `FanOutPlan@1.0` through the registry.
- **`FillEvent.fee` must be ≥ 0.** Maker rebates are expected as separate cash-flow records (A30). Changing that means a new version.
- **Path status is a baseline snapshot.** `real` and `proposed` reflect `b340c99`. Proposed paths become real as their packets land. The test enforces only that `real` paths in algobots exist. Paths in stock-vaults and vps-infra are not checked in CI, which checks out algobots only.
- **Kestra flow paths are unresolved.** A16 `flows/analytics/` and A24 `flows/operations/` stay proposed in algobots. Deploying them to vps-infra `kestra/flows/` is an `infrastructure-state` change for A25 to own.
- **The commit-scope test** (`test_a01_commits_stay_inside_a01_scope`) inspects commits whose message cites ALG-3097, diffing each against its parent. It skips on shallow clones such as CI. CI run 37398196561 failed before fix `9821449` because a depth-1 checkout makes the commit look like a root commit.
- **Independent review is pending.** `integrated_commit` is null until the review passes and the branch merges to `main`.

## Recovery

Revert the A01 merge commit on `main`. No runtime code depends on `algobots.contracts` yet, so disabling it leaves the existing suite unaffected (196 tests at `b340c99`). Evidence in `artifacts/A01/` is preserved.
