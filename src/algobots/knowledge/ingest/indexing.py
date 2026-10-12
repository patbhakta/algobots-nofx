"""Incremental embedding + full-text index over A14-1 chunks (A14-2).

Doctrine (docvault lane): indexes are sha256-keyed rebuildable derivatives of
the canon. This module is deterministic and entirely local — the default
embedder is a seeded hashed bag-of-tokens projection (stdlib only), so the
pipeline runs with zero external API spend. A model-backed embedder can be
introduced later behind the same callable shape; its name and version then
flow into the same per-artifact tracking.

Incrementality: chunk ids are content-addressed (A14-1), so the embeddings
manifest keyed by ``chunk_id`` per model is a sufficient change detector —
re-indexing unchanged content embeds nothing, and a model/version bump
re-embeds everything under the new key while the old artifacts remain
inspectable on disk.

Index layout under the store root::

    index/embeddings/<model_key>/manifest.json    # model meta + {chunk_id: doc_id}
    index/embeddings/<model_key>/<chunk_id>.json  # one vector per chunk
    index/fts/<source_id>.json                    # postings + chunk meta + failed docs
    index/artifacts.json                          # IndexArtifact ledger

Every artifact records the model name + version that produced it (for FTS the
"model" is the retrieval engine id), the chunk count, and a digest over the
indexed chunk ids — index provenance is never anonymous.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from algobots.knowledge.ingest.models import (
    EvidenceChunk,
    utcnow_iso,
)
from algobots.knowledge.ingest.store import JsonIngestStore

_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)

# BM25 parameters (mirrors the verified vault_chat retrieval shape).
BM25_K1 = 1.5
BM25_B = 0.75


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


# ------------------------------------------------------------------ model --


@dataclass(frozen=True)
class EmbeddingModel:
    """Identity of the embedding function. The (name, version, dims) triple
    keys the artifact tree; changing any of it re-embeds everything."""

    name: str
    version: str
    dims: int = 128

    @property
    def key(self) -> str:
        raw = f"{self.name}@{self.version}"
        return f"{raw}-{self.dims}d-" + hashlib.sha256(raw.encode()).hexdigest()[:8]


@dataclass(frozen=True)
class DeterministicEmbedder:
    """Seeded hashed bag-of-tokens projection (local, deterministic, free).

    Each token hashes (seeded by the model identity) to a bucket and a sign;
    the vector is the signed sum, L2-normalised. Same text + same model =>
    same vector, always, across processes and machines — which is what makes
    the incremental manifest trustworthy without a vendor.
    """

    model: EmbeddingModel = field(default_factory=lambda: EmbeddingModel("hashed-bag", "1"))

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.model.dims
        seed = f"{self.model.name}:{self.model.version}".encode()
        for token in tokenize(text):
            h = hashlib.sha256(seed + b":" + token.encode()).digest()
            bucket = int.from_bytes(h[:4], "big") % self.model.dims
            sign = 1.0 if h[4] & 1 else -1.0
            vec[bucket] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]


DEFAULT_EMBEDDER = DeterministicEmbedder()


# --------------------------------------------------------------- artifacts --


@dataclass(frozen=True)
class IndexArtifact:
    """Provenance record for one produced index artifact."""

    artifact_id: str
    kind: str  # "embeddings" | "fts"
    model_name: str
    model_version: str
    chunk_count: int
    content_digest: str  # sha256 over the sorted chunk ids covered
    created_at: str

    def to_json(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "chunk_count": self.chunk_count,
            "content_digest": self.content_digest,
            "created_at": self.created_at,
        }


@dataclass
class SyncStatus:
    """Screen state for one source: last run + last good version."""

    source_id: str
    last_run_at: str = ""
    last_snapshot_id: str = ""
    status: str = "never_run"  # never_run | ok | partial | failed
    errors: list[str] = field(default_factory=list)
    quarantined: int = 0
    docs: int = 0
    chunks_indexed: int = 0
    embeddings_new: int = 0
    last_good: dict[str, Any] | None = None  # {snapshot_id, at, docs, chunks}

    def to_json(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "last_run_at": self.last_run_at,
            "last_snapshot_id": self.last_snapshot_id,
            "status": self.status,
            "errors": self.errors,
            "quarantined": self.quarantined,
            "docs": self.docs,
            "chunks_indexed": self.chunks_indexed,
            "embeddings_new": self.embeddings_new,
            "last_good": self.last_good,
        }


# ------------------------------------------------------------------ report --


@dataclass
class IndexReport:
    embeddings_new: list[str] = field(default_factory=list)
    fts_sources_rebuilt: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)

    @property
    def did_work(self) -> bool:
        return bool(self.embeddings_new or self.fts_sources_rebuilt)


# ------------------------------------------------------------------- index --


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest_chunk_ids(chunk_ids: Any) -> str:
    joined = "\n".join(sorted(chunk_ids))
    return hashlib.sha256(joined.encode()).hexdigest()


class KnowledgeIndex:
    """Incremental embeddings + BM25 full-text index over current chunks."""

    def __init__(self, store: JsonIngestStore, embedder: DeterministicEmbedder | None = None):
        self.store = store
        self.embedder = embedder or DEFAULT_EMBEDDER
        self.root = store.root / "index"
        # Sources excluded from the live view (tombstoned/revoked). Durable
        # state lives in the tombstone/ACL records; this set is the live
        # invalidation hook's landing zone.
        self._excluded: set[str] = set()

    # ------------------------------------------------------------- update --

    def update(self, source_id: str) -> IndexReport:
        """(Re-)index one source's current chunks. Hash-keyed: unchanged
        content embeds nothing, unchanged postings rewrite nothing."""
        report = IndexReport()
        live = self._live_chunks(source_id)
        self._update_embeddings(live, report)
        self._update_fts(source_id, live, report)
        return report

    def _live_chunks(self, source_id: str) -> list[EvidenceChunk]:
        """Current-version chunks, excluding missing documents (their lineage
        stays in the store; the live search surface drops them)."""
        out: list[EvidenceChunk] = []
        for doc in self.store.documents(source_id):
            if doc.missing or not doc.current_version_id:
                continue
            out.extend(self.store.chunks_for(doc.current_version_id))
        return out

    def _update_embeddings(self, live: list[EvidenceChunk], report: IndexReport) -> None:
        model = self.embedder.model
        mdir = self.root / "embeddings" / model.key
        manifest_path = mdir / "manifest.json"
        if manifest_path.exists():
            manifest = _read_json(manifest_path)
        else:
            manifest = {
                "model": {"name": model.name, "version": model.version, "dims": model.dims},
                "chunks": {},
            }
        chunks: dict[str, str] = manifest["chunks"]
        for chunk in live:
            # chunk_id is content-addressed, so its presence in this model's
            # manifest already proves the stored vector matches the content.
            if chunk.chunk_id in chunks:
                continue
            _write_json(
                mdir / f"{chunk.chunk_id}.json",
                {
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.doc_id,
                    "content": chunk.text,
                    "vector": self.embedder.embed(chunk.text),
                    "model": {"name": model.name, "version": model.version},
                    "created_at": utcnow_iso(),
                },
            )
            chunks[chunk.chunk_id] = chunk.doc_id
            report.embeddings_new.append(chunk.chunk_id)
        manifest["model"] = {"name": model.name, "version": model.version, "dims": model.dims}
        _write_json(manifest_path, manifest)
        self._record_artifact(
            report,
            IndexArtifact(
                artifact_id=f"emb-{model.key}-{_digest_chunk_ids(chunks.keys())[:16]}",
                kind="embeddings",
                model_name=model.name,
                model_version=model.version,
                chunk_count=len(chunks),
                content_digest=_digest_chunk_ids(chunks.keys()),
                created_at=utcnow_iso(),
            ),
        )

    def _update_fts(
        self, source_id: str, live: list[EvidenceChunk], report: IndexReport
    ) -> None:
        payload = self._build_fts_payload(source_id, live)
        path = self.root / "fts" / f"{source_id}.json"
        if path.exists() and _read_json(path) == payload:
            return  # unchanged: zero new index work
        _write_json(path, payload)
        report.fts_sources_rebuilt.append(source_id)
        chunk_ids = [c.chunk_id for c in live]
        self._record_artifact(
            report,
            IndexArtifact(
                artifact_id="fts-" + hashlib.sha256(source_id.encode()).hexdigest()[:12],
                kind="fts",
                model_name="bm25",
                model_version="1",
                chunk_count=len(chunk_ids),
                content_digest=_digest_chunk_ids(chunk_ids),
                created_at=utcnow_iso(),
            ),
        )

    def _build_fts_payload(
        self, source_id: str, live: list[EvidenceChunk]
    ) -> dict[str, Any]:
        postings: dict[str, dict[str, int]] = {}
        lengths: dict[str, int] = {}
        chunk_meta: dict[str, dict[str, Any]] = {}
        doc_paths: dict[str, str] = {}
        failed: dict[str, dict[str, Any]] = {}
        for chunk in live:
            doc_paths.setdefault(chunk.doc_id, "")
            tokens = tokenize(chunk.text)
            lengths[chunk.chunk_id] = len(tokens)
            freq: dict[str, int] = {}
            for token in tokens:
                freq[token] = freq.get(token, 0) + 1
            for token, n in freq.items():
                postings.setdefault(token, {})[chunk.chunk_id] = n
            version = self.store.get_version(chunk.version_id)
            doc = self.store.get_document(chunk.doc_id)
            path = doc.current_path if doc else (version.path if version else "")
            doc_paths[chunk.doc_id] = path
            chunk_meta[chunk.chunk_id] = {
                "doc_id": chunk.doc_id,
                "version_id": chunk.version_id,
                "path": path,
                "anchor": chunk.anchor,
                "heading": chunk.heading,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "text": chunk.text,
            }
        # Invalid documents stay queryable-as-failed with visible errors:
        # current versions with zero chunks and a matching quarantine record.
        failed_by_hash = {
            q.content_hash: q for q in self.store.quarantine(source_id) if q.content_hash
        }
        for doc in self.store.documents(source_id):
            if doc.missing or not doc.current_version_id:
                continue
            version = self.store.get_version(doc.current_version_id)
            if version is None or version.chunk_count > 0:
                continue
            record = failed_by_hash.get(version.content_hash)
            if record is None:
                continue
            failed[doc.doc_id] = {
                "path": doc.current_path,
                "reason": record.reason,
                "message": record.message,
            }
        return {
            "source_id": source_id,
            "docs": failed,
            "doc_paths": doc_paths,
            "lengths": lengths,
            "postings": postings,
            "chunk_meta": chunk_meta,
        }

    def _record_artifact(self, report: IndexReport, artifact: IndexArtifact) -> None:
        path = self.root / "artifacts.json"
        ledger = _read_json(path) if path.exists() else []
        if any(a["artifact_id"] == artifact.artifact_id for a in ledger):
            return
        ledger.append(artifact.to_json())
        _write_json(path, ledger)
        report.artifacts.append(artifact.artifact_id)

    # ------------------------------------------------------------- search --

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        include_source: Callable[[str], bool] | None = None,
    ) -> dict[str, Any]:
        """BM25 over all sources' live FTS files + failed-doc path matches.

        ``include_source`` is the caller's gate (ACLs, tombstones); sources
        it rejects contribute neither chunk hits nor failed-doc entries.
        """
        hits: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        tokens = tokenize(query)
        fts_dir = self.root / "fts"
        if not tokens or not fts_dir.exists():
            return {"hits": hits, "failures": failures}
        for path in sorted(fts_dir.glob("*.json")):
            payload = _read_json(path)
            source_id = payload["source_id"]
            if source_id in self._excluded:
                continue
            if include_source is not None and not include_source(source_id):
                continue
            hits.extend(self._bm25(source_id, payload, tokens))
            failures.extend(self._failed_matches(source_id, payload, tokens))
        hits.sort(key=lambda h: (-h["score"], h["chunk_id"]))
        failures.sort(key=lambda f: f["doc_id"])
        return {"hits": hits[:limit], "failures": failures[:limit]}

    @staticmethod
    def _bm25(
        source_id: str, payload: dict[str, Any], tokens: list[str]
    ) -> list[dict[str, Any]]:
        postings: dict[str, dict[str, int]] = payload["postings"]
        lengths: dict[str, int] = payload["lengths"]
        chunk_meta: dict[str, dict[str, Any]] = payload["chunk_meta"]
        n_chunks = len(chunk_meta)
        avg_len = (sum(lengths.values()) / len(lengths)) if lengths else 1.0
        avg_len = avg_len or 1.0
        scores: dict[str, float] = {}
        for token in tokens:
            posting = postings.get(token)
            if not posting:
                continue
            df = len(posting)
            idf = math.log(1.0 + (n_chunks - df + 0.5) / (df + 0.5))
            for chunk_id, tf in posting.items():
                dl = lengths.get(chunk_id, avg_len) or avg_len
                denom = tf + BM25_K1 * (1.0 - BM25_B + BM25_B * dl / avg_len)
                scores[chunk_id] = scores.get(chunk_id, 0.0) + idf * tf * (BM25_K1 + 1.0) / denom
        out: list[dict[str, Any]] = []
        for chunk_id, score in scores.items():
            meta = chunk_meta[chunk_id]
            out.append(
                {
                    "chunk_id": chunk_id,
                    "source_id": source_id,
                    "doc_id": meta["doc_id"],
                    "version_id": meta["version_id"],
                    "path": meta["path"],
                    "anchor": meta["anchor"],
                    "heading": meta["heading"],
                    "start_line": meta["start_line"],
                    "end_line": meta["end_line"],
                    "text": meta["text"],
                    "score": round(score, 6),
                }
            )
        return out

    @staticmethod
    def _failed_matches(
        source_id: str, payload: dict[str, Any], tokens: list[str]
    ) -> list[dict[str, Any]]:
        wanted = set(tokens)
        out = []
        for doc_id, info in payload.get("docs", {}).items():
            if wanted & set(tokenize(info.get("path", ""))):
                out.append(
                    {
                        "doc_id": doc_id,
                        "source_id": source_id,
                        "path": info["path"],
                        "status": "failed",
                        "reason": info["reason"],
                        "message": info["message"],
                    }
                )
        return out

    # ------------------------------------------------------- invalidation --

    def invalidate_source(self, source_id: str) -> None:
        """Index-view invalidation hook: drop the source from the live search
        view. Durable artifacts stay on disk (rebuildable derivatives); the
        tombstone + revoked ACL are the durable proof of removal."""
        self._excluded.add(source_id)

    def restore_source(self, source_id: str) -> None:
        self._excluded.discard(source_id)
