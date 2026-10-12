"""Deterministic recorded market-data fixtures and local replay adapters (A05 item 2).

Adapters are source-agnostic: a recording is JSONL where each line is one
:class:`~algobots.contracts.marketdata.MarketSnapshot` payload. Every line
records event time, available time, receive time, source, sequence,
entitlement and quality flags, so replay can gate on *availability*, not just
event time (acceptance case 4). Raw lines are retained verbatim on the
:class:`Recording` for correction/replay recovery — parse errors never
overwrite the original record.
"""

from __future__ import annotations

import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from algobots.contracts.marketdata import MarketSnapshot

__all__ = ["RecordingError", "Recording", "load_recording", "recordings_path"]


class RecordingError(ValueError):
    """The fixture file violates the recording invariants."""


class Recording:
    """Validated snapshots plus the raw JSONL lines they came from."""

    def __init__(self, snapshots: tuple[MarketSnapshot, ...], raw: tuple[str, ...]) -> None:
        self._snapshots = snapshots
        self.raw = raw
        by_stream: dict[tuple[str, str], list[MarketSnapshot]] = defaultdict(list)
        for snap in snapshots:
            by_stream[(snap.instrument_id, snap.source)].append(snap)
        for (instrument_id, source), stream in by_stream.items():
            seqs = [s.sequence for s in stream]
            if seqs != sorted(seqs) or len(set(seqs)) != len(seqs):
                raise RecordingError(
                    f"sequences for {instrument_id}/{source} are not strictly increasing: {seqs}"
                )
            by_seq = {s.sequence: s for s in stream}
            for snap in stream:
                if snap.correction_of is not None:
                    target = by_seq.get(snap.correction_of)
                    if target is None or target.sequence >= snap.sequence:
                        raise RecordingError(
                            f"{instrument_id}/{source} seq {snap.sequence} corrects unknown or "
                            f"later sequence {snap.correction_of}"
                        )
        self._by_stream = dict(by_stream)

    def snapshots(self, instrument_id: str) -> tuple[MarketSnapshot, ...]:
        """All snapshots of one instrument across sources, ordered by (available, sequence)."""
        out = [s for stream in self._by_stream.values() for s in stream
               if s.instrument_id == instrument_id]
        return tuple(sorted(out, key=lambda s: (s.available_time, s.sequence)))

    def instrument_ids(self) -> tuple[str, ...]:
        return tuple(sorted({s.instrument_id for s in self._snapshots}))

    @property
    def snapshots_all(self) -> tuple[MarketSnapshot, ...]:
        return self._snapshots

    @classmethod
    def load(cls, path: Path) -> Recording:
        raw = tuple(line for line in path.read_text().splitlines() if line.strip())
        snapshots: list[MarketSnapshot] = []
        for lineno, line in enumerate(raw, start=1):
            try:
                snapshots.append(MarketSnapshot.model_validate(json.loads(line)))
            except Exception as exc:  # noqa: BLE001 — annotate, keep the raw line for recovery
                raise RecordingError(f"{path.name}:{lineno}: {exc}") from exc
        return cls(tuple(snapshots), raw)


def recordings_path() -> Path:
    return Path(__file__).with_name("fixtures") / "recordings.jsonl"


@lru_cache(maxsize=1)
def load_recording(path: Path | None = None) -> Recording:
    """The bundled deterministic recording (or one at ``path``)."""
    return Recording.load(path if path is not None else recordings_path())
