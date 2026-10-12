"""Online search + sources screen service (A14-2).

The retrieval surface with teeth:

- every query is gated by per-source ACLs (A03 role -> knowledge permission
  class) and by tombstones — a removed source stops being exposed;
- results are cached with a TTL strictly shorter than the propagation window,
  and the removal path purges matching cache entries and drops the source
  from the live index view synchronously (invalidation hooks);
- removal is authorized removal: owner-only, tombstone + ACL revocation +
  invalidation in one transaction-shaped sequence, with the propagation
  completion stamped on the tombstone.

Canon-first: nothing here deletes lineage or snapshots. Removal removes
*exposure*, not history.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from algobots.knowledge.ingest.acl import (
    KnowledgeAction,
    SourceAcl,
    acl_from_json,
    allowed,
    can_read_class,
    default_acl,
)
from algobots.knowledge.ingest.indexing import (
    KnowledgeIndex,
    SyncStatus,
)
from algobots.knowledge.ingest.ingest import Ingestor
from algobots.knowledge.ingest.models import (
    PendingExtraction,
    QuarantineRecord,
    VaultSource,
)
from algobots.knowledge.ingest.store import JsonIngestStore
from algobots.knowledge.ingest.tombstones import (
    Tombstone,
    make_tombstone,
    parse_iso,
    stamp_propagated,
)

# Cache TTL default: comfortably inside the 60s propagation target so even a
# cache entry written the instant before removal cannot outlive the window
# once the purge hook has run (the purge is synchronous anyway; the TTL bound
# is defense in depth for hooks that fail loudly).
DEFAULT_CACHE_TTL_SECONDS = 30.0


class PermissionDenied(PermissionError):
    """Raised when the role may not perform the requested knowledge action."""


@dataclass
class _CacheEntry:
    hits: list[dict[str, Any]]
    failures: list[dict[str, Any]]
    sources: frozenset[str]
    at: float  # time.monotonic()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SearchService:
    def __init__(
        self,
        store: JsonIngestStore,
        index: KnowledgeIndex | None = None,
        *,
        cache_ttl: float = DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        self.store = store
        self.index = index or KnowledgeIndex(store)
        self.cache_ttl = cache_ttl
        self._cache: dict[tuple[str, str, str], _CacheEntry] = {}

    # ----------------------------------------------------------- sync/run --

    def run_sync(self, source: VaultSource) -> SyncStatus:
        """Ingest + index one source, then persist the screen state."""
        errors: list[str] = []
        try:
            report = Ingestor(self.store).run(source)
            errors.extend(report.errors)
            index_report = self.index.update(source.source_id)
        except Exception as exc:  # noqa: BLE001 — surfaced on the screen, never swallowed
            status = SyncStatus(
                source_id=source.source_id,
                last_run_at=_now_iso(),
                status="failed",
                errors=[f"sync crashed: {exc}"],
            )
            self._save_sync_status(status)
            raise
        docs = self.store.documents(source.source_id)
        chunks = len(self.index._live_chunks(source.source_id))
        status = SyncStatus(
            source_id=source.source_id,
            last_run_at=_now_iso(),
            last_snapshot_id=report.snapshot_id,
            status="ok" if not errors else "partial",
            errors=errors,
            quarantined=len(self.store.quarantine(source.source_id)),
            docs=len(docs),
            chunks_indexed=chunks,
            embeddings_new=len(index_report.embeddings_new),
        )
        if not errors:
            status.last_good = {
                "snapshot_id": report.snapshot_id,
                "at": status.last_run_at,
                "docs": status.docs,
                "chunks": status.chunks_indexed,
                "version_ids": [
                    d.current_version_id for d in docs if d.current_version_id
                ][:50],
            }
        else:
            previous = self.sync_status(source.source_id)
            if previous is not None:
                status.last_good = previous.last_good
        self._save_sync_status(status)
        return status

    def sync_status(self, source_id: str) -> SyncStatus | None:
        p = self.store.root / "sync-status" / f"{source_id}.json"
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return SyncStatus(**data)

    def _save_sync_status(self, status: SyncStatus) -> None:
        p = self.store.root / "sync-status" / f"{status.source_id}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(status.to_json(), indent=1, sort_keys=True) + "\n")

    # ----------------------------------------------------------- acl state --

    def get_acl(self, source_id: str) -> SourceAcl:
        data = self._load_acl_map()
        return acl_from_json(data[source_id]) if source_id in data else default_acl(source_id)

    def set_acl(self, acl: SourceAcl) -> None:
        data = self._load_acl_map()
        data[acl.source_id] = acl.to_json()
        self._write_acl_map(data)
        # ACL changes move the visibility line (revocation, class change):
        # cached results for this source are stale the moment this lands.
        # Cache-only purge — the source stays in the live index for roles
        # that may still read it (index exclusion is tombstone-only).
        self._purge_cache_for(acl.source_id)

    def _load_acl_map(self) -> dict[str, Any]:
        p = self.store.root / "source_acls.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def _write_acl_map(self, data: dict[str, Any]) -> None:
        p = self.store.root / "source_acls.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(p)

    # -------------------------------------------------------- tombstones --

    def tombstones(self, source_id: str | None = None) -> list[Tombstone]:
        p = self.store.root / "tombstones.jsonl"
        if not p.exists():
            return []
        out: list[Tombstone] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if source_id is None or d["source_id"] == source_id:
                out.append(
                    Tombstone(
                        source_id=d["source_id"],
                        reason=d["reason"],
                        created_at=d["created_at"],
                        propagation_seconds=d["propagation_seconds"],
                        propagation_deadline=d["propagation_deadline"],
                        revoked_by=d.get("revoked_by"),
                        propagated_at=d.get("propagated_at"),
                    )
                )
        return out

    def active_tombstone(self, source_id: str) -> Tombstone | None:
        ts = self.tombstones(source_id)
        return ts[-1] if ts else None

    def _append_tombstone(self, tombstone: Tombstone) -> None:
        p = self.store.root / "tombstones.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(tombstone.to_json(), sort_keys=True) + "\n")

    # ------------------------------------------------------------ queries --

    def visible_sources(
        self, role: str | None, tenant_id: UUID | None = None
    ) -> list[tuple[VaultSource, SourceAcl]]:
        """Sources the role may read: tenant-scoped, ACL live, not tombstoned,
        permission class readable by the role."""
        out = []
        for source in self.store.sources(tenant_id):
            if self.active_tombstone(source.source_id) is not None:
                continue
            acl = self.get_acl(source.source_id)
            if not acl.live or not can_read_class(role, acl.permission):
                continue
            out.append((source, acl))
        return out

    def _gate(self, role: str | None, tenant_id: UUID | None) -> Any:
        def include(source_id: str) -> bool:
            if self.active_tombstone(source_id) is not None:
                return False
            acl = self.get_acl(source_id)
            if not acl.live or not can_read_class(role, acl.permission):
                return False
            source = self.store.get_source(source_id)
            if source is None:
                return False
            if tenant_id is not None and source.tenant_id != tenant_id:
                return False
            return True

        return include

    def search(
        self,
        role: str | None,
        query: str,
        *,
        tenant_id: UUID | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        key = (query.strip().lower(), str(role), str(tenant_id))
        cached = self._cache.get(key)
        if cached is not None and (time.monotonic() - cached.at) < self.cache_ttl:
            return {"hits": cached.hits[:limit], "failures": cached.failures[:limit]}
        result = self.index.search(query, limit=limit, include_source=self._gate(role, tenant_id))
        sources = frozenset(
            [h["source_id"] for h in result["hits"]] + [f["source_id"] for f in result["failures"]]
        )
        self._cache[key] = _CacheEntry(
            hits=result["hits"], failures=result["failures"], sources=sources, at=time.monotonic()
        )
        return result

    # ----------------------------------------------------------- removal --

    def remove_source(
        self,
        source_id: str,
        *,
        reason: str,
        revoked_by: str | None = None,
        actor_role: str | None,
    ) -> Tombstone:
        """Authorized removal: tombstone + ACL revocation + invalidation.

        Owner-only (knowledge.remove_source). The propagation clock starts at
        tombstone creation; `invalidate_source` must complete before the
        declared deadline and stamps `propagated_at` on the tombstone.
        """
        if not allowed(actor_role, KnowledgeAction.REMOVE_SOURCE):
            raise PermissionDenied(
                f"Role '{actor_role}' may not remove knowledge sources (owner only)"
            )
        source = self.store.get_source(source_id)
        if source is None:
            raise KeyError(source_id)
        tombstone = make_tombstone(
            source_id, reason=reason, revoked_by=revoked_by
        )
        self._append_tombstone(tombstone)
        acl = self.get_acl(source_id)
        acl.revoked_at = _now_iso()
        acl.updated_at = _now_iso()
        self.set_acl(acl)
        elapsed = self.invalidate_source(source_id)
        done = stamp_propagated(tombstone, at=_now_iso())
        self._rewrite_last_tombstone(source_id, done)
        if parse_iso(done.propagated_at or "") > parse_iso(done.propagation_deadline):
            raise RuntimeError(
                f"tombstone propagation exceeded the declared window: {elapsed:.3f}s"
            )
        return done

    def invalidate_source(self, source_id: str) -> float:
        """Cache + live-index invalidation hook. Returns elapsed seconds."""
        started = time.monotonic()
        self._purge_cache_for(source_id)
        self.index.invalidate_source(source_id)
        return time.monotonic() - started

    def _purge_cache_for(self, source_id: str) -> None:
        self._cache = {
            k: v for k, v in self._cache.items() if source_id not in v.sources
        }

    def _rewrite_last_tombstone(self, source_id: str, tombstone: Tombstone) -> None:
        p = self.store.root / "tombstones.jsonl"
        lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
        out = []
        seen = False
        for line in reversed(lines):
            if not line.strip():
                continue
            d = json.loads(line)
            if not seen and d["source_id"] == source_id:
                out.append(json.dumps(tombstone.to_json(), sort_keys=True))
                seen = True
            else:
                out.append(line)
        p.write_text("\n".join(reversed(out)) + "\n", encoding="utf-8")

    # ------------------------------------------------------------- screen --

    def screen(
        self, role: str | None, tenant_id: UUID | None = None
    ) -> list[dict[str, Any]]:
        """Knowledge-source screen rows: sync status, last good version,
        failures, ACL class, tombstone state — tenant-scoped."""
        rows: list[dict[str, Any]] = []
        for source in self.store.sources(tenant_id):
            acl = self.get_acl(source.source_id)
            tombstone = self.active_tombstone(source.source_id)
            status = self.sync_status(source.source_id)
            failures = self._failures(source.source_id)
            rows.append(
                {
                    "source_id": source.source_id,
                    "root": source.root,
                    "permission_class": acl.permission_class,
                    "acl_revoked_at": acl.revoked_at,
                    "readable": (
                        acl.live
                        and tombstone is None
                        and can_read_class(role, acl.permission)
                    ),
                    "tombstoned": tombstone is not None,
                    "tombstone": tombstone.to_json() if tombstone else None,
                    "sync": status.to_json() if status else SyncStatus(source.source_id).to_json(),
                    "failures": failures,
                }
            )
        return rows

    def _failures(self, source_id: str) -> list[dict[str, Any]]:
        """Everything visibly wrong on one source: quarantine records and
        failed/unsupported extraction queue entries."""
        out: list[dict[str, Any]] = []
        for q in self.store.quarantine(source_id):
            out.append(
                {
                    "kind": "quarantine",
                    "path": q.path,
                    "reason": q.reason,
                    "message": q.message,
                    "occurred_at": q.occurred_at,
                }
            )
        for e in self.store.pending_extractions(source_id):
            if e.status in ("failed", "unsupported"):
                out.append(
                    {
                        "kind": f"extraction:{e.status}",
                        "path": e.path,
                        "reason": e.capability,
                        "message": e.error or "no approved processor for this capability",
                        "occurred_at": e.updated_at,
                    }
                )
        return out

    def quarantine(self, source_id: str) -> list[QuarantineRecord]:
        return self.store.quarantine(source_id)

    def pending(self, source_id: str) -> list[PendingExtraction]:
        return self.store.pending_extractions(source_id)
