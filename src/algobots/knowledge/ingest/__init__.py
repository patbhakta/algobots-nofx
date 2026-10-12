"""Knowledge ingest core (packet A14, slice A14-1).

Vault source registration, immutable pre-parse snapshots, stable document
identity across renames, content-hashed versions, section-aligned Markdown
evidence chunks, an approved-processor extraction queue for non-Markdown
assets, path-confined security, and hash-keyed idempotency.

Doctrine carried over from the verified docvault lane: sha256-keyed stages,
element/section-aligned chunking (never fixed-size), canon-first (the vault's
Markdown notes are the truth; everything here is a rebuildable derivative),
gates that surface failure instead of inventing text.

This module is intentionally framework-free (stdlib only): persistence is a
JSON store; API/DB integration happens in later A14 slices on top of these
shapes.
"""

from algobots.knowledge.ingest.assets import (
    ApprovedProcessors,
    ExtractionResult,
    SimpleProcessor,
    route_pending,
)
from algobots.knowledge.ingest.ingest import Ingestor, IngestReport
from algobots.knowledge.ingest.models import (
    KIND_ASSET,
    KIND_MARKDOWN,
    DocumentRecord,
    DocumentVersion,
    EvidenceChunk,
    PathEntry,
    PendingExtraction,
    QuarantineRecord,
    VaultSource,
    WikiLink,
)
from algobots.knowledge.ingest.parsing import (
    MarkdownParseError,
    ParsedDocument,
    Section,
    build_chunks,
    parse_frontmatter,
    parse_markdown,
)
from algobots.knowledge.ingest.security import PathEscapeError, resolve_within_root
from algobots.knowledge.ingest.snapshot import (
    ASSET_CAPABILITIES,
    SnapshotResult,
    snapshot_source,
)
from algobots.knowledge.ingest.store import JsonIngestStore

__all__ = [
    "ASSET_CAPABILITIES",
    "ApprovedProcessors",
    "DocumentRecord",
    "DocumentVersion",
    "EvidenceChunk",
    "ExtractionResult",
    "IngestReport",
    "Ingestor",
    "JsonIngestStore",
    "KIND_ASSET",
    "KIND_MARKDOWN",
    "MarkdownParseError",
    "ParsedDocument",
    "PathEntry",
    "PathEscapeError",
    "PendingExtraction",
    "QuarantineRecord",
    "Section",
    "SimpleProcessor",
    "SnapshotResult",
    "VaultSource",
    "WikiLink",
    "build_chunks",
    "parse_frontmatter",
    "parse_markdown",
    "resolve_within_root",
    "route_pending",
    "snapshot_source",
]
