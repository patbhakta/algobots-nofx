"""JSON-backed ingest store (A14-1 reference implementation).

Layout under the store root — one inspectable JSON file per entity, plus an
append-only quarantine ledger and immutable snapshot trees:

    sources/<source_id>.json
    documents/<doc_id>.json
    versions/<version_id>.json
    chunks/<version_id>.json            # version-keyed; ids are content-addressed
    pending_extractions.json            # queue, keyed by entry_id
    quarantine.jsonl                     # append-only error ledger
    snapshots/<source_id>/<snapshot_id>/ # immutable copies + manifest.json

Idempotency doctrine: every write is keyed by a content hash, so re-importing
unchanged content rewrites byte-identical files and creates nothing new. The
store is a derivative of the snapshots; drop it and rebuild from canon.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID

from algobots.knowledge.ingest.models import (
    DocumentRecord,
    DocumentVersion,
    EvidenceChunk,
    PendingExtraction,
    QuarantineRecord,
    VaultSource,
    chunks_from_json,
    document_from_json,
    pending_from_json,
    quarantine_from_json,
    source_from_json,
    to_json,
    version_from_json,
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class JsonIngestStore:
    """Durable lineage store. All mutations are hash-keyed and idempotent."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ sources --
    def save_source(self, source: VaultSource) -> None:
        _write_json(self.root / "sources" / f"{source.source_id}.json", to_json(source))

    def get_source(self, source_id: str) -> VaultSource | None:
        p = self.root / "sources" / f"{source_id}.json"
        return source_from_json(_read_json(p)) if p.exists() else None

    def sources(self, tenant_id: UUID | None = None) -> list[VaultSource]:
        out = []
        d = self.root / "sources"
        if not d.exists():
            return out
        for p in sorted(d.glob("*.json")):
            s = source_from_json(_read_json(p))
            if tenant_id is None or s.tenant_id == tenant_id:
                out.append(s)
        return out

    # ---------------------------------------------------------- documents --
    def save_document(self, doc: DocumentRecord) -> None:
        _write_json(self.root / "documents" / f"{doc.doc_id}.json", to_json(doc))

    def get_document(self, doc_id: str) -> DocumentRecord | None:
        p = self.root / "documents" / f"{doc_id}.json"
        return document_from_json(_read_json(p)) if p.exists() else None

    def documents(self, source_id: str | None = None) -> list[DocumentRecord]:
        out = []
        d = self.root / "documents"
        if not d.exists():
            return out
        for p in sorted(d.glob("*.json")):
            doc = document_from_json(_read_json(p))
            if source_id is None or doc.source_id == source_id:
                out.append(doc)
        return out

    # ----------------------------------------------------------- versions --
    def save_version(self, version: DocumentVersion) -> None:
        _write_json(self.root / "versions" / f"{version.version_id}.json", to_json(version))

    def get_version(self, version_id: str) -> DocumentVersion | None:
        p = self.root / "versions" / f"{version_id}.json"
        return version_from_json(_read_json(p)) if p.exists() else None

    def versions(self, doc_id: str) -> list[DocumentVersion]:
        out = []
        for vid in self._version_ids_for(doc_id):
            v = self.get_version(vid)
            if v is not None:
                out.append(v)
        return out

    def _version_ids_for(self, doc_id: str) -> list[str]:
        doc = self.get_document(doc_id)
        return list(doc.version_history) if doc else []

    # ------------------------------------------------------------- chunks --
    def save_chunks(self, version_id: str, chunks: list[EvidenceChunk]) -> bool:
        """Persist the chunk set for one document version. Keyed by the
        content-addressed version id, an identical rewrite is a no-op.
        Returns True when NEW chunk work was created (embedding callers key
        off this — chunk ids themselves are content-addressed, so identical
        content in two documents still shares embedding work), False when a
        byte-identical set already existed."""
        p = self.root / "chunks" / f"{version_id}.json"
        payload = to_json(chunks)
        if p.exists() and _read_json(p) == payload:
            return False
        _write_json(p, payload)
        return True

    def chunks_for(self, version_id: str) -> list[EvidenceChunk]:
        p = self.root / "chunks" / f"{version_id}.json"
        return chunks_from_json(_read_json(p)) if p.exists() else []

    # -------------------------------------------------- pending extraction --
    def pending_extractions(self, source_id: str | None = None) -> list[PendingExtraction]:
        p = self.root / "pending_extractions.json"
        if not p.exists():
            return []
        entries = [pending_from_json(e) for e in _read_json(p).values()]
        if source_id is not None:
            entries = [e for e in entries if e.source_id == source_id]
        return entries

    def save_pending_extraction(self, entry: PendingExtraction) -> None:
        p = self.root / "pending_extractions.json"
        data: dict[str, Any] = _read_json(p) if p.exists() else {}
        data[entry.entry_id] = to_json(entry)
        _write_json(p, data)

    def get_pending_extraction(self, entry_id: str) -> PendingExtraction | None:
        p = self.root / "pending_extractions.json"
        if not p.exists():
            return None
        data = _read_json(p)
        return pending_from_json(data[entry_id]) if entry_id in data else None

    # --------------------------------------------------------- quarantine --
    def append_quarantine(self, record: QuarantineRecord) -> None:
        p = self.root / "quarantine.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(to_json(record), sort_keys=True) + "\n")

    def quarantine(self, source_id: str | None = None) -> list[QuarantineRecord]:
        p = self.root / "quarantine.jsonl"
        if not p.exists():
            return []
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = quarantine_from_json(json.loads(line))
            if source_id is None or r.source_id == source_id:
                out.append(r)
        return out

    # ---------------------------------------------------------- snapshots --
    def snapshot_dir(self, source_id: str, snapshot_id: str) -> Path:
        return self.root / "snapshots" / source_id / snapshot_id

    def has_snapshot(self, source_id: str, snapshot_id: str) -> bool:
        return (self.snapshot_dir(source_id, snapshot_id) / "manifest.json").exists()
