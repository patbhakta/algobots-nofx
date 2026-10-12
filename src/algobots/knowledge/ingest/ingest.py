"""Ingest orchestrator (A14-1): source registration -> snapshot -> lineage.

Phase order is doctrine: SNAPSHOT FIRST (immutable, hash-keyed), then all
parsing/indexing reads only from the snapshot — never from the live vault.

Identity rules:

- A document id is assigned at first sight and never changes; a pure rename
  (same content hash at a new path) keeps the same id, so citations survive.
- A content edit produces a new `DocumentVersion` (content-addressed id); a
  revert re-links the existing version instead of forging a duplicate.
- Unchanged re-import does zero work: same snapshot id, no new versions, no
  new chunks (content-addressed chunk ids), no new queue entries.

Security: every filesystem touch goes through path confinement; escaping
symlinks and traversal attempts become visible quarantine records, and no
byte outside the registered root is ever read. Failed parses surface errors
with zero chunks — placeholder text is never generated.
"""

from __future__ import annotations

import hashlib
import uuid as uuid_mod
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from algobots.knowledge.ingest.models import (
    KIND_ASSET,
    KIND_MARKDOWN,
    DocumentRecord,
    DocumentVersion,
    PathEntry,
    PendingExtraction,
    QuarantineRecord,
    VaultSource,
    utcnow_iso,
)
from algobots.knowledge.ingest.parsing import MarkdownParseError, build_chunks, parse_markdown
from algobots.knowledge.ingest.security import resolve_within_root
from algobots.knowledge.ingest.snapshot import snapshot_source
from algobots.knowledge.ingest.store import JsonIngestStore


