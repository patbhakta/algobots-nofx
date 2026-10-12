"""Lineage records for vault ingestion (A14-1).

Dataclasses only — pure data, JSON-(de)serialisable, no framework imports.
The knowledge ingest core is deliberately decoupled from `algobots.api`:
persistence here is a JSON store (`store.JsonIngestStore`); a later slice
can add a DB-backed store behind the same shapes.

Doctrine (docvault, verified lane): records are sha256-keyed derivatives of
the source content. The vault's Markdown notes are the canon; every record
below is rebuildable from an immutable snapshot.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

KIND_MARKDOWN = "markdown"
KIND_ASSET = "asset"

# Pending-extraction statuses. `unsupported` is set at queue time for assets
# whose type maps to no approved capability — a visible non-claim, never a
# silent drop and never an invented extraction.
EXTRACTION_PENDING = "pending"
EXTRACTION_NO_PROCESSOR = "no_approved_processor"
EXTRACTION_PROCESSED = "processed"
EXTRACTION_FAILED = "failed"
EXTRACTION_UNSUPPORTED = "unsupported"


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class VaultSource:
    """A registered vault root owned by exactly one tenant (A03 tenancy).

    ``acl_ref`` is an opaque reference to the ACL/grant record governing
    reads of this root (e.g. an account-grant id); the ingest core never
    interprets it, it only preserves the lineage link.
    """

    source_id: str
    tenant_id: UUID
    root: str  # resolved absolute path as registered
    acl_ref: str
    created_at: str


@dataclass(frozen=True)
class PathEntry:
    """One observed location of a document (rename history)."""

    path: str
    first_seen: str  # snapshot_id
    last_seen: str  # snapshot_id


@dataclass
class DocumentRecord:
    """Stable document identity: survives renames, chains versions.

    ``doc_id`` is content-addressed at first sight (sha256 of source + first
    content hash), so a pure rename — same bytes, new path — resolves to the
    same identity and citations keep working.
    """

    doc_id: str
    source_id: str
    tenant_id: UUID
    kind: str  # KIND_MARKDOWN | KIND_ASSET
    current_path: str
    path_history: list[PathEntry] = field(default_factory=list)
    version_history: list[str] = field(default_factory=list)  # version_ids, in order
    current_version_id: str | None = None
    missing: bool = False  # path vanished with no hash successor; lineage kept
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = utcnow_iso()
        if not self.updated_at:
            self.updated_at = self.created_at


@dataclass(frozen=True)
class DocumentVersion:
    """Content state of a document at one point in time.

    ``version_id`` is content-addressed (sha256 of doc + content hash): the
    same content under the same identity is the same version, so a revert
    re-links an existing version instead of forging a duplicate.
    """

    version_id: str
    doc_id: str
    content_hash: str  # sha256 hex of the raw bytes
    path: str  # path as seen by this version
    size_bytes: int
    snapshot_id: str  # immutable snapshot the bytes live in
    chunk_count: int
    created_at: str


@dataclass(frozen=True)
class WikiLink:
    target: str
    section: str | None = None
    label: str | None = None


@dataclass(frozen=True)
class EvidenceChunk:
    """A section-aligned evidence unit — verbatim text, never invented.

    ``chunk_id`` is content-addressed (sha256 of version content hash +
    section anchor + order): identical content always yields identical chunk
    ids, so unchanged re-imports generate zero new embedding work and a
    revert reuses the chunks it already had.
    """

    chunk_id: str
    doc_id: str
    version_id: str
    anchor: str  # slug heading path, "" for the preamble before any heading
    heading: str | None  # raw heading text, None for the preamble
    heading_level: int  # 1-6, 0 for the preamble
    page: int | None  # page anchor from frontmatter when declared
    start_line: int  # 1-based, inclusive
    end_line: int  # 1-based, inclusive
    text: str  # verbatim source slice
    order: int
    links: tuple[WikiLink, ...] = ()


@dataclass
class PendingExtraction:
    """Queue entry for a non-Markdown asset awaiting an approved processor.

    No universal support claim: `capability` names what this asset needs
    ("pdf-text", "ocr", "table-parse"); "unknown" types are queued as
    ``unsupported`` and stay visible forever until a processor is approved.
    """

    entry_id: str  # content-addressed: sha256(source_id + content_hash)
    source_id: str
    doc_id: str
    version_id: str
    path: str
    content_hash: str
    capability: str
    status: str = EXTRACTION_PENDING
    processor: str | None = None
    quality: dict[str, Any] | None = None  # e.g. {"ocr_confidence": 0.94}
    extracted_text: str | None = None  # only ever set by an approved processor
    error: str | None = None
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.updated_at:
            self.updated_at = utcnow_iso()


@dataclass(frozen=True)
class QuarantineRecord:
    """Visible error record — nothing malformed is ever silently dropped."""

    record_id: str
    source_id: str
    path: str
    reason: str  # utf8_decode | frontmatter | nul_bytes | symlink_escape | symlink_skipped
    message: str
    occurred_at: str
    snapshot_id: str | None = None
    content_hash: str | None = None


def to_json(obj: Any) -> Any:
    """Recursively convert dataclasses/UUIDs/tuples to JSON-safe values."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: to_json(v) for k, v in asdict(obj).items()}
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, (list, tuple)):
        return [to_json(v) for v in obj]
    if isinstance(obj, dict):
        return {k: to_json(v) for k, v in obj.items()}
    return obj


