"""Admission errors (A08). ``AdmissionError`` extends the ledger error base
so one except-clause covers the whole execution spine."""

from algobots.execution.ledger.errors import LedgerError

__all__ = [
    "AdmissionDenied",
    "AdmissionError",
    "OvercommitRejected",
    "ReservationNotFound",
]


class AdmissionError(LedgerError):
    """Base: admission refused or malformed."""


class AdmissionDenied(AdmissionError):
    """Policy or controls denied the proposal (fail closed)."""

    def __init__(self, decision):
        self.decision = decision
        super().__init__(f"{decision.decision} [{decision.rule}]: {decision.reason}")


class OvercommitRejected(AdmissionError):
    """The account pool cannot fund the reservation (race or shortage)."""

    def __init__(self, requested, available):
        self.requested = requested
        self.available = available
        super().__init__(
            f"reservation {requested} would overcommit the account pool "
            f"({available} unreserved)"
        )


class ReservationNotFound(AdmissionError):
    pass
