"""Ledger service errors. Status codes are HTTP-shaped so the future /intents
mount (A22) maps them 1:1 without re-triaging semantics.
"""

from __future__ import annotations

__all__ = [
    "AccountFrozen",
    "AmbiguousSubmit",
    "GuardRejected",
    "IdempotencyConflict",
    "IllegalTransitionError",
    "IntentNotFound",
    "LedgerError",
]


class LedgerError(Exception):
    code: str = "ledger_error"
    status_code: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class IdempotencyConflict(LedgerError):
    """Same idempotency key, different payload: rejected, original untouched (AC2)."""

    code = "idempotency_key_conflict"
    status_code = 409


class AccountFrozen(LedgerError):
    """Account is frozen on ambiguous order existence until operator resolution (AC5)."""

    code = "account_frozen"
    status_code = 423


class GuardRejected(LedgerError):
    """Active-entry guard: repeated business signal while an entry is still active."""

    code = "active_entry_guard"
    status_code = 409


class IntentNotFound(LedgerError):
    code = "intent_not_found"
    status_code = 404


class IllegalTransitionError(LedgerError):
    code = "illegal_transition"
    status_code = 409


class AmbiguousSubmit(Exception):
    """Raised by an execution seam when delivery outcome is unknown (timeout,
    connection drop, missing client-ID lookup). The command MAY exist remotely;
    the caller must mark UNKNOWN, never blind-resubmit a fresh command.
    """

    def __init__(self, reason: str, *, lookup_available: bool = True) -> None:
        super().__init__(reason)
        self.reason = reason
        self.lookup_available = lookup_available
