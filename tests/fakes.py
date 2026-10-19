"""A Redis double with real stream semantics, shared by both legs' tests.

``tests/e2e`` drives the order path over a real server, which is the only way
to measure GATE G1's latency honestly. That run is skipped when the service is
absent, so the *rules* on either side of the transport — consumer-group
redelivery, cursor advance, decoding, idempotency — are asserted here instead,
where they run on every ``pytest`` with no services at all.

The fake is faithful where it matters and nowhere else: the pending list is
real (redelivery is the thing being tested, and a fake that acked eagerly
would test nothing), entry ids sort like real ones, and ``xread`` is
exclusive-after-cursor exactly as the server is. It models one consumer group,
which is all a node ever has.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeRedis:
    """The stream commands the gateway and the node use between them.

    ``XADD``/``XGROUP CREATE``/``XREADGROUP``/``XACK`` are the command leg
    (``algobots:cmd:<node>``); ``XREAD`` and ``SCAN`` are the event leg
    (``trader-*:algobots:events.*``).
    """

    streams: dict[str, list[tuple[str, dict[str, str]]]] = field(default_factory=dict)
    groups: dict[tuple[str, str], int] = field(default_factory=dict)
    #: (stream, group) -> entry ids delivered but not yet acked.
    pending: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    _seq: int = 0

    # --- shared ---------------------------------------------------------------

    def xadd(self, key: str, fields: dict[str, str]) -> str:
        self._seq += 1
        entry_id = f"{self._seq}-0"
        self.streams.setdefault(key, []).append((entry_id, dict(fields)))
        return entry_id

    def scan_iter(self, match: str = "*") -> Iterator[str]:
        yield from (key for key in list(self.streams) if fnmatch.fnmatch(key, match))

    def delete(self, *keys: str) -> int:
        return sum(1 for key in keys if self.streams.pop(key, None) is not None)

    def ping(self) -> bool:
        return True

    # --- the event leg: plain XREAD, exclusive of the cursor -------------------

    def xread(
        self, streams: dict[str, str], count: int = 10, block: int | None = None
    ) -> list[Any]:
        out = []
        for key, cursor in streams.items():
            entries = self.streams.get(key, [])
            batch = [(eid, f) for eid, f in entries if _after(eid, cursor)][:count]
            if batch:
                out.append((key, batch))
        return out

    # --- the command leg: consumer groups with a pending list -----------------

    def xgroup_create(self, key: str, group: str, id: str = "0", mkstream: bool = False) -> None:  # noqa: A002 — redis' own kwarg name
        if (key, group) in self.groups:
            raise RuntimeError("BUSYGROUP Consumer Group name already exists")
        if mkstream:
            self.streams.setdefault(key, [])
        self.groups[(key, group)] = 0
        self.pending[(key, group)] = []

    def xreadgroup(
        self,
        group: str,
        consumer: str,
        streams: dict[str, str],
        count: int = 10,
        block: int | None = None,
    ) -> list[Any]:
        out = []
        for key, cursor in streams.items():
            entries = self.streams.get(key, [])
            if cursor == ">":
                start = self.groups.get((key, group), 0)
                batch = entries[start : start + count]
                self.groups[(key, group)] = start + len(batch)
                self.pending.setdefault((key, group), []).extend(eid for eid, _ in batch)
            else:
                # The pending list: everything delivered and not acked.
                owed = set(self.pending.get((key, group), []))
                batch = [(eid, f) for eid, f in entries if eid in owed][:count]
            if batch:
                out.append((key, batch))
        return out

    def xack(self, key: str, group: str, entry_id: str) -> int:
        owed = self.pending.setdefault((key, group), [])
        if entry_id in owed:
            owed.remove(entry_id)
            return 1
        return 0

    def pending_count(self, key: str, group: str) -> int:
        return len(self.pending.get((key, group), []))

    # --- what the tests read --------------------------------------------------

    def entries(self, key: str) -> list[tuple[str, dict[str, str]]]:
        return list(self.streams.get(key, []))


def _after(entry_id: str, cursor: str) -> bool:
    """``XREAD`` is exclusive of its cursor, and ids sort as (ms, seq)."""
    return _parts(entry_id) > _parts(cursor)


def _parts(entry_id: str) -> tuple[int, int]:
    ms, _, seq = str(entry_id).partition("-")
    return int(ms or 0), int(seq or 0)


__all__ = ["FakeRedis"]
