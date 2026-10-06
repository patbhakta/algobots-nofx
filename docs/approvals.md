# Approval Queue & Action Ledger (S4.3 — [ALG-3092](/ALG/issues/ALG-3092))

Human-in-the-loop gate for live-bound orders: semi-auto accounts park every
order for a human verdict, decisions/expiries/broadcast outcomes land in an
append-only action ledger enforced by database triggers, and each action
carries a persisted park→decision latency.

## Parking rule (paper-only standing law)

- `POST /api/orders` on an account with `mode = semi_auto` creates the order
  with status **`parked`** — never `pending`/`submitted` — and returns the
  queued request id in the **`X-Approval-Request-Id`** response header
  (`src/algobots/api/routers/resources.py` → `parks()` /
  `park_order()` in `src/algobots/api/approvals/service.py`).
- Paper (and non-semi-auto) accounts are unchanged: orders are created
  `pending` exactly as before.
- Parked orders cannot be deleted: `DELETE /api/orders/{id}` only allows
  `pending`/`cancelled`/`rejected` → 409 for `parked`. A parked order leaves
  the queue only through a verdict or expiry sweep, which releases the order
  row to its verdict-mapped status (`approved → submitted`,
  `rejected`/`expired → cancelled`).

## Queue state machine

```
parked ──► approved
   │ └───► rejected
   └─────► expired   (sweep only)
```

- Legal edges live in `LEGAL_TRANSITIONS`; `decide_request()` applies them via
  `_transition()`, which raises **409** on anything illegal (decided requests
  are terminal; there is no un-decide).
- `POST /api/approvals/{request_id}/decide` with
  `{"verdict": "approved" | "rejected", "reason": "..."}` records the human
  verdict. Reject **requires** a reason → **422** otherwise; the reason is
  persisted on the request and in the ledger row.
- Expiry is reachable only via the sweep — never the decide endpoint.
  `POST /api/approvals/sweep-expiry` moves overdue parked requests (TTL
  `PARK_TTL_SECONDS = 300` s) to `expired`, cancels their orders, and is
  idempotent: already-decided requests are never touched.
- Tenancy follows the house rule: another user's requests are
  indistinguishable from missing ones (404).

## Latency

- Every decision records `latency_ms` = park → decision timestamps, persisted
  **on the request row and in the ledger row** for that action. Expiry records
  the same measure at sweep time; broadcast records decision → report latency.
- Deterministic by injection: `parked_at`/`decided_at` are injectable, so
  `test_latency_math_park_to_decision_deterministic`
  (`tests/approvals/test_approvals_api.py`) proves the arithmetic with a fixed
  1500 ms delta. (SQLite returns naive datetimes; `aware_utc()` restores
  tzinfo losslessly so the math stays sound.)

## Append-only action ledger

- Migration `0004_approvals_action_ledger` (`src/algobots/api/migrations/versions/`)
  installs **BEFORE UPDATE / BEFORE DELETE triggers** on `action_ledger` for
  both SQLite and Postgres that raise `action_ledger is append-only`. No
  application path and no ad-hoc SQL can rewrite history; there is
  deliberately no `updated_at` column.
- `append_ledger()` in `service.py` is the ONLY writer. Rows carry `action`
  (`order_parked`, `approval_approved`, `approval_rejected`,
  `approval_expired`, `broadcast_reported`), `subject_type`/`subject_id`,
  `actor_id`, `reason`, `latency_ms`, and a canonical `detail_json`.
- Distinct from the S0.2 middleware `audit_log` table
  (see [control-plane.md](control-plane.md)): `audit_log` records HTTP
  mutations (method/path/status/request-id); `action_ledger` records
  approval-domain actions with reason and latency per action.
- Proof: `tests/approvals/test_action_ledger.py` — raw SQL UPDATE, raw SQL
  DELETE, ORM UPDATE, and ORM DELETE all fail; one test additionally asserts
  the ledger is populated with actor/reason/latency and stays distinct from
  `audit_log`.
- Read the tail at `GET /api/approvals/ledger?limit=…` (1–1000, default 200,
  newest first).

## Broadcast reporting

Venue outcomes of dispatching an approved request fold
`(total, sent, queued)` into:

| State | Meaning |
| --- | --- |
| `sent` | fully executed at the venue (`sent ≥ total`) |
| `part_sent` | some filled, nothing queued |
| `part_queued` | partial fill with remainder queued (also the partial-queue default) |
| `queued` | nothing executed, fully queued |

- `POST /api/approvals/{request_id}/broadcast` with
  `{"sent_qty", "queued_qty", "reason?"}`; one outcome row per request
  (unique index, second report → 409).
- Validation: **409** unless the request is `approved`; **422** for negative
  quantities, both-zero, or `sent_qty + queued_qty` exceeding the parked
  order qty. The computed state and the decision→report `latency_ms` land on
  the row and in the ledger.

## Dashboard inbox

`algobots.dashboard.approvals.approval_inbox_snapshot(db, user_id)` builds
the secret-free model behind the approval inbox (following the
`dashboard/accounts.py` pattern); `render_approvals_html(snapshot)` renders
it as an escaped HTML fragment with no frontend stack. The snapshot shows:

- the **parked queue** — symbol/side/qty/account, park reason, live wait
  (`age_ms`), expiry timestamp;
- **decided items** — verdict, decision reason, persisted park→decision
  `latency_ms`;
- **totals** (`requests`/`parked`/`approved`/`rejected`/`expired`) and the
  **action-ledger tail** (latest 20 by default).

## Observability

Structured, secret-free events on logger `algobots.api.approvals.*` —
`order_parked`, `approval_decided`, `approval_expiry_swept`,
`broadcast_reported` — carrying ids, symbols, states, and latencies only.
Tests assert no secret material ever appears in responses, logs, or the DB.

## Endpoint map

| Route | Verbs |
| --- | --- |
| `/api/approvals` (`?status=`, `?order_id=`) | GET |
| `/api/approvals/{request_id}` | GET |
| `/api/approvals/{request_id}/decide` | POST |
| `/api/approvals/{request_id}/broadcast` | POST |
| `/api/approvals/sweep-expiry` | POST |
| `/api/approvals/ledger` (`?limit=`) | GET |

## Migration & tests

`alembic upgrade head` applies `0004_approvals_action_ledger`
(`approval_requests`, `broadcasts`, `action_ledger` + immutability triggers).

```bash
pytest tests/approvals/        # parking, state machine, latency, ledger, inbox
```
