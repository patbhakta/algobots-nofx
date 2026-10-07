"""algobots.execution.ledger — durable intent ledger (A07, ALG-3103).

Public surface (the intent -> plan -> reservation -> command route; see the
``execution-contract`` resource in docs/repository-map.json):

- ``states``:     order/intent state machines; UNKNOWN is only exit-able via
                  reconciliation-origin observations (no blind resubmit)
- ``service``:    ``commit_intent`` (durable commit + transport dedup +
                  active-entry guard), ``attach_plan``/``stage_commands``
                  (per-account child IDs + transactional outbox),
                  ``dispatch_pending``/``replay_outbox`` (stable-identity
                  replay), ``apply_order_event``/``apply_fill_event``/
                  ``apply_events`` (receipt dedup, idempotent settlement,
                  projections), freeze/resolve, ``get_intent``
                  (the /intents/{id} view contract)
- ``models``:     ORM tables owned by migration 0006
- ``errors``:     HTTP-shaped ledger errors
"""

from algobots.execution.ledger import models, states
from algobots.execution.ledger.errors import (
    AccountFrozen,
    AmbiguousSubmit,
    GuardRejected,
    IdempotencyConflict,
    IntentNotFound,
    LedgerError,
)
from algobots.execution.ledger.service import (
    CommitResult,
    DispatchReport,
    EventApplyResult,
    apply_events,
    apply_fill_event,
    apply_order_event,
    attach_plan,
    business_fingerprint,
    commit_intent,
    dispatch_pending,
    freeze_account,
    get_intent,
    mark_unknown,
    replay_outbox,
    request_cancel,
    request_replace,
    resolve_freeze,
    stage_commands,
)

__all__ = [
    "AccountFrozen",
    "AmbiguousSubmit",
    "CommitResult",
    "DispatchReport",
    "EventApplyResult",
    "GuardRejected",
    "IdempotencyConflict",
    "IntentNotFound",
    "LedgerError",
    "apply_events",
    "apply_fill_event",
    "apply_order_event",
    "attach_plan",
    "business_fingerprint",
    "commit_intent",
    "dispatch_pending",
    "freeze_account",
    "get_intent",
    "mark_unknown",
    "models",
    "request_cancel",
    "request_replace",
    "resolve_freeze",
    "replay_outbox",
    "stage_commands",
    "states",
]
