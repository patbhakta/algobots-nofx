"""Source-delete tombstones (A14-2).

Removing a knowledge source never destructively rewrites the vault or the
lineage store (packet exclusion): removal is recorded as a tombstone, the
source's ACL is revoked, and every online surface (search results, caches,
live index view) must stop exposing the source within the declared
propagation window. The default target is 60 seconds.

`propagated_at` is stamped when the invalidation hooks finish; a tombstone
whose `propagated_at` exceeds `propagation_deadline` is a defect the timed
test exists to catch before it ships.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from algobots.knowledge.ingest.models import utcnow_iso

# Declared propagation window target (seconds): exposure must cease within
# this budget after a tombstone is created.
DEFAULT_PROPAGATION_SECONDS = 60.0


@dataclass(frozen=True)
class Tombstone:
    source_id: str
    reason: str
    created_at: str
    propagation_seconds: float
    propagation_deadline: str  # ISO; exposure beyond this is a defect
    revoked_by: str | None = None
    propagated_at: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "reason": self.reason,
            "created_at": self.created_at,
            "propagation_seconds": self.propagation_seconds,
            "propagation_deadline": self.propagation_deadline,
            "revoked_by": self.revoked_by,
            "propagated_at": self.propagated_at,
        }


def make_tombstone(
    source_id: str,
    *,
    reason: str,
    revoked_by: str | None = None,
    propagation_seconds: float = DEFAULT_PROPAGATION_SECONDS,
) -> Tombstone:
    now = datetime.now(UTC)
    deadline = now + timedelta(seconds=propagation_seconds)
    return Tombstone(
        source_id=source_id,
        reason=reason,
        created_at=now.isoformat(),
        propagation_seconds=propagation_seconds,
        propagation_deadline=deadline.isoformat(),
        revoked_by=revoked_by,
    )


def stamp_propagated(tombstone: Tombstone, *, at: str | None = None) -> Tombstone:
    """Return the tombstone with its propagation completion stamped."""
    return Tombstone(
        source_id=tombstone.source_id,
        reason=tombstone.reason,
        created_at=tombstone.created_at,
        propagation_seconds=tombstone.propagation_seconds,
        propagation_deadline=tombstone.propagation_deadline,
        revoked_by=tombstone.revoked_by,
        propagated_at=at or utcnow_iso(),
    )


def is_active(tombstone: Tombstone | None) -> bool:
    """A tombstone is active from creation; only explicit records deactivate."""
    return tombstone is not None


def parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