def source_from_json(data: dict[str, Any]) -> VaultSource:
    return VaultSource(
        source_id=data["source_id"],
        tenant_id=UUID(data["tenant_id"]),
        root=data["root"],
        acl_ref=data["acl_ref"],
        created_at=data["created_at"],
    )


def document_from_json(data: dict[str, Any]) -> DocumentRecord:
    return DocumentRecord(
        doc_id=data["doc_id"],
        source_id=data["source_id"],
        tenant_id=UUID(data["tenant_id"]),
        kind=data["kind"],
        current_path=data["current_path"],
        path_history=[PathEntry(**e) for e in data.get("path_history", [])],
        version_history=list(data.get("version_history", [])),
        current_version_id=data.get("current_version_id"),
        missing=bool(data.get("missing", False)),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
    )


def version_from_json(data: dict[str, Any]) -> DocumentVersion:
    return DocumentVersion(
        version_id=data["version_id"],
        doc_id=data["doc_id"],
        content_hash=data["content_hash"],
        path=data["path"],
        size_bytes=data["size_bytes"],
        snapshot_id=data["snapshot_id"],
        chunk_count=data["chunk_count"],
        created_at=data["created_at"],
    )


def chunks_from_json(data: list[dict[str, Any]]) -> list[EvidenceChunk]:
    out: list[EvidenceChunk] = []
    for c in data:
        links = tuple(
            WikiLink(target=wl["target"], section=wl.get("section"), label=wl.get("label"))
            for wl in c.get("links", [])
        )
        out.append(
            EvidenceChunk(
                chunk_id=c["chunk_id"],
                doc_id=c["doc_id"],
                version_id=c["version_id"],
                anchor=c["anchor"],
                heading=c.get("heading"),
                heading_level=c.get("heading_level", 0),
                page=c.get("page"),
                start_line=c["start_line"],
                end_line=c["end_line"],
                text=c["text"],
                links=links,
                order=c["order"],
            )
        )
    return out


def pending_from_json(data: dict[str, Any]) -> PendingExtraction:
    return PendingExtraction(
        entry_id=data["entry_id"],
        source_id=data["source_id"],
        doc_id=data["doc_id"],
        version_id=data["version_id"],
        path=data["path"],
        content_hash=data["content_hash"],
        capability=data["capability"],
        status=data["status"],
        processor=data.get("processor"),
        quality=data.get("quality"),
        extracted_text=data.get("extracted_text"),
        error=data.get("error"),
        updated_at=data.get("updated_at", ""),
    )


def quarantine_from_json(data: dict[str, Any]) -> QuarantineRecord:
    return QuarantineRecord(
        record_id=data["record_id"],
        source_id=data["source_id"],
        path=data["path"],
        reason=data["reason"],
        message=data["message"],
        snapshot_id=data.get("snapshot_id"),
        content_hash=data.get("content_hash"),
        occurred_at=data["occurred_at"],
    )
