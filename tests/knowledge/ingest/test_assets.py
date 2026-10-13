"""AC4 — non-Markdown assets: pending-extraction queue, approved processors
only, quality flags, and NO universal support claim (A14-1).
"""

from __future__ import annotations

import pytest

from algobots.knowledge.ingest import (
    ApprovedProcessors,
    ExtractionResult,
    SimpleProcessor,
    route_pending,
)
from conftest import register


def _proc(name: str, caps: tuple[str, ...], text: str = "extracted", quality=None):
    return SimpleProcessor(
        name=name,
        capabilities=frozenset(caps),
        _extract=lambda path: ExtractionResult(
            processor=name, text=text, quality=quality or {"text_chars": len(text)}
        ),
    )


def _queue(make_vault, store, ingest, *names):
    root, _ = make_vault(*names)
    source = register(ingest, store, root)
    report = ingest.run(source)
    return source, report


def test_assets_queued_with_capability(make_vault, store, ingest):
    source, report = _queue(
        make_vault, store, ingest, "assets/sample-table.csv", "assets/fake-scan.png"
    )
    entries = {e.path: e for e in store.pending_extractions(source.source_id)}
    assert entries["sample-table.csv"].capability == "table-parse"
    assert entries["fake-scan.png"].capability == "ocr"
    assert all(e.status == "pending" for e in entries.values())
    assert report.assets_queued


def test_unknown_type_queued_unsupported_never_routed(make_vault, store, ingest):
    source, _ = _queue(make_vault, store, ingest, "assets/mystery.bin")
    entries = store.pending_extractions(source.source_id)
    assert len(entries) == 1
    assert entries[0].capability == "unknown"
    assert entries[0].status == "unsupported"

    routed = route_pending(store, source.source_id, ApprovedProcessors(()))
    assert routed == []  # unsupported types are never routed at all


def test_no_approved_processor_stays_visible(make_vault, store, ingest):
    source, _ = _queue(make_vault, store, ingest, "assets/sample-table.csv")
    routed = route_pending(store, source.source_id, ApprovedProcessors(()))
    assert len(routed) == 1
    assert routed[0].status == "no_approved_processor"
    assert "no approved processor" in routed[0].error
    stored = store.pending_extractions(source.source_id)[0]
    assert stored.status == "no_approved_processor"  # visible, not dropped


def test_approved_processor_runs_and_quality_flags_stored(make_vault, store, ingest):
    source, _ = _queue(make_vault, store, ingest, "assets/fake-scan.png")
    seen_paths = []

    def _extract(path):
        seen_paths.append(path)
        return ExtractionResult(
            processor="test-ocr",
            text="OCR text",
            quality={"ocr_confidence": 0.93, "text_chars": 8},
        )

    approved = ApprovedProcessors(
        (SimpleProcessor(name="test-ocr", capabilities=frozenset({"ocr"}), _extract=_extract),)
    )
    routed = route_pending(store, source.source_id, approved)
    assert routed[0].status == "processed"
    assert routed[0].processor == "test-ocr"
    assert routed[0].quality == {"ocr_confidence": 0.93, "text_chars": 8}
    assert routed[0].extracted_text == "OCR text"

    stored = store.pending_extractions(source.source_id)[0]
    assert stored.quality["ocr_confidence"] == 0.93

    # the processor read the SNAPSHOT copy, not the live vault file
    assert len(seen_paths) == 1
    assert "snapshots" in str(seen_paths[0])
    assert str(seen_paths[0]).startswith(str(store.root))


def test_processor_failure_recorded_never_substituted(make_vault, store, ingest):
    source, _ = _queue(make_vault, store, ingest, "assets/sample-table.csv")

    def _boom(path):
        raise RuntimeError("corrupt table header")

    approved = ApprovedProcessors(
        (SimpleProcessor(name="tbl", capabilities=frozenset({"table-parse"}), _extract=_boom),)
    )
    routed = route_pending(store, source.source_id, approved)
    assert routed[0].status == "failed"
    assert "RuntimeError: corrupt table header" in routed[0].error
    assert routed[0].extracted_text is None  # no invented text, ever

    q = [r for r in store.quarantine(source.source_id) if r.reason == "extraction_failed"]
    assert len(q) == 1
    assert "no text substituted" in q[0].message


def test_capability_routing_is_exact(make_vault, store, ingest):
    """A processor approved for ocr must not touch a table-parse asset."""
    source, _ = _queue(make_vault, store, ingest, "assets/sample-table.csv")
    approved = ApprovedProcessors((_proc("only-ocr", ("ocr",), text="nope"),))
    routed = route_pending(store, source.source_id, approved)
    assert routed[0].status == "no_approved_processor"
    assert routed[0].extracted_text is None


def test_registry_rejects_conflicting_approvals():
    with pytest.raises(ValueError, match="approved for both"):
        ApprovedProcessors(
            (
                _proc("a", ("ocr",)),
                _proc("b", ("ocr",)),
            )
        )


def test_renamed_asset_keeps_queue_entry_content_addressed(make_vault, store, ingest):
    root, _ = make_vault("assets/sample-table.csv")
    source = register(ingest, store, root)
    ingest.run(source)
    entry_id = store.pending_extractions(source.source_id)[0].entry_id

    (root / "sample-table.csv").rename(root / "table-renamed.csv")
    r2 = ingest.run(source)
    assert r2.assets_queued == []  # same content: queue entry reused
    assert r2.renames  # asset identity also survives renames
    entry = store.pending_extractions(source.source_id)[0]
    assert entry.entry_id == entry_id  # content-addressed: stable
    assert entry.path == "table-renamed.csv"  # but tracks the current location
