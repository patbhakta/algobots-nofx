"""Knowledge ingest core (packet A14, slices A14-1 + A14-2).

A14-1 — vault source registration, immutable pre-parse snapshots, stable
document identity across renames, content-hashed versions, section-aligned
Markdown evidence chunks, an approved-processor extraction queue for
non-Markdown assets, path-confined security, and hash-keyed idempotency.

A14-2 — incremental embeddings + BM25 full-text index with per-artifact
model/version tracking, tenant/source ACLs on the A03 role matrix (authored
knowledge vs engineering documentation as separate permission classes),
source-delete tombstones with a proven <= 60s propagation window, quarantine
surfacing (invalid documents stay queryable-as-failed), and the
``/api/knowledge`` HTTP surface via ``algobots.knowledge.ingest.router``.

Doctrine carried over from the verified docvault lane: sha256-keyed stages,
element/section-aligned chunking (never fixed-size), canon-first (the vault's
Markdown notes are the truth; everything here is a rebuildable derivative),
gates that surface failure instead of inventing text.

The core modules stay stdlib-only; the router module is the only file that
imports the API stack and is deliberately NOT re-exported here, so importing
this package never drags FastAPI or the database along.
"""

from algobots.knowledge.ingest.acl import (
    KNOWLEDGE_ROLE_MATRIX,
    PermissionClass,
    SourceAcl,
    allowed,
    can_read_class,
    default_acl,
)
from algobots.knowledge.ingest.assets import (
    ApprovedProcessors,
    ExtractionResult,
    SimpleProcessor,
    route_pending,
)
from algobots.knowledge.ingest.indexing import (
    DEFAULT_EMBEDDER,
    DeterministicEmbedder,
    EmbeddingModel,
    IndexArtifact,
    IndexReport,
    KnowledgeIndex,
    SyncStatus,
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
from algobots.knowledge.ingest.search import (
    DEFAULT_CACHE_TTL_SECONDS,
    PermissionDenied,
    SearchService,
)
from algobots.knowledge.ingest.security import PathEscapeError, resolve_within_root
from algobots.knowledge.ingest.snapshot import (
    ASSET_CAPABILITIES,
    SnapshotResult,
    snapshot_source,
)
from algobots.knowledge.ingest.store import JsonIngestStore
from algobots.knowledge.ingest.tombstones import (
    DEFAULT_PROPAGATION_SECONDS,
    Tombstone,
    make_tombstone,
)

__all__ = [
    "ASSET_CAPABILITIES",
    "DEFAULT_CACHE_TTL_SECONDS",
    "DEFAULT_EMBEDDER",
    "DEFAULT_PROPAGATION_SECONDS",
    "ApprovedProcessors",
    "DeterministicEmbedder",
    "DocumentRecord",
    "DocumentVersion",
    "EmbeddingModel",
    "EvidenceChunk",
    "ExtractionResult",
    "IndexArtifact",
    "IndexReport",
    "IngestReport",
    "Ingestor",
    "JsonIngestStore",
    "KIND_ASSET",
    "KIND_MARKDOWN",
    "KNOWLEDGE_ROLE_MATRIX",
    "KnowledgeIndex",
    "MarkdownParseError",
    "ParsedDocument",
    "PathEntry",
    "PathEscapeError",
    "PendingExtraction",
    "PermissionClass",
    "PermissionDenied",
    "QuarantineRecord",
    "SearchService",
    "Section",
    "SimpleProcessor",
    "SnapshotResult",
    "SourceAcl",
    "SyncStatus",
    "Tombstone",
    "VaultSource",
    "WikiLink",
    "allowed",
    "build_chunks",
    "can_read_class",
    "default_acl",
    "make_tombstone",
    "parse_frontmatter",
    "parse_markdown",
    "resolve_within_root",
    "route_pending",
    "snapshot_source",
]
