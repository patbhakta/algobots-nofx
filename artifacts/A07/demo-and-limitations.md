# A07 — Demo & Limitations (ALG-3103)

## What was built

`src/algobots/execution/ledger/` — durable intent ledger:

- **Durable commit** (`commit_intent`): intent row lands before any external
  effect; unique `(tenant, idempotency_key)` is the transport-key dedup;
  same key + different `payload_hash` → conflict, original untouched.
- **Active-entry guard**: partial unique index `(tenant, account,
  business_hash)` over active entry statuses — a repeated business signal
  with *different* transport keys cannot open a second active entry
  (entries only: `CREATE_TARGET`/`PLACE_ORDER`; cancels/reduces pass).
- **OrderPlan persistence + per-account child order IDs**: deterministic
  `A7<intent-hex>C<index>` client order IDs, unique per `(tenant, account)`.
- **Order state machine** (`states.py`): SUBMITTED → ACKNOWLEDGED →
  PARTIALLY_FILLED → FILLED/CANCELED/REJECTED/EXPIRED, PENDING_CANCEL /
  PENDING_REPLACE, UNKNOWN (exit only via reconciliation-origin events —
  "no blind resubmit" is structural).
- **Transactional outbox** (`intent_outbox`): stable `uuid5` event ids;
  `dispatch_pending`/`replay_outbox` re-delivers the SAME command on
  recovery; the seam dedups on `command_id`.
- **Receipt dedup + exactly-once settlement**: `FillEvent.dedup_key`
  receipts + `cash_movements` keyed `fill:<dedup>:notional|fee`;
  `order_event_receipts` / `fill_receipts` / `cash_movements` are
  append-only at the DB level (triggers, migration 0006).
- **Event projections**: cumulative filled qty, weighted average price,
  fees per child order; intent status rolls up from children.
- **Account freeze**: ambiguous existence without client-ID lookup →
  one active `account_freezes` row; entries on that account get 423 until
  `resolve_freeze` (operator); cancels and reconciliation events still flow.

Contracts (execution-contract resource): `OutboxEvent@1.0`,
`IntentStatusResponse@1.0` (+ nested `ChildOrderStatusView`) in
`src/algobots/contracts/outbox.py` — additive registrations; lock
transition verified (`--check-transition origin/main` ok, 21 contracts).

Migration `0006_execution_ledger` (db-migrations resource): 8 tables,
append-only triggers, partial unique indexes, dialect-branched SQLite/PG.

Broker fault emulator (test double): `tests/execution/ledger/emulator.py` —
accept-before-timeout, connection drop, missing client-ID lookup,
duplicate fill, reordered events, delayed cancel.

## Demo (replay the trace)

```
make demo-A07 PYTHON=python3
```

Writes `artifacts/A07/demo-run.json`:

1. **Duplicate replay** — 50 replays of one request (20 concurrent via
   ThreadPoolExecutor, 30 sequential) + 3 same-business requests with fresh
   keys: exactly 1 intent, `created_exactly_once: true`, 3 guard
   rejections.
2. **Accepted-but-timeout** — commit → plan → stage → dispatch with the
   `accept_before_timeout` fault: intent/child → UNKNOWN, broker holds
   exactly 1 order; recovery replay of the SAME command returns DUPLICATE
   (still 1 order); reconciliation-origin ACCEPTED + fill resolve the child
   to FILLED. Full step trace embedded in the artifact.

## Verification (actual commands and results)

```
make verify-A07 PYTHON=python3
# tests/execution/ledger + tests/packets/A07 -> 33 passed
# acceptance.py -> AC1: PASS (3) AC2: PASS (1) AC3: PASS (4) AC4: PASS (5) AC5: PASS (4)

python3 -m ruff check src/algobots/contracts src/algobots/execution \
  src/algobots/api/migrations/versions/0006_execution_ledger.py \
  tests/execution/ledger tests/packets/A07        # All checks passed

PYTHONPATH=src python3 -m algobots.contracts --check-transition origin/main
# schema lock transition from origin/main ok (21 contracts)

PYTHONPATH=src python3 -m pytest tests -q          # full suite
# only pre-existing failure: tests/demo/test_ledger.py::test_positions_and_orders_endpoints
# (fails identically on clean main @ f7a9dad — demo lane ALG-3281, not A07)
```

Migration hygiene: `upgrade head` / `downgrade 0005` / re-`upgrade` verified
against SQLite; append-only triggers fire on UPDATE and DELETE.

## Limitations (explicit)

- **No network exactly-once claim.** Every guarantee is a durable-commit +
  deduplication property on our side (unique keys, stable identities,
  idempotent settlement). A duplicate external order can still be *observed*
  at a broker that ignores `command_id`/client-order-ID dedup; within one
  ownership epoch we never mint a second command for the same child, and the
  emulator honors that contract. Across an ownership handoff a new epoch
  deliberately mints a NEW command identity for the same
  `client_order_id` (see
  `test_staging_is_idempotent_per_epoch_and_versioned_across_epochs`) —
  broker-side client-order-ID dedup is the backstop there, which A08's seam
  contract should pin explicitly. A07 claims at-most-one *confirmed*
  external order per intent, not network-level exactly-once delivery.
- **No Redis, no lock service.** Correctness rests on database constraints
  alone, per the packet's exclusion.
- **HTTP mount is A22 scope.** `POST /intents` (202 + intent id) and
  `GET /intents/{id}` response shapes exist as contracts
  (`IntentStatusResponse`); the FastAPI router wiring belongs to the api/
  write scope, which A07 does not hold.
- **SQLite in tests; Postgres in production shape.** Migration SQL is
  dialect-branched (SQLite triggers / PG functions) following the 0004
  precedent, but only the SQLite path is exercised by CI tests here.
- **Replace/cancel command emission is A08 scope.** A07 persists
  PENDING_CANCEL/PENDING_REPLACE states and the transition edges; routing
  replacement children through the seam is the next packet's seam work.
- **Reconciliation is operator/scan-driven.** UNKNOWN resolution consumes
  reconciliation-origin `OrderEvent`s (as the Nautilus seam would derive
  them); A07 does not schedule the scan itself.
- **Fills only from seam events.** `demo/ledger.py` remains a
  reconciliation target (P&L recompute), never a fill source — no second
  fill path exists (ADR 0001).
