"""A14 demo: one vault through import -> edit -> rename -> delete (``make demo-A14``).

Synthetic fixtures only — no stock-vaults live data, no network, no API
spend. Each phase prints the lineage the operator cares about (identity,
versions, citations) plus processing cost (wall time and how many embeddings
the phase actually paid for). Output is teed to artifacts/A14/demo-output.txt.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from algobots.knowledge.ingest import SearchService  # noqa: E402
from algobots.knowledge.ingest.ingest import Ingestor  # noqa: E402
from algobots.knowledge.ingest.store import JsonIngestStore  # noqa: E402

OUT = ROOT / "artifacts" / "A14" / "demo-output.txt"
TENANT = uuid4()
LINES: list[str] = []


def say(line: str = "") -> None:
    print(line)
    LINES.append(line)


NOTE_V1 = """---
title: KXBTC15M Regime Notes
page: 7
tags: [regime, kxbtc]
---

Preamble on regime detection.

# Volatility Regimes

The 15m series separates compressed from expanded regimes.

## Bootstrapping

Walk-forward windows bootstrap the thresholds.

# Execution

Execution slices follow the regime state.
"""

NOTE_V2_ADDITION = """

## Cost Analysis

Editing this note adds a fresh section with new evidence text.
"""


def phase(title: str) -> None:
    say()
    say(f"== {title} " + "=" * max(0, 66 - len(title)))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="a14-demo-"))
    vault = tmp / "vault" / "notes"
    vault.mkdir(parents=True)
    note = vault / "regime-notes.md"
    note.write_text(NOTE_V1)

    say("A14 — Obsidian ingestion & lineage demo (synthetic vault, offline)")
    say(f"vault root : {tmp / 'vault'}")
    say(f"store      : {tmp / 'store'}")

    store = JsonIngestStore(tmp / "store")
    service = SearchService(store)

    # ---- phase 1: import ------------------------------------------------
    phase("1. import")
    t0 = time.perf_counter()
    source = Ingestor.register_source(
        store, tenant_id=TENANT, root=tmp / "vault", acl_ref="demo"
    )
    first = service.run_sync(source)
    import_ms = (time.perf_counter() - t0) * 1000
    doc = store.documents(source.source_id)[0]
    say(f"source_id           : {source.source_id}")
    say(f"doc_id              : {doc.doc_id}")
    say(f"snapshot            : {first.last_snapshot_id}")
    say(f"docs / chunks       : {first.docs} / {first.chunks_indexed}")
    say(f"embeddings paid     : {first.embeddings_new} (first import embeds everything)")
    say(f"processing cost     : {import_ms:.0f} ms")
    citation = service.search("owner", "bootstrapping", tenant_id=TENANT)["hits"][0]
    say(f"citation            : chunk {citation['chunk_id'][:16]}… at {citation['path']}#"
        f"{citation['anchor']} (v {citation['version_id'][:16]}…)")

    # ---- phase 2: edit ---------------------------------------------------
    phase("2. edit -> new version; edited doc re-embeds, others untouched")
    note.write_text(NOTE_V1 + NOTE_V2_ADDITION)
    t0 = time.perf_counter()
    edited = service.run_sync(source)
    edit_ms = (time.perf_counter() - t0) * 1000
    doc2 = store.get_document(doc.doc_id)
    say(f"doc_id              : {doc2.doc_id} (unchanged — identity survives edits)")
    say(f"version chain       : {len(doc2.version_history)} versions "
        f"({', '.join(v[:12] + '…' for v in doc2.version_history)})")
    say(f"embeddings paid     : {edited.embeddings_new} (chunk ids are version-keyed,")
    say("                      so the edited document re-embeds; other documents reuse)")
    say(f"processing cost     : {edit_ms:.0f} ms")
    hit = SearchService(store).search("owner", "cost analysis", tenant_id=TENANT)["hits"][0]
    say(f"new section cited   : {hit['path']}#{hit['anchor']} (v {hit['version_id'][:12]}…)")
    # Citation of an unchanged section under the current version — the
    # reference the rename phase must keep stable.
    citation_v2 = SearchService(store).search("owner", "bootstrapping", tenant_id=TENANT)[
        "hits"
    ][0]
    # ---- phase 3: rename -------------------------------------------------
    phase("3. rename -> identity and citations kept, zero embeddings")
    note.rename(vault / "regime-notes-renamed.md")
    t0 = time.perf_counter()
    renamed = service.run_sync(source)
    rename_ms = (time.perf_counter() - t0) * 1000
    doc3 = store.get_document(doc.doc_id)
    say(f"doc_id              : {doc3.doc_id} (unchanged — identity survives renames)")
    say(f"current path        : {doc3.current_path}")
    say(f"path history        : {len(doc3.path_history)} entries "
        f"(first seen in snapshot {doc3.path_history[0].first_seen[:12]}…)")
    say(f"embeddings paid     : {renamed.embeddings_new} (rename re-embeds nothing)")
    say(f"processing cost     : {rename_ms:.0f} ms")
    hit = SearchService(store).search("owner", "bootstrapping", tenant_id=TENANT)["hits"][0]
    same = hit["chunk_id"] == citation_v2["chunk_id"]
    say(f"citation stable     : {same} — chunk {hit['chunk_id'][:16]}… now at {hit['path']}")

    # ---- phase 4: delete -------------------------------------------------
    phase("4. delete -> exposure ceases, lineage kept")
    t0 = time.perf_counter()
    tombstone = service.remove_source(
        source.source_id, reason="demo removal", revoked_by="user-demo", actor_role="owner"
    )
    delete_ms = (time.perf_counter() - t0) * 1000
    exposure = service.search("owner", "bootstrapping", tenant_id=TENANT)
    say(f"propagation         : {delete_ms:.0f} ms (window {60}s) — tombstone "
        f"propagated_at {tombstone.propagated_at is not None}")
    say(f"exposure after      : {len(exposure['hits'])} hits, "
        f"{len(exposure['failures'])} failures")
    say(f"visible sources     : {len(service.visible_sources('owner', TENANT))}")
    say(f"lineage kept        : {len(store.documents(source.source_id))} documents, "
        f"{len(store.versions(doc.doc_id))} versions remain on record (canon-first)")

    say()
    say(f"totals: import {import_ms:.0f} ms, edit {edit_ms:.0f} ms, "
        f"rename {rename_ms:.0f} ms, delete {delete_ms:.0f} ms — all local, zero API spend")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(LINES) + "\n")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