def _hash_hex(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()


@dataclass
class IngestReport:
    """What one ingest run changed — the zero-work proof for idempotency."""

    source_id: str
    snapshot_id: str
    snapshot_created: bool
    files_seen: int = 0
    unchanged: int = 0
    documents_new: list[str] = field(default_factory=list)
    versions_new: list[str] = field(default_factory=list)
    renames: list[tuple[str, str, str]] = field(default_factory=list)  # (doc_id, old, new)
    chunks_new: list[str] = field(default_factory=list)  # embedding work list
    assets_queued: list[str] = field(default_factory=list)  # entry ids
    missing: list[str] = field(default_factory=list)  # doc ids flagged missing
    reclaimed: list[str] = field(default_factory=list)  # missing docs that returned
    quarantined: list[str] = field(default_factory=list)  # record ids
    errors: list[str] = field(default_factory=list)  # human-readable summaries

    def error(self, message: str) -> None:
        self.errors.append(message)


class Ingestor:
    def __init__(self, store: JsonIngestStore) -> None:
        self.store = store

    # -------------------------------------------------------- registration --
    @staticmethod
    def register_source(
        store: JsonIngestStore,
        *,
        tenant_id: UUID,
        root: Path,
        acl_ref: str,
        source_id: str | None = None,
    ) -> VaultSource:
        """Register a vault root for a tenant. Idempotent: the default id is
        content-addressed off (tenant, resolved root), so re-registering the
        same root returns the same source record."""
        root_p = Path(root)
        if not root_p.is_dir():
            raise ValueError(f"source root is not a directory: {root_p}")
        resolved = str(root_p.resolve())
        sid = source_id or ("src-" + _hash_hex(str(tenant_id), resolved)[:16])
        source = VaultSource(
            source_id=sid,
            tenant_id=tenant_id,
            root=resolved,
            acl_ref=acl_ref,
            created_at=utcnow_iso(),
        )
        store.save_source(source)
        return source

    # ------------------------------------------------------------------ run --
    def run(self, source: VaultSource) -> IngestReport:
        snap = snapshot_source(self.store, source)
        report = IngestReport(
            source_id=source.source_id,
            snapshot_id=snap.snapshot_id,
            snapshot_created=snap.created,
        )
        for finding in snap.findings:
            record_id = "qs-" + _hash_hex(source.source_id, finding.path, finding.reason)[:20]
            self._quarantine(
                report,
                QuarantineRecord(
                    record_id=record_id,
                    source_id=source.source_id,
                    path=finding.path,
                    reason=finding.reason,
                    message=finding.message,
                    snapshot_id=None,
                    content_hash=None,
                    occurred_at=utcnow_iso(),
                ),
            )

        snap_dir = self.store.snapshot_dir(source.source_id, snap.snapshot_id)
        manifest_paths = {m.path for m in snap.files}
        docs = {d.current_path: d for d in self.store.documents(source.source_id)}

        # Rename candidates: docs whose path vanished, keyed by content hash.
        # Deterministic tie-break: lexicographically smallest current_path.
        vanished: dict[str, list[DocumentRecord]] = {}
        for d in docs.values():
            if d.current_path not in manifest_paths:
                v = self.store.get_version(d.current_version_id) if d.current_version_id else None
                if v is not None:
                    vanished.setdefault(v.content_hash, []).append(d)
        for candidates in vanished.values():
            candidates.sort(key=lambda d: d.current_path)

        for m in snap.files:
            doc = docs.get(m.path)
            if doc is not None and not self._same_class(doc, m.is_markdown):
                # Same path now carries a different file class (e.g. note.md
                # replaced by note.pdf content): the old identity is stale at
                # this path — flag it missing instead of mutating its kind.
                if not doc.missing:
                    doc.missing = True
                    doc.updated_at = utcnow_iso()
                    self.store.save_document(doc)
                    report.missing.append(doc.doc_id)
                doc = None

            if doc is not None and doc.current_version_id is not None:
                current = self.store.get_version(doc.current_version_id)
                if current is not None and current.content_hash == m.content_hash:
                    self._unchanged(report, doc, snap.snapshot_id)
                    continue

            if doc is None:
                candidates = [
                    c for c in vanished.get(m.content_hash, [])
                    if self._same_class(c, m.is_markdown)
                ]
                if candidates:
                    doc = candidates.pop(0)
                    self._rename(report, doc, m.path, snap.snapshot_id)

            if doc is None:
                doc = DocumentRecord(
                    doc_id="d-" + uuid_mod.uuid4().hex[:24],
                    source_id=source.source_id,
                    tenant_id=source.tenant_id,
                    kind=KIND_MARKDOWN if m.is_markdown else KIND_ASSET,
                    current_path=m.path,
                )
                doc.path_history = [PathEntry(m.path, snap.snapshot_id, snap.snapshot_id)]
                report.documents_new.append(doc.doc_id)

            if m.is_markdown:
                self._ingest_markdown(report, source, doc, m, snap_dir, snap.snapshot_id)
            else:
                self._ingest_asset(report, source, doc, m, snap_dir, snap.snapshot_id)

        # Docs still vanished and unconsumed by a rename are flagged missing —
        # lineage is never destructively deleted. (Rename-consumed docs were
        # mutated in place: their current_path is back inside the manifest.)
        for hash_candidates in vanished.values():
            for d in hash_candidates:
                if d.current_path not in manifest_paths and not d.missing:
                    d.missing = True
                    d.updated_at = utcnow_iso()
                    self.store.save_document(d)
                    report.missing.append(d.doc_id)
        return report

    # ------------------------------------------------------------ internals --
    def _same_class(self, doc: DocumentRecord, is_markdown: bool) -> bool:
        return (doc.kind == KIND_MARKDOWN) == is_markdown

    def _unchanged(self, report: IngestReport, doc: DocumentRecord, snapshot_id: str) -> None:
        report.unchanged += 1
        if doc.missing:
            doc.missing = False
            doc.updated_at = utcnow_iso()
            self.store.save_document(doc)
            report.reclaimed.append(doc.doc_id)
        entry = doc.path_history[-1] if doc.path_history else None
        if entry is not None and entry.last_seen != snapshot_id:
            doc.path_history[-1] = PathEntry(entry.path, entry.first_seen, snapshot_id)
            doc.updated_at = utcnow_iso()
            self.store.save_document(doc)

    def _rename(
        self, report: IngestReport, doc: DocumentRecord, new_path: str, snapshot_id: str
    ) -> None:
        old = doc.current_path
        doc.current_path = new_path
        doc.path_history.append(PathEntry(new_path, snapshot_id, snapshot_id))
        doc.missing = False
        doc.updated_at = utcnow_iso()
        self.store.save_document(doc)
        report.renames.append((doc.doc_id, old, new_path))

    def _quarantine(self, report: IngestReport, record: QuarantineRecord) -> None:
        existing = {r.record_id for r in self.store.quarantine(record.source_id)}
        if record.record_id in existing:
            return  # idempotent: security findings recur every import
        self.store.append_quarantine(record)
        report.quarantined.append(record.record_id)
        report.error(f"[{record.reason}] {record.path}: {record.message}")

    def _ingest_markdown(self, report, source, doc, m, snap_dir, snapshot_id) -> None:
        safe = resolve_within_root(snap_dir, m.path)
        raw = safe.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            self._record_version(report, doc, m, snapshot_id, chunk_count=0)
            self._quarantine(
                report,
                QuarantineRecord(
                    record_id="q-" + _hash_hex(
                        source.source_id, m.content_hash, "utf8_decode"
                    )[:20],
                    source_id=source.source_id,
                    path=m.path,
                    reason="utf8_decode",
                    message=f"file is not valid UTF-8 ({exc}); no chunks generated",
                    snapshot_id=snapshot_id,
                    content_hash=m.content_hash,
                    occurred_at=utcnow_iso(),
                ),
            )
            return
        try:
            parsed = parse_markdown(text)
        except MarkdownParseError as exc:
            self._record_version(report, doc, m, snapshot_id, chunk_count=0)
            self._quarantine(
                report,
                QuarantineRecord(
                    record_id="q-" + _hash_hex(source.source_id, m.content_hash, exc.reason)[:20],
                    source_id=source.source_id,
                    path=m.path,
                    reason=exc.reason,
                    message=f"{exc.message}; no chunks generated",
                    snapshot_id=snapshot_id,
                    content_hash=m.content_hash,
                    occurred_at=utcnow_iso(),
                ),
            )
            return
        version_id = "v-" + _hash_hex(doc.doc_id, m.content_hash)[:24]
        chunks = build_chunks(doc.doc_id, version_id, m.content_hash, parsed.sections, parsed.page)
        if self.store.save_chunks(version_id, chunks):
            for c in chunks:
                if c.chunk_id not in report.chunks_new:
                    report.chunks_new.append(c.chunk_id)
        if self.store.get_version(version_id) is None:
            self.store.save_version(
                DocumentVersion(
                    version_id=version_id,
                    doc_id=doc.doc_id,
                    content_hash=m.content_hash,
                    path=m.path,
                    size_bytes=m.size_bytes,
                    snapshot_id=snapshot_id,
                    chunk_count=len(chunks),
                    created_at=utcnow_iso(),
                )
            )
            report.versions_new.append(version_id)
        if not doc.version_history or doc.version_history[-1] != version_id:
            doc.version_history.append(version_id)
        doc.current_version_id = version_id
        doc.updated_at = utcnow_iso()
        self.store.save_document(doc)

    def _record_version(self, report, doc, m, snapshot_id, *, chunk_count: int) -> None:
        """Version bookkeeping for content that exists but failed to parse."""
        version_id = "v-" + _hash_hex(doc.doc_id, m.content_hash)[:24]
        if self.store.get_version(version_id) is None:
            self.store.save_version(
                DocumentVersion(
                    version_id=version_id,
                    doc_id=doc.doc_id,
                    content_hash=m.content_hash,
                    path=m.path,
                    size_bytes=m.size_bytes,
                    snapshot_id=snapshot_id,
                    chunk_count=chunk_count,
                    created_at=utcnow_iso(),
                )
            )
            report.versions_new.append(version_id)
        if not doc.version_history or doc.version_history[-1] != version_id:
            doc.version_history.append(version_id)
        doc.current_version_id = version_id
        doc.updated_at = utcnow_iso()
        self.store.save_document(doc)

    def _ingest_asset(self, report, source, doc, m, snap_dir, snapshot_id) -> None:
        self._record_version(report, doc, m, snapshot_id, chunk_count=0)
        entry_id = "x-" + _hash_hex(source.source_id, m.content_hash)[:24]
        entry = self.store.get_pending_extraction(entry_id)
        if entry is None:
            entry = PendingExtraction(
                entry_id=entry_id,
                source_id=source.source_id,
                doc_id=doc.doc_id,
                version_id=doc.current_version_id or "",
                path=m.path,
                content_hash=m.content_hash,
                capability=m.capability,
                status="unsupported" if m.capability == "unknown" else "pending",
            )
            self.store.save_pending_extraction(entry)
            report.assets_queued.append(entry_id)
        elif entry.path != m.path and entry.status == "pending":
            # content-addressed entry follows the asset's current location
            entry.path = m.path
            entry.updated_at = utcnow_iso()
            self.store.save_pending_extraction(entry)
