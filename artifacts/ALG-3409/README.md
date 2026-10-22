# ALG-3409 — denial egress and acknowledgement after engine execution

Verified on the paper deployment at `100.82.57.72:8210`, 2026-10-22 08:47 UTC.
The node image runs pinned Nautilus 2.0.0rc6, `Environment.SANDBOX`.

## Change

rc6 `Strategy.submit_order` enqueues work and returns while the order is still
`INITIALIZED`. `CommandStream` now accepts a `before_ack` hook. The paper node
checks engine state there and raises while execution is queued, leaving the
entry in the consumer group's pending list. Its next poll retries pending
entries first; a cached order prevents another submission. Queued cancellations
also stay pending until confirmation.

A `DENIED` order explicitly publishes its actual cached `OrderDenied` event
through `EventEgress` before XACK. Failed Redis publication leaves it pending.
The exported timestamps use ISO strings because the deployed gateway predates
the rc6 nanosecond normalization. The first live probe revealed that mismatch;
its two incompatible test events were replaced with corrected ISO envelopes,
and the gateway recovered. Other events and existing orders were preserved.

## Acceptance evidence

Raw output: [delivery-smoke.jsonl](delivery-smoke.jsonl).
Reproducer: `scripts/rc6_delivery_smoke.py`, run on the paper Docker host.
It uses the configured gateway session internally without printing credentials,
stops only `nautilus-node`, and always starts it again.

- `alg3409-denied-096e594182`, qty 100: GET returned `rejected`, reason
  `QUANTITY_BELOW_MINIMUM: effective=100, min=1000`.
- `alg3409-restart-096e594182`, qty 1000: stopped the node, admitted the command,
  delivered it with XREADGROUP to the real stable `NAUTILUS-PAPER` consumer;
  XPENDING was **1**. Started the node; it recovered the pending command and
  emitted `OrderFilled` at **1.12161**, trade `T-e1cf2e032b2b5dcc-001`.
  XPENDING became **0** only after execution.
- 71 focused tests passed (`tests/node` and `tests/gateway/test_rc6_wire.py`).
  Ruff passed on all changed Python files. Regression tests cover initialized
  orders, denial egress failure/retry, cancellations, and pending replay.

Runtime code deployed/pushed as `1a674b9`; subsequent commit adds this evidence,
the repeatable host smoke, and hook documentation.

## Separate finding and limits

The deployed gateway still lacks the existing rc6 variant-envelope parser,
so the successfully executed restart probe remains `admitted` in that gateway.
Follow-up [ALG-3410](/ALG/issues/ALG-3410) owns deploying that compatibility code
and verifying fills through GET. The denial path works with its existing parser.

This change prevents acknowledgement of queued work; it does not reconstruct
commands already acknowledged by the old code. It does not add persistent
sandbox venue/cache state or claim exactly-once execution across a crash after
a fill and before XACK.
