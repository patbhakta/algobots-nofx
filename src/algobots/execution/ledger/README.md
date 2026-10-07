# A07 — Intent ledger, deduplication, and order state (ALG-3103)

Durable Intent → OrderPlan → per-account child orders → transactional outbox →
broker-seam events → receipts/projections, with three families of protection
against duplicates and ambiguity:

1. **Transport-key dedup (AC1/AC2)** — unique `(tenant, idempotency_key)` on
   `execution_intents`. Concurrent identical commits collapse to the row that
   won the insert race; a same-key/different-payload commit is a 409 conflict
   that leaves the original untouched.
2. **Active-entry guard** — a partial unique index over
   `(tenant, account, business_hash)` while the intent is in an active status.
   The business fingerprint covers account, deployment, action and payload —
   *not* the idempotency key — so a repeated business signal with a fresh
   transport key still cannot open a second active entry on the same account.
3. **Exactly-once settlement (AC4)** — fills dedup on `FillEvent.dedup_key`
   (environment + account + broker fill id / composite key); cash movements
   are keyed `fill:<dedup>:notional|fee`, so replays and redeliveries settle
   once. Reordered batches (fill before its acknowledgment) are pumped to a
   fixpoint by `apply_events`.

## UNKNOWN and no blind resubmit (AC3)

When the seam reports an ambiguous delivery (`AmbiguousSubmit`), the child
order enters UNKNOWN and the outbox row stays PENDING with its stable event
id. Recovery replays *the same command* (same `command_id`, same client order
ID); the seam deduplicates on it. The state machine structurally refuses
UNKNOWN → live without a reconciliation-origin observation, and
`stage_commands` refuses to mint a new command for an UNKNOWN child.

## Account freeze (AC5)

Ambiguous existence *without* a client-ID lookup freezes the account
(`account_freezes`, one active row per account). While frozen, entry intents
on that account are rejected (423) until an operator resolution
(`resolve_freeze`) closes the freeze; cancels and reconciliations still flow.

## Spine constraint (ADR 0001)

The ledger records orders/fills only from `OrderEvent`/`FillEvent` contracts —
the shapes the Nautilus `ExecutionClient` seam derives. Fills come from
`OrderFilled` events only; `algobots.demo.ledger` stays a reconciliation
target, never a fill source. The `AdapterNotAuthorized` guard from A06 is
untouched.

## Scope notes

The HTTP mount (`POST /intents`, `GET /intents/{id}`) is A22 scope; the
response shapes are already contracts (`IntentStatusResponse`, `OutboxEvent`
in `algobots.contracts.outbox`). We make no claim of network exactly-once
delivery — every guarantee above is a deduplicated, durable-commit property
on our side. No Redis lock is involved anywhere: correctness rests on
database constraints alone.

## Modules

- `states.py` — order/intent state machines (`LEGAL` edges, rollup)
- `errors.py` — HTTP-shaped ledger errors + `AmbiguousSubmit` (seam signal)
- `models.py` — ORM tables owned by migration `0006`
- `service.py` — commit/plan/stage/dispatch/apply/freeze/resolve/get_intent
