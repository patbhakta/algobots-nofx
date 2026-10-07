"""algobots.execution.admission — account admission serialization (A08).

The single serialization point where concurrent strategies commit claims on
shared cash/inventory. See :mod:`algobots.execution.admission.service`.
"""

from algobots.execution.admission.errors import (
    AdmissionDenied,
    AdmissionError,
    OvercommitRejected,
    ReservationNotFound,
)
from algobots.execution.admission.service import (
    AdmissionResult,
    admit_entry,
    available_cash,
    consume_on_fill,
    deposit,
    expire_reservations,
    get_controls,
    get_or_create_admission,
    mark_uncertain,
    record_mark,
    release_reservation,
    resize_reservation,
    set_controls,
    set_inventory,
    state_snapshot,
)

__all__ = [
    "AdmissionDenied",
    "AdmissionError",
    "AdmissionResult",
    "OvercommitRejected",
    "ReservationNotFound",
    "admit_entry",
    "available_cash",
    "consume_on_fill",
    "deposit",
    "expire_reservations",
    "get_controls",
    "get_or_create_admission",
    "mark_uncertain",
    "record_mark",
    "release_reservation",
    "resize_reservation",
    "set_controls",
    "set_inventory",
    "state_snapshot",
]
