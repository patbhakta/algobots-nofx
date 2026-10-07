# A08 — Demo & Limitations (ALG-3104)

## What was built

`src/algobots/risk/` — the deterministic policy rail (extends the S1.2 surface):

- **Policy engine** (`policy.py`): `evaluate_proposal` is a PURE function —
  same policy + proposal + state snapshot + clock → same `RiskDecision`.
  Precedence is frozen in `contracts.risk.RISK_RULE_PRECEDENCE`
  (permission → stale state → account control → daily loss → rate →
  deployment budget → concentration → gross exposure → max order → funds);
  the first rule that fires is the decision. Clamps shrink to the largest
  admissible size with the rule named in the reason (an AI proposal asking
  for more gets a deterministic clamp, never a silent pass). Risk-reducing
  actions are exempt from every entry-only denial.
- **Daily loss** (`daily.py`): trading day = local calendar day in the
  account's IANA timezone; components are explicit (realized, unrealized at
  marked positions, deposits/withdrawals adjust the equity reference and are
  never P&L); every mark carries its quality and `loss >= cap` trips
  (envelope convention).
- **Controls** (`controls.py`): entry pause / cancel-entries / reduce-only /
  separately-authorized flatten (actor + bounded window, never implied by a
  pause); `protection_status` lists every protective order with its working
  state — pausing entries never removes stops. `validate_protective_order`
  enforces direction (stop must reduce the position), quantity (≤ |position|,
  no over-hedge) and broker capability (`Capabilities` protection options;
  unknown = disabled). Exits are NOT exempt from these venue constraints.

`src/algobots/execution/admission/` — account admission serialization:

- **Serialization point**: the account pool row (`account_admissions`) is
  reserved through a bounded compare-and-swap on its `version` epoch; the
  funds invariant (`reserved + required <= available`) is checked in exact
  Decimal arithmetic on the row the CAS read. Two simultaneous $700 entries
  on a $1,000 pool cannot both win — sequentially the policy's funds rule
  denies (the snapshot reports committed reservations), under a race the CAS
  does. No SQL arithmetic on money text columns (engine-portable).
- **Reservation store** (`reservations`): one CASH row per plan child
  (principal + fee/slippage buffer bps from the policy); the pool claim is
  exactly the sum of row claims. States HELD / UNCERTAIN / CONSUMED /
  RELEASED with DB-level CHECKs (valid states; a RELEASED row must carry its
  reason: reconciled rejection / canceled / filled / expired / operator
  correction).
- **Lifecycle**: release only on reconciled rejection, cancellation, fill,
  expiry (`valid_until`) or explicit operator correction; partial fill
  resizes the claim; fills consume (settled notional + fees leave the pool,
  unused buffer returns). UNKNOWN orders and cancel-pending remainders go
  UNCERTAIN and RETAIN their obligations — they can never fund a new
  conflicting entry.
- **A07 integration**: `admit_entry` commits the intent and attaches the plan
  (with reservation contracts) in the SAME transaction as the reservation —
  a funded reservation without an intent cannot exist, and any store failure
  rolls the whole admission back (fail closed for new exposure).
- **Account state**: per-account instrument marks (price + quality +
  observed_at) feed the stale-state gate; `state_snapshot` builds the
  policy's view net of active reservations.

Contracts (execution-contract resource): `RiskPolicyVersion@1.0` and
`RiskDecision@1.0` (+ nested constraint/permission models) in
`src/algobots/contracts/risk.py` — additive registrations; lock transition
verified (`--check-transition origin/main` ok, 23 contracts). `OrderPlan@1.0`
and `Reservation@1.0` pins untouched.

Endpoints (execution-contract resource): `GET/PUT /api/accounts/{id}/controls`,
`POST /api/accounts/{id}/controls/flatten[/cancel]`, `POST /api/risk/preview`
(tenant-scoped; preview is the same deterministic engine with NO reservation
and NO intent; flatten authorization is deliberately not settable through
the bulk controls shape).

Migration `0007_account_risk_admission` (db-migrations resource): 5 tables
(pools, inventories, reservations, controls, marks) with the lifecycle
CHECKs and the plan-child unique index.

## Demo (replay the trace)

```
make demo-A08 PYTHON=python3     # -> artifacts/A08/demo-run.json
make verify-A08 PYTHON=python3   # -> artifacts/A08/test-results + acceptance.json
```

The demo trace shows:

1. **Race**: $1,000 pool, two concurrent $700 entries (separate sessions,
   real threads) → exactly one ADMITTED, one REJECTED
   (`insufficient_funds`), pool invariant `reserved == sum(active claims)
   <= available` holding at every step; a reconciled release returns funds.
2. **Entry pause without removing stops**: entries paused → next entry
   DENIED (`account_control`), the working stop stays working and is listed
   in the protection status; resume → entry admitted.
3. **Stale state**: a 120s-old STALE_CACHE mark → new risk DENIED
   (`stale_state`) with protections still visible; a fresh REALTIME mark →
   admitted.

## Limitations

- **Advisory serialization on SQLite**: the CAS serializes admissions
  correctly on both SQLite and PostgreSQL, but on SQLite heavy write
  concurrency surfaces as retryable busy errors (bounded retries in the
  loop). The production posture is PostgreSQL, where the CAS row-lock is
  native.
- **No margin/options risk engine** (per exclusions): the `MARGIN`
  reservation kind exists in the contract but admission logic implements
  CASH (and the inventory store for SELL inventory) only. Margin budgets are
  out of scope by design.
- **Rate limits are snapshot-fed**: the policy evaluates `orders_last_minute`
  / `entries_today` from the proposal's snapshot state; a persistent
  sliding-window recorder per account is provided by the S1.2
  `RateBreakers`, which the integrated engine wires in at dispatch. The
  policy stays pure.
- **Daily loss inputs**: realized P&L and equity reference are supplied by
  the caller (ledger settlements + account snapshot); A08 computes and
  reports, it does not re-derive fills (A07 owns settlement).
- **Preview is snapshot-based**: `/risk/preview` evaluates against an
  operator-supplied state snapshot, not a live read of the admission store —
  it is a what-if rail, never an admission.
- **Exits not exempt from venue constraints**: protective-order validation
  runs on every risk-reducing submission the controls layer sees; an exit
  the venue cannot express (unsupported order type/protection) is refused
  with the capability reason.
