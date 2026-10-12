"""A14-2 indexing: deterministic local embeddings + incremental BM25 FTS.

Proves: same text -> same vector (no vendor, no spend); unchanged re-sync
embeds nothing and rewrites no postings; an edit re-embeds only the changed
chunks (hash-keyed); every artifact carries model name + version + digest;
search returns section-aligned verbatim hits.
"""

from __future__ import annotations

import json

from algobots.knowledge.ingest import (
    DeterministicEmbedder,
    EmbeddingModel,
    KnowledgeIndex,
)


def _manifest(store, key):
    return json.loads(
        (store.root / "index" / "embeddings" / key / "manifest.json").read_text()
    )


def test_deterministic_embedder_is_stable_and_model_sensitive():
    base = DeterministicEmbedder()
    v1 = base.embed("bootstrapping methods validation")
    assert v1 == base.embed("bootstrapping methods validation")
    assert len(v1) == base.model.dims
    norm = sum(x * x for x in v1) ** 0.5
    assert abs(norm - 1.0) < 1e-9
    bumped = DeterministicEmbedder(
        model=EmbeddingModel(name=base.model.name, version="2", dims=base.model.dims)
    )
    assert bumped.embed("bootstrapping methods validation") != v1
    assert base.embed("alpha") != base.embed("beta gamma")


def test_unchanged_resync_is_zero_index_work(service, make_source, make_vault, store):
    root, _ = make_vault("notes/simple-note.md", "notes/nested-note.md")
    source = make_source(root)
    index = KnowledgeIndex(store)
    report = index.update(source.source_id)
    assert report.embeddings_new == []
    assert report.fts_sources_rebuilt == []
    assert not report.did_work
    status = service.run_sync(source)
    assert status.embeddings_new == 0
    assert status.status == "ok"


def test_edit_reembeds_only_changed_chunks(service, make_source, make_vault, store):
    root, put = make_vault("notes/simple-note.md")
    source = make_source(root)
    key = service.index.embedder.model.key
    before = set((store.root / "index" / "embeddings" / key).glob("*.json")) - {
        store.root / "index" / "embeddings" / key / "manifest.json"
    }
    # Edit: append a paragraph to the Results section (only that chunk changes).
    note = root / "simple-note.md"
    note.write_text(note.read_text() + "\nAppended result paragraph.\n", encoding="utf-8")
    status = service.run_sync(source)
    after = set((store.root / "index" / "embeddings" / key).glob("*.json")) - {
        store.root / "index" / "embeddings" / key / "manifest.json"
    }
    new_files = after - before
    assert len(new_files) == status.embeddings_new >= 1
    assert before <= after  # untouched chunk vectors are reused, not recomputed


def test_model_version_bump_reembeds_all(service, make_source, make_vault, store):
    root, _ = make_vault("notes/simple-note.md")
    source = make_source(root)
    old_key = service.index.embedder.model.key
    bumped = DeterministicEmbedder(
        model=EmbeddingModel(name="hashed-bag", version="2", dims=128)
    )
    service.index.embedder = bumped
    report = service.index.update(source.source_id)
    assert len(report.embeddings_new) > 0
    new_key = bumped.model.key
    assert new_key != old_key
    manifest = _manifest(store, new_key)
    assert manifest["model"]["version"] == "2"
    # old artifacts remain inspectable (rebuildable derivatives are kept)
    assert _manifest(store, old_key)["model"]["version"] == "1"


def test_artifacts_track_model_and_version(service, make_source, make_vault, store):
    root, _ = make_vault("notes/simple-note.md")
    make_source(root)
    ledger = json.loads((store.root / "index" / "artifacts.json").read_text())
    kinds = {a["kind"] for a in ledger}
    assert kinds == {"embeddings", "fts"}
    for artifact in ledger:
        assert artifact["model_name"] and artifact["model_version"]
        assert artifact["chunk_count"] >= 1
        assert len(artifact["content_digest"]) == 64
    emb = next(a for a in ledger if a["kind"] == "embeddings")
    assert emb["model_name"] == "hashed-bag" and emb["model_version"] == "1"
    fts = next(a for a in ledger if a["kind"] == "fts")
    assert fts["model_name"] == "bm25" and fts["model_version"] == "1"
    chunk_file = next(
        p
        for p in (store.root / "index" / "embeddings").rglob("*.json")
        if p.name != "manifest.json"
    )
    vector = json.loads(chunk_file.read_text())
    assert vector["model"] == {"name": "hashed-bag", "version": "1"}


def test_fts_search_is_aligned_and_ranked(service, make_source, make_vault, tenant_id):
    root, _ = make_vault("notes/simple-note.md", "notes/nested-note.md")
    source = make_source(root)
    result = service.search("owner", "bootstrapping", tenant_id=tenant_id)
    assert result["hits"], "expected bootstrapping hits"
    for hit in result["hits"]:
        assert hit["source_id"] == source.source_id
        assert hit["anchor"], "section-aligned hits carry an anchor"
        assert hit["start_line"] >= 1 and hit["end_line"] >= hit["start_line"]
        assert "bootstrapping" in hit["text"].lower()
        assert hit["path"].endswith(".md")
    scores = [h["score"] for h in result["hits"]]
    assert scores == sorted(scores, reverse=True)
    # verbatim: the appendix fence hash is code, never a heading/chunk split
    appendix = service.search("owner", "appendix", tenant_id=tenant_id)
    assert appendix["hits"]
    assert all("```python" not in h["text"] or "# this hash is code" in h["text"]
               for h in appendix["hits"])
