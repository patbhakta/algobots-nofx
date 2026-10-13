"""Non-Markdown assets: pending-extraction queue + approved processors (A14-1).

No universal support claim. An asset is registered as a queue entry naming
the CAPABILITY it needs ("pdf-text", "ocr", "table-parse"); extraction runs
only when an explicitly approved processor for that capability has been
provided. With none approved, the entry stays visible as
``no_approved_processor`` — reported, never silently dropped, never
substituted with invented text. Asset types outside the capability table are
queued as ``unsupported`` and are never routed at all.

This slice ships ZERO processors by design; the registry starts empty and
callers (tests, later slices) inject explicitly approved ones.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from algobots.knowledge.ingest.models import (
    EXTRACTION_FAILED,
    EXTRACTION_NO_PROCESSOR,
    EXTRACTION_PROCESSED,
    PendingExtraction,
    QuarantineRecord,
    utcnow_iso,
)


@dataclass(frozen=True)
class ExtractionResult:
    """What one approved processor actually got out of an asset."""

    processor: str
    text: str  # extracted text — verbatim model output, never invented here
    quality: dict[str, Any]  # e.g. {"ocr_confidence": 0.93, "text_chars": 1204}


class AssetProcessor(Protocol):
    """A processor implementation. `capabilities` is the explicit approval
    surface: the router only ever calls processors for those capabilities."""

    name: str
    capabilities: frozenset[str]

    def extract(self, path: Path) -> ExtractionResult: ...  # pragma: no cover


@dataclass(frozen=True)
class SimpleProcessor:
    """Test/DI processor backed by plain callables."""

    name: str
    capabilities: frozenset[str]
    _extract: Callable[[Path], ExtractionResult]

    def extract(self, path: Path) -> ExtractionResult:
        return self._extract(path)


class ApprovedProcessors:
    """The only routing surface: processors MUST be registered here to run."""

    def __init__(self, processors: tuple[AssetProcessor, ...] = ()) -> None:
        by_name: dict[str, AssetProcessor] = {}
        for p in processors:
            if p.name in by_name:
                raise ValueError(f"duplicate processor name: {p.name!r}")
            if not p.capabilities:
                raise ValueError(f"processor {p.name!r} approves no capabilities")
            by_name[p.name] = p
        self._by_name = by_name
        self._by_capability: dict[str, AssetProcessor] = {}
        for p in processors:
            for cap in p.capabilities:
                existing = self._by_capability.get(cap)
                if existing is not None and existing.name != p.name:
                    raise ValueError(
                        f"capability {cap!r} approved for both "
                        f"{existing.name!r} and {p.name!r}"
                    )
                self._by_capability[cap] = p

    def find(self, capability: str) -> AssetProcessor | None:
        return self._by_capability.get(capability)

    def names(self) -> list[str]:
        return sorted(self._by_name)


def route_pending(
    store,
    source_id: str,
    approved: ApprovedProcessors,
) -> list[PendingExtraction]:
    """Run every still-pending queue entry of one source through its
    approved processor. Reads only from the immutable snapshot copies.
    Entries without an approved processor are marked ``no_approved_processor``
    and stay visible; a processor failure marks the entry ``failed`` with the
    error surfaced — text is only ever recorded from a successful run."""
    routed: list[PendingExtraction] = []
    for entry in store.pending_extractions(source_id):
        if entry.status != "pending":
            continue
        if entry.capability == "unknown":
            continue  # unsupported types are never routed (no claim made)
        processor = approved.find(entry.capability)
        if processor is None:
            entry.status = EXTRACTION_NO_PROCESSOR
            entry.error = (
                f"no approved processor for capability {entry.capability!r}"
            )
            entry.updated_at = utcnow_iso()
            store.save_pending_extraction(entry)
            routed.append(entry)
            continue
        snapshot_path = _snapshot_path_for(store, entry)
        try:
            result = processor.extract(snapshot_path)
        except Exception as exc:  # noqa: BLE001 - failure is data, surfaced
            entry.status = EXTRACTION_FAILED
            entry.processor = processor.name
            entry.error = f"{type(exc).__name__}: {exc}"
            entry.updated_at = utcnow_iso()
            store.save_pending_extraction(entry)
            routed.append(entry)
            store.append_quarantine(
                QuarantineRecord(
                    record_id=f"qx-{entry.entry_id}-{processor.name}",
                    source_id=source_id,
                    path=entry.path,
                    reason="extraction_failed",
                    message=(
                        f"processor {processor.name!r} failed on {entry.path}: "
                        f"{type(exc).__name__}: {exc} — no text substituted"
                    ),
                    snapshot_id=None,
                    content_hash=entry.content_hash,
                    occurred_at=utcnow_iso(),
                )
            )
            continue
        entry.status = EXTRACTION_PROCESSED
        entry.processor = result.processor
        entry.quality = dict(result.quality)
        entry.extracted_text = result.text
        entry.error = None
        entry.updated_at = utcnow_iso()
        store.save_pending_extraction(entry)
        routed.append(entry)
    return routed


def _snapshot_path_for(store, entry: PendingExtraction) -> Path:
    """Locate the asset's snapshot copy from its version record."""
    version = store.get_version(entry.version_id)
    if version is None:
        raise LookupError(f"no version {entry.version_id} for pending entry")
    return store.snapshot_dir(entry.source_id, version.snapshot_id) / entry.path
