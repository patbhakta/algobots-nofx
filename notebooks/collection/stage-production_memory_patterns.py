import marimo

__generated_with = "0.25.1"
app = marimo.App()


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Production Memory Patterns

    > **Getting agent memory to work in a demo is straightforward. Keeping it fast, cheap, private, and reliable at scale is the real challenge. Production memory patterns bridge the gap between "it works on my laptop" and "it serves a million users."**

    Most agent memory tutorials stop at "store embeddings in a vector DB." But in production you face questions they never cover: What happens when your memory store grows to 50 GB? How do you keep retrieval under 100 ms when some users have 10,000 memories? What about GDPR (Europe's privacy law): can you delete every trace of a user across embeddings, graphs, and caches? How do you stop a runaway agent from burning $500 in embedding calls overnight?

    Think of this like building a restaurant kitchen vs. cooking at home. At home you have one pan and one fridge. In a restaurant, you need a hot line (for dishes being served now), a walk-in cooler (for today's ingredients), and a deep freezer (for long-term storage). You also need health inspections, cost controls, and backup plans for when the power goes out.

    This notebook implements **deployment-grade memory infrastructure** covering six pillars:

    1. **Tiered storage:** Hot (in-memory/Redis), warm (Postgres + pgvector), and cold (compressed archive) tiers with automatic promotion and demotion based on access patterns.
    2. **Graph relationships:** An entity-relationship layer for structured knowledge that complements vector similarity.
    3. **Privacy & PII handling:** Detection, redaction, and complete user deletion ("right to forget") across all tiers.
    4. **Memory budget enforcement:** Hard limits on token count, memory count, and storage per user to prevent unbounded growth.
    5. **Cost control:** Tracking and capping spend on embeddings, LLM extraction, and storage.
    6. **Observability:** Structured metrics for latency, cache hit rates, tier distribution, and cost.

    **By the end of this notebook you'll have:**
    - A working tiered memory system with hot/warm/cold storage.
    - PII (personally identifiable information) detection and redaction with full user data deletion.
    - Budget enforcement that prevents runaway memory growth.
    - Cost tracking with configurable spend limits.
    - A clear mental model for production memory architecture.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Key Concepts

    - **Hot/warm/cold tiers:** A storage hierarchy. Think of it like a kitchen: the hot tier is your countertop (instant access, limited space), the warm tier is your fridge (fast access, larger capacity), and the cold tier is your basement freezer (slow access, huge and cheap). Frequently accessed memories live in fast but expensive storage. Rarely accessed ones go to compressed cold archives.
    - **Redis for short-term memory:** Redis is an in-memory data store providing sub-millisecond reads. You use it for recent context, session state, and frequently retrieved user facts. TTL-based expiry (automatic deletion after a set time) keeps it lean.
    - **Postgres + pgvector for long-term memory:** A relational database with vector similarity search. It combines the reliability and query flexibility of Postgres with embedding-based retrieval. This is the workhorse tier for most production systems.
    - **Graph DB for relationships:** Entity-relationship storage (e.g., Neo4j, or a lightweight in-process graph) that captures structured knowledge. For example: "Alice works_at Anthropic." This enables traversal queries that vector similarity cannot answer.
    - **Privacy & PII handling:** Detecting personally identifiable information (names, emails, SSNs) in memories before storage, redacting or encrypting sensitive fields, and implementing complete user data deletion across all tiers for GDPR/CCPA compliance.
    - **Memory budget enforcement:** Hard limits on per-user memory count, total tokens stored, and storage bytes. Enforced via eviction policies (LRU means "least recently used gets removed"; importance-weighted means "least important gets removed") that automatically prune low-value memories when budgets are exceeded.
    - **Cost control:** Tracking the dollar cost of each memory operation (embedding generation, LLM extraction, storage) and enforcing spend caps per user, per day, and globally to prevent bill shock.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Architecture

    <p align="center">
      <img src="../../images/diagrams/30_production_memory_patterns.svg" alt="diagram" width="720"/>
    </p>

    <details><summary>Mermaid source</summary>

    ```mermaid
    flowchart TD
        subgraph Ingestion["Memory Ingestion"]
            MSG["New Message"] --> PII["PII Scanner\n& Redactor"]
            PII --> EXT["Fact Extractor\n(LLM)"]
            EXT --> EMB["Embedding\nGenerator"]
            EMB --> COST["Cost Tracker\n$ gate"]
        end

        subgraph Tiers["Tiered Storage"]
            direction LR
            HOT["Hot Tier\n─────────\nIn-Memory / Redis\nTTL: minutes-hours\nLatency: <1ms"]
            WARM["Warm Tier\n─────────\nPostgres + pgvector\nTTL: days-months\nLatency: 5-50ms"]
            COLD["Cold Tier\n─────────\nCompressed Archive\nTTL: indefinite\nLatency: 100ms+"]
        end

        subgraph Graph["Relationship Layer"]
            GDB[("Entity Graph\n─────────\nnodes / edges\ntraversal queries")]
        end

        subgraph Controls["Guardrails"]
            BUD["Budget Enforcer\nmax tokens / max count"]
            PRV["Privacy Manager\nGDPR delete / audit log"]
            OBS["Observability\nmetrics / alerts"]
        end

        COST --> HOT
        HOT -->|"demote\n(TTL expiry)"| WARM
        WARM -->|"demote\n(low access)"| COLD
        COLD -->|"promote\n(re-accessed)"| WARM
        WARM -->|"promote\n(hot query)"| HOT
        EXT --> GDB

        HOT & WARM & COLD --> BUD
        HOT & WARM & COLD --> PRV
        HOT & WARM & COLD --> OBS

        style HOT fill:#ef4444,color:#fff
        style WARM fill:#f59e0b,color:#fff
        style COLD fill:#3b82f6,color:#fff
        style GDB fill:#8b5cf6,color:#fff
        style PII fill:#059669,color:#fff
        style COST fill:#d97706,color:#fff
    ```

    </details>
    """)
    return


@app.cell
def _():
    # Install required packages (run once)
    # '%pip install -q anthropic python-dotenv numpy' command supported automatically in marimo
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    We import the required libraries and set up the Anthropic client. You need an `ANTHROPIC_API_KEY` in your `.env` file.
    """)
    return


@app.cell
def _():
    import os
    import json
    import re
    import time
    import hashlib
    import zlib
    from collections import defaultdict
    from dataclasses import dataclass, field
    from datetime import datetime, timedelta
    from enum import Enum
    from typing import Any

    import numpy as np
    from dotenv import load_dotenv
    import anthropic

    load_dotenv()

    assert os.getenv("ANTHROPIC_API_KEY"), "Set ANTHROPIC_API_KEY in your .env file"
    client = anthropic.Anthropic()

    print("✓ API key loaded")
    print(f"✓ anthropic version: {anthropic.__version__}")
    return (
        Enum,
        anthropic,
        dataclass,
        datetime,
        defaultdict,
        field,
        hashlib,
        json,
        np,
        re,
        time,
        timedelta,
        zlib,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Core Implementation

    ### Data Model & Tier Definitions

    Every memory record carries metadata that the tiered system uses for placement decisions: access count, last access time, importance score, and the current tier. The system automatically promotes and demotes records based on access patterns.
    """)
    return


@app.cell
def _(Enum, dataclass, datetime, field):
    class MemoryTier(Enum):
        """Storage tier for a memory record."""
        HOT = 'hot'  # In-memory / Redis - sub-millisecond reads
        WARM = 'warm'  # Postgres + pgvector - millisecond reads
        COLD = 'cold'  # Compressed archive - 100ms+ reads

    @dataclass
    class MemoryRecord:
        """A single memory entry with production metadata."""
        id: str
        user_id: str
        content: str
        embedding: list[float] | None = None
        created_at: datetime = field(default_factory=datetime.utcnow)
        last_accessed: datetime = field(default_factory=datetime.utcnow)
        access_count: int = 0
        importance: float = 0.5
        tier: MemoryTier = MemoryTier.WARM  # 0.0 = trivial, 1.0 = critical
        ttl_seconds: int | None = None
        tags: list[str] = field(default_factory=list)  # None = no expiry
        pii_redacted: bool = False
        token_estimate: int = 0
        compressed_bytes: bytes | None = None  # approximate tokens in content
      # for cold tier
        def is_expired(self) -> bool:
            if self.ttl_seconds is None:
                return False
            age = (datetime.utcnow() - self.created_at).total_seconds()
            return age > self.ttl_seconds

        def touch(self):
            """Record an access event."""
            self.last_accessed = datetime.utcnow()
            self.access_count = self.access_count + 1

        def __repr__(self) -> str:
            short = self.content[:45] + '...' if len(self.content) > 45 else self.content
            return f'Memory({self.id}, tier={self.tier.value}, accesses={self.access_count}: {short})'

    def estimate_tokens(text: str) -> int:
        """Rough token estimate: ~4 chars per token for English text."""
        return max(1, len(text) // 4)
    print('✓ MemoryTier enum and MemoryRecord dataclass defined')
    return MemoryRecord, MemoryTier, estimate_tokens


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Hot Tier: In-Memory Cache with TTL

    The hot tier simulates a Redis-like cache: sub-millisecond reads, automatic TTL expiry (records disappear after their time-to-live runs out), and LRU eviction (when at capacity, the least recently used record gets removed) to the warm tier.

    In production you'd use actual Redis. Here we implement the same semantics in Python to keep the notebook self-contained.

    **Key design decisions:**
    - Fixed capacity per user (configurable). This prevents any single user from monopolizing cache.
    - TTL-based expiry checked on every read. No background thread is needed.
    - LRU eviction when at capacity: the least recently accessed record gets demoted to warm tier.
    """)
    return


@app.cell
def _(MemoryRecord, MemoryTier, defaultdict):
    class HotTierCache:
        """In-memory cache simulating Redis with TTL and LRU eviction.

        In production, replace with redis-py:
            import redis
            r = redis.Redis(host='localhost', port=6379)
            r.setex(key, ttl, json.dumps(record))
        """

        def __init__(self, max_per_user: int=50, default_ttl: int=3600):
            self.store: dict[str, MemoryRecord] = {}  # id -> record
            self.user_index: dict[str, set[str]] = defaultdict(set)  # user_id -> {ids}
            self.max_per_user = max_per_user
            self.default_ttl = default_ttl
            self.stats = {'hits': 0, 'misses': 0, 'evictions': 0, 'expirations': 0}

        def put(self, record: MemoryRecord) -> MemoryRecord | None:
            """Cache a record. Returns evicted record if capacity exceeded."""
            record.tier = MemoryTier.HOT
            if record.ttl_seconds is None:
                record.ttl_seconds = self.default_ttl
            evicted = None
            user_ids = self.user_index[record.user_id]
            if len(user_ids) >= self.max_per_user and record.id not in user_ids:
                lru_id = min(user_ids, key=lambda rid: self.store[rid].last_accessed)
                evicted = self.store.pop(lru_id)  # Evict LRU if at capacity
                user_ids.discard(lru_id)
                evicted.tier = MemoryTier.WARM
                self.stats['evictions'] = self.stats['evictions'] + 1
            self.store[record.id] = record
            user_ids.add(record.id)  # demote
            return evicted

    return (HotTierCache,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    We add the remaining methods to `HotTierCache`. The `get` method checks for expiry before returning a record. `get_user_records` purges expired entries on read. `delete_user` removes all of a user's cached records at once.
    """)
    return


@app.cell
def _(HotTierCache, MemoryRecord):
    def get(self, record_id: str) -> MemoryRecord | None:
        """Retrieve a record, returning None on miss or expiry."""
        record = self.store.get(record_id)
        if record is None:
            self.stats['misses'] = self.stats['misses'] + 1
            return None
        if record.is_expired():
            self._remove(record)
            self.stats['expirations'] = self.stats['expirations'] + 1
            self.stats['misses'] = self.stats['misses'] + 1
            return None
        record.touch()
        self.stats['hits'] = self.stats['hits'] + 1
        return record

    def _remove(self, record: MemoryRecord):
        self.store.pop(record.id, None)
        self.user_index[record.user_id].discard(record.id)

    def _get_user_records(self, user_id: str) -> list[MemoryRecord]:
        """Get all cached records for a user (purging expired ones)."""
        ids = list(self.user_index.get(user_id, set()))
        records = []
        for rid in ids:
            r = self.store.get(rid)
            if r and (not r.is_expired()):
                records.append(r)
            elif r:
                self._remove(r)
                self.stats['expirations'] = self.stats['expirations'] + 1
        return records

    def _delete_user(self, user_id: str) -> int:
        """Delete all records for a user. Returns count deleted."""
        ids = list(self.user_index.pop(user_id, set()))
        for rid in ids:
            self.store.pop(rid, None)
        return len(ids)

    @property
    def hit_rate(self) -> float:
        total = self.stats['hits'] + self.stats['misses']
        return self.stats['hits'] / total if total > 0 else 0.0

    def __len__(self):
        return len(self.store)
    HotTierCache.get = get
    HotTierCache._remove = _remove
    HotTierCache.get_user_records = _get_user_records
    HotTierCache.delete_user = _delete_user
    HotTierCache.hit_rate = hit_rate
    HotTierCache.__len__ = __len__
    print('✓ HotTierCache defined (Redis-like in-memory cache with TTL + LRU)')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Warm Tier: Vector Store (Postgres + pgvector)

    The warm tier simulates Postgres with the pgvector extension: persistent storage with embedding-based similarity search. This is the workhorse tier where most memories live.

    **In production** you'd use actual pgvector:
    ```sql
    CREATE TABLE memories (
        id UUID PRIMARY KEY,
        user_id UUID NOT NULL,
        content TEXT,
        embedding vector(1536),
        created_at TIMESTAMPTZ,
        importance FLOAT
    );
    CREATE INDEX ON memories USING ivfflat (embedding vector_cosine_ops);
    ```

    Here we implement the same retrieval semantics using NumPy for cosine similarity (a measure of how similar two vectors are, from -1 to 1).
    """)
    return


@app.cell
def _(MemoryRecord, MemoryTier, defaultdict):
    class WarmTierStore:
        """Simulates Postgres + pgvector with cosine similarity search.

        In production, replace with:
            import psycopg2
            cur.execute(
                "SELECT * FROM memories WHERE user_id = %s "
                "ORDER BY embedding <=> %s::vector LIMIT %s",
                (user_id, query_embedding, k)
            )
        """

        def __init__(self):
            self.records: dict[str, MemoryRecord] = {}
            self.user_index: dict[str, set[str]] = defaultdict(set)

        def put(self, record: MemoryRecord) -> None:
            record.tier = MemoryTier.WARM
            record.compressed_bytes = None  # decompress if promoted from cold
            self.records[record.id] = record
            self.user_index[record.user_id].add(record.id)

        def get(self, record_id: str) -> MemoryRecord | None:
            record = self.records.get(record_id)
            if record:
                record.touch()
            return record

    return (WarmTierStore,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Now we add search and housekeeping methods to the warm tier. The `search` method computes cosine similarity (a measure of how similar two vectors are) between the query embedding and stored embeddings. `get_low_access_records` finds stale records that haven't been touched in a while. These are candidates for demotion to cold storage.
    """)
    return


@app.cell
def _(MemoryRecord, WarmTierStore, np):
    def search(self, user_id: str, query_embedding: list[float], k: int = 5) -> list[MemoryRecord]:
        """Cosine similarity search over user memories."""
        user_ids = self.user_index.get(user_id, set())
        if not user_ids:
            return []

        candidates = []
        q = np.array(query_embedding)
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            return []

        for rid in user_ids:
            record = self.records[rid]
            if record.embedding is None:
                continue
            e = np.array(record.embedding)
            e_norm = np.linalg.norm(e)
            if e_norm == 0:
                continue
            sim = float(np.dot(q, e) / (q_norm * e_norm))
            candidates.append((sim, record))

        candidates.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in candidates[:k]]
        for r in results:
            r.touch()
        return results

    WarmTierStore.search = search
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    These smaller methods handle user-level operations. `get_user_records` returns all of a user's stored memories. `get_low_access_records` finds records not accessed in the last N days. These stale records are candidates for demotion to cold storage.
    """)
    return


@app.cell
def _(MemoryRecord, WarmTierStore, datetime, timedelta):
    def _get_user_records(self, user_id: str) -> list[MemoryRecord]:
        return [self.records[rid] for rid in self.user_index.get(user_id, set())]

    def _delete_user(self, user_id: str) -> int:
        ids = list(self.user_index.pop(user_id, set()))
        for rid in ids:
            self.records.pop(rid, None)
        return len(ids)

    def get_low_access_records(self, user_id: str, threshold_days: int=30) -> list[MemoryRecord]:
        """Find records not accessed in the last N days (candidates for cold demotion)."""
        cutoff = datetime.utcnow() - timedelta(days=threshold_days)
        return [self.records[rid] for rid in self.user_index.get(user_id, set()) if self.records[rid].last_accessed < cutoff]

    def remove(self, record_id: str) -> MemoryRecord | None:
        record = self.records.pop(record_id, None)
        if record:
            self.user_index[record.user_id].discard(record_id)
        return record

    def __len___1(self):
        return len(self.records)
    WarmTierStore.get_user_records = _get_user_records
    WarmTierStore.delete_user = _delete_user
    WarmTierStore.get_low_access_records = get_low_access_records
    WarmTierStore.remove = remove
    WarmTierStore.__len__ = __len___1
    print('✓ WarmTierStore defined (pgvector-like vector store with cosine similarity)')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Cold Tier: Compressed Archive

    The cold tier stores rarely accessed memories in compressed form. In production this could be S3 + Glacier (Amazon's cheap archival storage), or compressed columns in a separate Postgres table. Reads are slower, but storage costs are minimal.

    **Demotion criteria:** No access in 30+ days and low importance score.
    **Promotion:** When a cold memory is accessed, it gets decompressed and moved back to warm.
    """)
    return


@app.cell
def _(MemoryRecord, MemoryTier, defaultdict, zlib):
    class ColdTierArchive:
        """Compressed cold storage for rarely accessed memories.

        In production, replace with:
            - S3 with lifecycle policies (S3 -> Glacier after 90 days)
            - Postgres partitioned table with TOAST compression
            - Separate cold-storage database
        """

        def __init__(self):
            self.records: dict[str, MemoryRecord] = {}
            self.user_index: dict[str, set[str]] = defaultdict(set)
            self.bytes_saved: int = 0

        def archive(self, record: MemoryRecord) -> None:
            """Compress and store a memory record."""
            record.tier = MemoryTier.COLD
            original_size = len(record.content.encode('utf-8'))
            record.compressed_bytes = zlib.compress(record.content.encode('utf-8'))
            record.embedding = None  # drop embedding to save space
            compressed_size = len(record.compressed_bytes)
            self.bytes_saved = self.bytes_saved + (original_size - compressed_size)
            self.records[record.id] = record
            self.user_index[record.user_id].add(record.id)

        def retrieve(self, record_id: str) -> MemoryRecord | None:
            """Decompress and return a cold record (for promotion back to warm)."""
            record = self.records.get(record_id)
            if record and record.compressed_bytes:
                record.content = zlib.decompress(record.compressed_bytes).decode('utf-8')
                record.touch()
            return record

        def get_user_records(self, user_id: str) -> list[MemoryRecord]:
            return [self.records[rid] for rid in self.user_index.get(user_id, set())]

        def delete_user(self, user_id: str) -> int:
            ids = list(self.user_index.pop(user_id, set()))
            for rid in ids:
                self.records.pop(rid, None)
            return len(ids)

        def remove(self, record_id: str) -> MemoryRecord | None:
            return self.records.pop(record_id, None)

        def __len__(self):
            return len(self.records)
    print('✓ ColdTierArchive defined (zlib-compressed cold storage)')
    return (ColdTierArchive,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Graph Relationship Store

    Vector similarity is great for "find memories related to X." But it can't answer structured queries like "who does Alice work with?" or "what are all the places the user has lived?" A lightweight entity-relationship graph complements vector search for these cases.

    Think of it like a social network map. Vector search finds things that *sound similar*. Graph search finds things that are *connected*. Both are useful, and they answer different types of questions.

    **In production** you'd use Neo4j, Amazon Neptune, or even Postgres with recursive CTEs (a SQL feature for traversing relationships). Here we use an adjacency-list graph (a dictionary mapping each entity to its connections).
    """)
    return


@app.cell
def _(dataclass, datetime, field):
    @dataclass
    class GraphEdge:
        """A relationship between two entities."""
        source: str         # e.g., "Alice"
        relation: str       # e.g., "works_at"
        target: str         # e.g., "Anthropic"
        user_id: str
        timestamp: datetime = field(default_factory=datetime.utcnow)
        memory_id: str | None = None  # link back to source memory

    return (GraphEdge,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    `GraphRelationshipStore` is a lightweight in-memory graph. It maps entity names to their connections using an adjacency list (a dictionary where each key is an entity and the value is its list of edges). The `get_neighbors` method does BFS (breadth-first search) to find all entities within N hops.
    """)
    return


@app.cell
def _(GraphEdge, defaultdict):
    class GraphRelationshipStore:
        """Lightweight entity-relationship graph.

        In production, replace with:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(uri, auth=(user, password))
            session.run(
                "MERGE (a:Entity {name: $source}) "
                "MERGE (b:Entity {name: $target}) "
                "CREATE (a)-[:REL {type: $rel}]->(b)",
                source=edge.source, target=edge.target, rel=edge.relation
            )
        """

        def __init__(self):
            self.edges: list[GraphEdge] = []
            self.adjacency: dict[str, list[GraphEdge]] = defaultdict(list)

        def add_edge(self, edge: GraphEdge) -> None:
            self.edges.append(edge)
            self.adjacency[edge.source.lower()].append(edge)

        def query(self, entity: str, relation: str | None = None) -> list[GraphEdge]:
            """Find edges from an entity, optionally filtered by relation type."""
            edges = self.adjacency.get(entity.lower(), [])
            if relation:
                edges = [e for e in edges if e.relation == relation]
            return edges

        def get_neighbors(self, entity: str, depth: int = 1) -> set[str]:
            """BFS traversal to find entities within N hops."""
            visited = set()
            frontier = {entity.lower()}
            for _ in range(depth):
                next_frontier = set()
                for node in frontier:
                    if node in visited:
                        continue
                    visited.add(node)
                    for edge in self.adjacency.get(node, []):
                        next_frontier.add(edge.target.lower())
                frontier = next_frontier - visited
            return visited | frontier

        def delete_user(self, user_id: str) -> int:
            """Delete all edges for a user."""
            original = len(self.edges)
            self.edges = [e for e in self.edges if e.user_id != user_id]
            # Rebuild adjacency
            self.adjacency.clear()
            for edge in self.edges:
                self.adjacency[edge.source.lower()].append(edge)
            return original - len(self.edges)

        def __len__(self):
            return len(self.edges)


    print("✓ GraphRelationshipStore defined (adjacency-list entity graph)")
    return (GraphRelationshipStore,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Privacy & PII Handling

    Production memory systems must handle personally identifiable information (PII) carefully. PII includes things like email addresses, phone numbers, social security numbers, and credit card numbers. This module provides:

    1. **Detection:** Regex-based scanning for common PII patterns (emails, phones, SSNs).
    2. **Redaction:** Replace detected PII with placeholder tokens before storage.
    3. **Right to forget:** Complete deletion of all user data across every tier and the graph store.
    4. **Audit logging:** Track every deletion for compliance records.

    > **Note:** In production, use a dedicated PII detection service (e.g., AWS Comprehend, Google DLP, or Microsoft Presidio) instead of regex patterns. Regex catches common formats but misses context-dependent PII like names or addresses.
    """)
    return


@app.cell
def _(datetime, re):
    class PIIHandler:
        """Detect, redact, and manage PII in memory content.

        In production, consider:
            - Microsoft Presidio (open-source, pluggable)
            - AWS Comprehend PII detection
            - Google Cloud DLP
            - Custom NER models for domain-specific PII
        """

        # Common PII patterns (US-centric; extend for other locales)
        PII_PATTERNS = {
            "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
            "phone_us": re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
            "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
            "credit_card": re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
            "ip_address": re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
        }

        def __init__(self):
            self.audit_log: list[dict] = []

        def scan(self, text: str) -> dict[str, list[str]]:
            """Scan text for PII. Returns {pii_type: [matched_values]}."""
            found = {}
            for pii_type, pattern in self.PII_PATTERNS.items():
                matches = pattern.findall(text)
                if matches:
                    found[pii_type] = matches
            return found

        def redact(self, text: str) -> tuple[str, dict[str, list[str]]]:
            """Redact PII from text. Returns (redacted_text, detected_pii)."""
            detected = self.scan(text)
            redacted = text
            for pii_type, values in detected.items():
                for value in values:
                    placeholder = f"[REDACTED_{pii_type.upper()}]"
                    redacted = redacted.replace(value, placeholder)
            return redacted, detected

        def log_deletion(self, user_id: str, tier: str, count: int):
            """Record a deletion event for compliance audit."""
            self.audit_log.append({
                "action": "user_data_deletion",
                "user_id": user_id,
                "tier": tier,
                "records_deleted": count,
                "timestamp": datetime.utcnow().isoformat(),
            })

    return (PIIHandler,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Let's test the PII scanner. We run three sample texts through it. The first two contain emails, phone numbers, SSNs, and credit card numbers. The third has no PII. Watch how the redactor replaces each detected value with a labeled placeholder.
    """)
    return


@app.cell
def _(PIIHandler):
    # ── Demo PII detection ──
    pii = PIIHandler()

    test_texts = [
        "My email is alice@example.com and my phone is (555) 123-4567.",
        "SSN: 123-45-6789, credit card 4111-1111-1111-1111.",
        "Alice works at Anthropic as a senior engineer.",  # no PII
    ]

    print("\u2713 PIIHandler defined\n")
    print("\u2500\u2500 PII Detection Demo \u2500\u2500")
    for text in test_texts:
        redacted, found = pii.redact(text)
        if found:
            print(f"  Original:  {text}")
            print(f"  Redacted:  {redacted}")
            print(f"  Found PII: {found}\n")
        else:
            print(f"  Clean:     {text}\n")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Memory Budget Enforcement

    Without hard limits, memory stores grow without bound. One power user could store 100,000 memories and drag down query latency for everyone. Budget enforcement caps growth per user and evicts low-value memories when limits are hit.

    **Three budget dimensions:**
    1. **Max memory count:** hard limit on number of records per user.
    2. **Max tokens:** total token budget across all memories (controls how much context window they consume).
    3. **Eviction policy:** when over budget, score each memory by `importance x recency` and evict the lowest-scoring ones.
    """)
    return


@app.cell
def _(MemoryRecord, datetime):
    class MemoryBudgetEnforcer:
        """Enforce per-user memory limits with importance-weighted eviction.

        Budget is checked on every write. When exceeded, lowest-value
        memories are returned for demotion or deletion.
        """

        def __init__(self, max_memories_per_user: int=500, max_tokens_per_user: int=100000):
            self.max_memories = max_memories_per_user
            self.max_tokens = max_tokens_per_user

        def check_budget(self, records: list[MemoryRecord]) -> dict:
            """Check if a user's memories exceed budget limits.

            Returns:
                dict with 'over_count', 'over_tokens', 'eviction_candidates'
            """
            total_tokens = sum((r.token_estimate for r in records))
            count = len(records)
            over_count = max(0, count - self.max_memories)
            over_tokens = max(0, total_tokens - self.max_tokens)
            scored = []
            now = datetime.utcnow()
            for r in records:
                age_days = max(1, (now - r.last_accessed).total_seconds() / 86400)
                recency = 1.0 / age_days
                score = r.importance * 0.6 + recency * 0.3 + min(r.access_count / 10, 1.0) * 0.1
                scored.append((score, r))  # Score each record: low score = good candidate for eviction
            scored.sort(key=lambda x: x[0])
            eviction_candidates = []
            tokens_to_free = over_tokens
            count_to_free = over_count
            for score, record in scored:  # more recent = higher score
                if count_to_free <= 0 and tokens_to_free <= 0:
                    break
                eviction_candidates.append(record)
                count_to_free = count_to_free - 1  # lowest score first
                tokens_to_free = tokens_to_free - record.token_estimate
            return {'within_budget': over_count <= 0 and over_tokens <= 0, 'current_count': count, 'current_tokens': total_tokens, 'over_count': over_count, 'over_tokens': over_tokens, 'eviction_candidates': eviction_candidates}
    print('✓ MemoryBudgetEnforcer defined')
    return (MemoryBudgetEnforcer,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Cost Control & Tracking

    Every memory operation has a dollar cost: embedding generation, LLM fact extraction, storage reads/writes. Without tracking, costs creep up silently until the monthly bill arrives. The cost tracker records every operation and enforces configurable spend limits.
    """)
    return


@app.cell
def _(datetime):
    class CostTracker:
        """Track and limit the dollar cost of memory operations.

        Pricing is approximate and configurable; update rates as models change.
        """

        # Approximate pricing (USD) - update for your models
        DEFAULT_RATES = {
            "embedding_per_1k_tokens": 0.00002,     # text-embedding-3-small
            "extraction_input_per_1k": 0.003,        # Claude Sonnet input
            "extraction_output_per_1k": 0.015,       # Claude Sonnet output
            "storage_per_gb_month": 0.25,            # pgvector on managed Postgres
        }

        def __init__(
            self,
            daily_limit: float = 10.0,
            monthly_limit: float = 200.0,
            rates: dict[str, float] | None = None,
        ):
            self.daily_limit = daily_limit
            self.monthly_limit = monthly_limit
            self.rates = rates or self.DEFAULT_RATES
            self.ledger: list[dict] = []

        def record(self, operation: str, tokens: int = 0, details: str = "") -> float:
            """Record a cost event and return the cost in USD."""
            if operation == "embedding":
                cost = (tokens / 1000) * self.rates["embedding_per_1k_tokens"]
            elif operation == "extraction_input":
                cost = (tokens / 1000) * self.rates["extraction_input_per_1k"]
            elif operation == "extraction_output":
                cost = (tokens / 1000) * self.rates["extraction_output_per_1k"]
            else:
                cost = 0.0

            self.ledger.append({
                "operation": operation,
                "tokens": tokens,
                "cost_usd": cost,
                "timestamp": datetime.utcnow().isoformat(),
                "details": details,
            })
            return cost

    return (CostTracker,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    We add reporting methods to the cost tracker. `get_daily_spend` sums today's charges. `check_limits` compares current spend against daily and monthly caps. `get_breakdown` groups costs by operation type so you can see where the money goes.
    """)
    return


@app.cell
def _(CostTracker, datetime, defaultdict):
    def get_daily_spend(self) -> float:
        today = datetime.utcnow().date()
        return sum((e['cost_usd'] for e in self.ledger if datetime.fromisoformat(e['timestamp']).date() == today))

    def get_total_spend(self) -> float:
        return sum((e['cost_usd'] for e in self.ledger))

    def check_limits(self) -> dict:
        daily = self.get_daily_spend()
        total = self.get_total_spend()
        return {'daily_spend': daily, 'daily_limit': self.daily_limit, 'daily_ok': daily < self.daily_limit, 'total_spend': total, 'monthly_limit': self.monthly_limit, 'monthly_ok': total < self.monthly_limit, 'can_proceed': daily < self.daily_limit and total < self.monthly_limit}

    def get_breakdown(self) -> dict[str, float]:
        breakdown: dict[str, float] = defaultdict(float)
        for entry in self.ledger:
            breakdown[entry['operation']] = breakdown[entry['operation']] + entry['cost_usd']
        return dict(breakdown)
    CostTracker.get_daily_spend = get_daily_spend
    CostTracker.get_total_spend = get_total_spend
    CostTracker.check_limits = check_limits
    CostTracker.get_breakdown = get_breakdown
    print('✓ CostTracker defined')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Tiered Memory System: Putting It All Together

    The `TieredMemorySystem` is the main orchestrator. It:
    1. Scans and redacts PII on ingest.
    2. Generates embeddings via the API.
    3. Stores new memories in the hot tier.
    4. Retrieves across all tiers with automatic promotion.
    5. Runs periodic maintenance: TTL expiry, budget enforcement, cold demotion.
    6. Tracks costs for every operation.
    7. Provides full user deletion (GDPR right-to-forget).
    """)
    return


@app.cell
def _(
    ColdTierArchive,
    CostTracker,
    GraphRelationshipStore,
    HotTierCache,
    MemoryBudgetEnforcer,
    PIIHandler,
    WarmTierStore,
    anthropic,
    estimate_tokens,
    hashlib,
    np,
):
    class TieredMemorySystem:
        """Production-grade tiered memory with all guardrails.

        Orchestrates hot/warm/cold tiers, graph store, PII handling,
        budget enforcement, and cost tracking.
        """

        def __init__(
            self,
            hot_max_per_user: int = 20,
            hot_ttl: int = 3600,
            budget_max_memories: int = 100,
            budget_max_tokens: int = 50_000,
            daily_cost_limit: float = 10.0,
        ):
            self.hot = HotTierCache(max_per_user=hot_max_per_user, default_ttl=hot_ttl)
            self.warm = WarmTierStore()
            self.cold = ColdTierArchive()
            self.graph = GraphRelationshipStore()
            self.pii = PIIHandler()
            self.budget = MemoryBudgetEnforcer(
                max_memories_per_user=budget_max_memories,
                max_tokens_per_user=budget_max_tokens,
            )
            self.cost = CostTracker(daily_limit=daily_cost_limit)
            self.client = anthropic.Anthropic()

        def _generate_embedding(self, text: str) -> list[float]:
            """Generate a deterministic pseudo-embedding for demo purposes.

            In production, replace with:
                response = openai.embeddings.create(
                    model="text-embedding-3-small", input=text
                )
                return response.data[0].embedding
            """
            # Hash-based deterministic pseudo-embedding (for demo reproducibility)
            h = hashlib.sha256(text.encode()).digest()
            rng = np.random.RandomState(int.from_bytes(h[:4], "big"))
            emb = rng.randn(256).tolist()
            # Track cost as if we called the real API
            tokens = estimate_tokens(text)
            self.cost.record("embedding", tokens, f"embed: {text[:40]}...")
            return emb

    return (TieredMemorySystem,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `add_memory` method runs the full ingestion pipeline. It scans for PII, redacts sensitive content, generates an embedding, creates a `MemoryRecord`, and stores it in both the hot and warm tiers. If the hot tier is full, the least recently used record gets evicted to warm.
    """)
    return


@app.cell
def _(MemoryRecord, TieredMemorySystem, estimate_tokens, hashlib, time):
    def add_memory(
        self,
        user_id: str,
        content: str,
        importance: float = 0.5,
        tags: list[str] | None = None,
        ttl_seconds: int | None = None,
        redact_pii: bool = True,
    ) -> MemoryRecord:
        """Add a memory through the full ingestion pipeline."""
        # 1. PII scan and redact
        if redact_pii:
            content, detected_pii = self.pii.redact(content)
            pii_redacted = bool(detected_pii)
        else:
            pii_redacted = False

        # 2. Generate embedding
        embedding = self._generate_embedding(content)

        # 3. Create record
        record = MemoryRecord(
            id=hashlib.md5(f"{user_id}:{content}:{time.time()}".encode()).hexdigest()[:12],
            user_id=user_id,
            content=content,
            embedding=embedding,
            importance=importance,
            tags=tags or [],
            ttl_seconds=ttl_seconds,
            pii_redacted=pii_redacted,
            token_estimate=estimate_tokens(content),
        )

        # 4. Store in hot tier (with potential LRU eviction to warm)
        evicted = self.hot.put(record)
        if evicted:
            self.warm.put(evicted)

        # 5. Also store in warm for persistence
        self.warm.put(record)

        return record

    TieredMemorySystem.add_memory = add_memory
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `retrieve` method searches across all three tiers. It checks the hot tier first (fastest), then warm (vector search), then cold (decompressed on access). Records accessed frequently get promoted from warm to hot. Cold records get promoted to warm when touched.
    """)
    return


@app.cell
def _(MemoryRecord, TieredMemorySystem, np):
    def retrieve(
        self,
        user_id: str,
        query: str,
        k: int = 5,
    ) -> list[MemoryRecord]:
        """Retrieve memories across all tiers with automatic promotion."""
        query_embedding = self._generate_embedding(query)
        results = []
        seen_ids = set()

        # 1. Check hot tier first
        hot_records = self.hot.get_user_records(user_id)
        if hot_records:
            q = np.array(query_embedding)
            q_norm = np.linalg.norm(q)
            scored = []
            for r in hot_records:
                if r.embedding is not None:
                    e = np.array(r.embedding)
                    e_norm = np.linalg.norm(e)
                    if e_norm > 0 and q_norm > 0:
                        sim = float(np.dot(q, e) / (q_norm * e_norm))
                        scored.append((sim, r))
            scored.sort(key=lambda x: x[0], reverse=True)
            for _, r in scored[:k]:
                results.append(r)
                seen_ids.add(r.id)

        # 2. Search warm tier
        warm_results = self.warm.search(user_id, query_embedding, k=k)
        for r in warm_results:
            if r.id not in seen_ids:
                results.append(r)
                seen_ids.add(r.id)
                # Promote to hot if accessed frequently
                if r.access_count >= 3:
                    evicted = self.hot.put(r)
                    if evicted and evicted.id != r.id:
                        self.warm.put(evicted)

        # 3. Check cold tier (only if we need more results)
        if len(results) < k:
            cold_records = self.cold.get_user_records(user_id)
            for r in cold_records:
                if r.id not in seen_ids:
                    # Promote to warm on access
                    self.cold.remove(r.id)
                    r.embedding = self._generate_embedding(r.content)
                    self.warm.put(r)
                    results.append(r)
                    seen_ids.add(r.id)
                    if len(results) >= k:
                        break

        return results[:k]

    TieredMemorySystem.retrieve = retrieve
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    These methods handle graph relationships and periodic maintenance. `run_maintenance` enforces budget limits and demotes stale, low-importance records from warm to cold storage.
    """)
    return


@app.cell
def _(GraphEdge, TieredMemorySystem):
    def add_relationship(
        self, user_id: str, source: str, relation: str,
        target: str, memory_id: str | None = None,
    ):
        """Add an entity relationship to the graph store."""
        edge = GraphEdge(
            source=source, relation=relation, target=target,
            user_id=user_id, memory_id=memory_id,
        )
        self.graph.add_edge(edge)

    def query_relationships(self, entity: str, relation: str | None = None) -> list[GraphEdge]:
        return self.graph.query(entity, relation)

    def run_maintenance(self, user_id: str) -> dict:
        """Run maintenance: enforce budgets, demote cold candidates."""
        # 1. Budget enforcement
        all_warm = self.warm.get_user_records(user_id)
        budget_check = self.budget.check_budget(all_warm)

        evicted_to_cold = []
        if not budget_check["within_budget"]:
            for record in budget_check["eviction_candidates"]:
                self.warm.remove(record.id)
                self.cold.archive(record)
                evicted_to_cold.append(record.id)

        # 2. Demote stale warm records to cold
        stale = self.warm.get_low_access_records(user_id, threshold_days=30)
        for record in stale:
            if record.importance < 0.3:  # only demote low-importance
                self.warm.remove(record.id)
                self.cold.archive(record)
                evicted_to_cold.append(record.id)

        return {
            "budget_check": budget_check,
            "demoted_to_cold": evicted_to_cold,
            "hot_count": len(self.hot.get_user_records(user_id)),
            "warm_count": len(self.warm.get_user_records(user_id)),
            "cold_count": len(self.cold.get_user_records(user_id)),
        }

    TieredMemorySystem.add_relationship = add_relationship
    TieredMemorySystem.query_relationships = query_relationships
    TieredMemorySystem.run_maintenance = run_maintenance
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `delete_user` method implements GDPR right-to-forget. It removes all of a user's data across every tier (hot, warm, cold, and graph). Each deletion is logged in the PII audit trail for compliance. `get_stats` returns observability metrics for monitoring.
    """)
    return


@app.cell
def _(TieredMemorySystem):
    def _delete_user(self, user_id: str) -> dict:
        """GDPR right-to-forget: delete ALL user data across all tiers."""
        hot_deleted = self.hot.delete_user(user_id)
        warm_deleted = self.warm.delete_user(user_id)
        cold_deleted = self.cold.delete_user(user_id)
        graph_deleted = self.graph.delete_user(user_id)
        for tier, count in [('hot', hot_deleted), ('warm', warm_deleted), ('cold', cold_deleted), ('graph', graph_deleted)]:
            self.pii.log_deletion(user_id, tier, count)  # Audit log each tier
        return {'user_id': user_id, 'hot_deleted': hot_deleted, 'warm_deleted': warm_deleted, 'cold_deleted': cold_deleted, 'graph_deleted': graph_deleted, 'total_deleted': hot_deleted + warm_deleted + cold_deleted + graph_deleted, 'audit_entries': len(self.pii.audit_log)}

    def get_stats(self) -> dict:
        """Get system-wide observability metrics."""
        return {'tiers': {'hot': {'count': len(self.hot), 'hit_rate': f'{self.hot.hit_rate:.1%}', 'stats': self.hot.stats}, 'warm': {'count': len(self.warm)}, 'cold': {'count': len(self.cold), 'bytes_saved': self.cold.bytes_saved}}, 'graph': {'edges': len(self.graph)}, 'cost': self.cost.check_limits(), 'cost_breakdown': self.cost.get_breakdown()}
    TieredMemorySystem.delete_user = _delete_user
    TieredMemorySystem.get_stats = get_stats
    print('✓ TieredMemorySystem defined - full production orchestrator')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Usage Example: Full Production Pipeline

    Let's walk through the complete lifecycle: adding memories (with PII redaction), retrieving across tiers, querying the graph, enforcing budgets, tracking costs, and finally deleting all of a user's data.
    """)
    return


@app.cell
def _(TieredMemorySystem):
    # ── Initialize the system ──
    system = TieredMemorySystem(hot_max_per_user=5, hot_ttl=3600, budget_max_memories=15, budget_max_tokens=5000, daily_cost_limit=10.0)
    memories_data = [('Alice works at Anthropic as a senior engineer.', 0.9, ['work']), ('Alice lives in San Francisco, CA 94103.', 0.7, ['location']), ('Alice email is alice@anthropic.com and phone is (415) 555-0123.', 0.6, ['contact']), ('Alice prefers Python for data analysis and Rust for systems work.', 0.5, ['programming']), ('Alice is training for the SF marathon in October 2025.', 0.4, ['fitness']), ('Alice has a golden retriever named Max.', 0.3, ['pets']), ('SSN is 123-45-6789 shared for benefits enrollment.', 0.8, ['admin']), ('Alice enjoys hiking in Marin County on weekends.', 0.3, ['hobbies']), ('Credit card 4111-1111-1111-1111 is on file for expenses.', 0.7, ['finance']), ('Alice mentors two junior engineers on the safety team.', 0.5, ['work'])]  # small cache for demo
    print('── Adding Memories (with PII Redaction) ──\n')
    records = []  # tight budget for demo
    for content, importance, tags in memories_data:
        record = system.add_memory('alice', content, importance=importance, tags=tags)
        records.append(record)
        _pii_flag = ' ⚠ PII redacted' if record.pii_redacted else ''
    # ── Add memories for user "alice" ──
        _short = record.content[:65] + '...' if len(record.content) > 65 else record.content
        print(f'  [{record.tier.value:4s}] {record.id}: {_short}{_pii_flag}')
    system.add_relationship('alice', 'Alice', 'works_at', 'Anthropic', records[0].id)
    system.add_relationship('alice', 'Alice', 'lives_in', 'San Francisco', records[1].id)
    system.add_relationship('alice', 'Alice', 'owns_pet', 'Max (golden retriever)', records[5].id)
    system.add_relationship('alice', 'Alice', 'mentors', 'junior engineers', records[9].id)
    system.add_relationship('alice', 'Anthropic', 'located_in', 'San Francisco')
    # ── Add graph relationships ──
    print(f'\n✓ Added {len(records)} memories and {len(system.graph)} graph edges')
    return (system,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Now we retrieve memories using natural language queries. The system searches across all tiers and returns the most relevant records. Watch the tier labels and access counts in the output.
    """)
    return


@app.cell
def _(system):
    # ── Retrieve memories by semantic query ──
    print('── Memory Retrieval ──\n')
    queries = ['What does Alice do for work?', 'Where does Alice live?', 'What programming languages does Alice use?']
    for query in queries:
        results = system.retrieve('alice', query, k=3)
        print(f'  Query: "{query}"')
        for _r in results:
            _short = _r.content[:70]
            print(f'    → [{_r.tier.value}] (importance={_r.importance:.1f}, accesses={_r.access_count}) {_short}')
        print()
    print('── Graph Queries ──\n')
    for _entity in ['Alice', 'Anthropic']:
        _edges = system.query_relationships(_entity)
        print(f'  {_entity}:')
        for _e in _edges:
            print(f'    → {_e.relation} → {_e.target}')
    neighbors = system.graph.get_neighbors('alice', depth=2)
    # ── Graph relationship queries ──
    # Show graph traversal
    print(f'\n  Entities within 2 hops of Alice: {neighbors}')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    We run maintenance to enforce budget limits and demote stale records. The system checks per-user memory count and token limits. Records that exceed the budget get moved to cold storage.
    """)
    return


@app.cell
def _(system):
    # ── Run maintenance (budget enforcement + cold demotion) ──
    print("── Maintenance & Budget Enforcement ──\n")

    maintenance = system.run_maintenance("alice")

    print(f"  Budget within limits: {maintenance['budget_check']['within_budget']}")
    print(f"  Current count: {maintenance['budget_check']['current_count']} / {system.budget.max_memories}")
    print(f"  Current tokens: {maintenance['budget_check']['current_tokens']} / {system.budget.max_tokens}")
    if maintenance["demoted_to_cold"]:
        print(f"  Demoted to cold: {maintenance['demoted_to_cold']}")
    print(f"\n  Tier distribution:")
    print(f"    Hot:  {maintenance['hot_count']}")
    print(f"    Warm: {maintenance['warm_count']}")
    print(f"    Cold: {maintenance['cold_count']}")

    # ── Cost tracking ──
    print("\n── Cost Tracking ──\n")
    stats = system.get_stats()
    cost_info = stats["cost"]
    print(f"  Daily spend:   ${cost_info['daily_spend']:.6f} / ${cost_info['daily_limit']:.2f}")
    print(f"  Total spend:   ${cost_info['total_spend']:.6f} / ${cost_info['monthly_limit']:.2f}")
    print(f"  Within limits: {cost_info['can_proceed']}")

    print(f"\n  Cost breakdown by operation:")
    for op, amount in stats["cost_breakdown"].items():
        print(f"    {op}: ${amount:.6f}")

    print(f"\n  Cache performance:")
    hot_stats = stats["tiers"]["hot"]
    print(f"    Hit rate: {hot_stats['hit_rate']}")
    print(f"    Hits: {hot_stats['stats']['hits']}, Misses: {hot_stats['stats']['misses']}")
    print(f"    Evictions: {hot_stats['stats']['evictions']}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Finally we test the GDPR right-to-forget. Calling `delete_user` wipes all of Alice's data from every tier and the graph store. The audit log records each deletion for compliance purposes.
    """)
    return


@app.cell
def _(system):
    # ── GDPR Right-to-Forget: Complete User Deletion ──
    print("── GDPR User Deletion ──\n")

    # Show what exists before deletion
    print("  Before deletion:")
    print(f"    Hot tier:  {len(system.hot.get_user_records('alice'))} records")
    print(f"    Warm tier: {len(system.warm.get_user_records('alice'))} records")
    print(f"    Cold tier: {len(system.cold.get_user_records('alice'))} records")
    print(f"    Graph:     {len(system.graph.edges)} edges")

    # Execute deletion
    deletion_report = system.delete_user("alice")

    print(f"\n  Deletion complete:")
    print(f"    Hot deleted:   {deletion_report['hot_deleted']}")
    print(f"    Warm deleted:  {deletion_report['warm_deleted']}")
    print(f"    Cold deleted:  {deletion_report['cold_deleted']}")
    print(f"    Graph deleted: {deletion_report['graph_deleted']}")
    print(f"    Total deleted: {deletion_report['total_deleted']}")

    # Verify deletion is complete
    print(f"\n  After deletion:")
    print(f"    Hot tier:  {len(system.hot.get_user_records('alice'))} records")
    print(f"    Warm tier: {len(system.warm.get_user_records('alice'))} records")
    print(f"    Cold tier: {len(system.cold.get_user_records('alice'))} records")
    print(f"    Graph:     {len(system.graph.edges)} edges")

    # Show audit log
    print(f"\n  Audit log ({len(system.pii.audit_log)} entries):")
    for entry in system.pii.audit_log:
        print(f"    [{entry['timestamp']}] {entry['tier']}: {entry['records_deleted']} records deleted")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Bonus: LLM-Powered Fact Extraction with Cost Tracking

    In production, raw conversation turns are processed by an LLM to extract structured facts and relationships before storage. This cell demonstrates the pattern with real API calls and cost tracking.
    """)
    return


@app.cell
def _(TieredMemorySystem, estimate_tokens, json):
    def extract_facts_and_relations(
        text: str,
        user_id: str,
        system: TieredMemorySystem,
        model: str = "claude-sonnet-4-20250514",
    ) -> dict:
        """Extract structured facts and relationships from text using Claude."""

        # Track extraction cost
        input_tokens = estimate_tokens(text) + 200  # prompt overhead
        system.cost.record("extraction_input", input_tokens, "fact extraction")

        response = system.client.messages.create(
            model=model,
            max_tokens=512,
            system=(
                "Extract facts and entity relationships from the text. "
                "Return JSON with: "
                '"facts": [{"content": "...", "importance": 0.0-1.0, "tags": [...]}], '
                '"relationships": [{"source": "...", "relation": "...", "target": "..."}]'
            ),
            messages=[{"role": "user", "content": f"Extract from: {text}"}],
        )

        output_text = response.content[0].text.strip()
        system.cost.record("extraction_output", estimate_tokens(output_text), "fact extraction")

        try:
            if output_text.startswith("```"):
                output_text = output_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            parsed = json.loads(output_text)
        except json.JSONDecodeError:
            parsed = {"facts": [], "relationships": []}

        # Store extracted facts
        added_records = []
        for fact in parsed.get("facts", []):
            record = system.add_memory(
                user_id=user_id,
                content=fact["content"],
                importance=fact.get("importance", 0.5),
                tags=fact.get("tags", []),
            )
            added_records.append(record)

        # Store relationships
        for rel in parsed.get("relationships", []):
            system.add_relationship(
                user_id=user_id,
                source=rel["source"],
                relation=rel["relation"],
                target=rel["target"],
            )

        return {
            "facts_extracted": len(added_records),
            "relationships_extracted": len(parsed.get("relationships", [])),
            "records": added_records,
            "cost_so_far": system.cost.get_total_spend(),
        }

    return (extract_facts_and_relations,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Let's test the extraction pipeline on a realistic conversation snippet. The user mentions a new address, a new job, a new manager, and a new pet. Watch how the extractor pulls structured facts and relationships from unstructured text. Notice that PII (the street address) gets redacted automatically.
    """)
    return


@app.cell
def _(extract_facts_and_relations, system):
    print('── LLM Fact Extraction ──\n')
    conversation = 'User: I just moved to Austin, Texas last week. My new address is 742 Evergreen Terrace, Austin TX 78701. I am starting a new role as a tech lead at Stripe next Monday. My manager will be Sarah Chen. Oh and I adopted a cat named Pixel from the shelter!'
    print(f'  Input: {conversation[:80]}...\n')
    result = extract_facts_and_relations(conversation, 'bob', system)
    print(f"  Facts extracted: {result['facts_extracted']}")
    print(f"  Relationships:   {result['relationships_extracted']}")
    print(f"  Total cost:      ${result['cost_so_far']:.6f}")
    print()
    for _r in result['records']:
        _pii_flag = ' ⚠ PII' if _r.pii_redacted else ''
        print(f'  → {_r.content[:70]}{_pii_flag}')
    print(f"\n  Graph edges for Bob's entities:")
    for _entity in ['bob', 'stripe', 'sarah chen', 'austin', 'pixel']:
        _edges = system.graph.query(_entity)
        for _e in _edges:
            print(f'    {_e.source} → {_e.relation} → {_e.target}')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Discussion & Tradeoffs

    ### Why Tiered Storage?

    | Tier | Backing Store | Latency | Cost/GB/mo | Use Case |
    |------|--------------|---------|------------|----------|
    | **Hot** | Redis / Memcached | <1 ms | ~$25 | Current session context, frequent queries |
    | **Warm** | Postgres + pgvector | 5-50 ms | ~$0.25 | Long-term facts, semantic search |
    | **Cold** | S3 / Glacier / compressed | 100 ms+ | ~$0.004 | Archival, rarely accessed, compliance retention |

    The 100x cost difference between hot and cold storage makes tiering essential at scale. A user with 10,000 memories costs $0.25/month in warm storage but $25/month if everything stays cached in Redis.

    ### PII Handling in Practice

    Regex-based PII detection (as shown) catches common patterns but has significant limitations:
    - **False negatives:** It won't detect names, addresses, or context-dependent PII without NER (named entity recognition).
    - **False positives:** It may redact legitimate data (IP addresses in technical logs).
    - **Embedding leakage:** Even if text is redacted, embeddings may encode PII. Consider training PII-aware embedding models or applying differential privacy.

    **Production recommendation:** Use Microsoft Presidio or a cloud DLP service for detection. Encrypt PII fields at rest. Maintain a separate PII mapping table that can be deleted independently.

    ### Budget Enforcement Strategies

    The importance-weighted eviction shown here is one approach. Alternatives include:

    | Strategy | Pros | Cons |
    |----------|------|------|
    | **LRU (Least Recently Used)** | No scoring needed | May evict important but infrequent memories |
    | **Importance-weighted** (this notebook) | Preserves high-value memories | Requires accurate importance scores |
    | **TTL-only** | Predictable, no decision logic | Time isn't always the right signal |
    | **Token-budget with summarization** | Preserves all info in condensed form | Summarization adds cost and may lose nuance |

    ### Cost Control Lessons

    1. **Batch embeddings.** Generating embeddings one-by-one is 3-5x more expensive than batching. Accumulate memories and embed in bulk.
    2. **Cache embeddings.** If the same text is embedded twice, you've wasted money. Hash content and cache embedding results.
    3. **Use smaller models for extraction.** Haiku-class models work well for structured fact extraction at 10-20x lower cost than Opus.
    4. **Set hard daily limits.** A bug in an extraction loop can burn through your monthly budget in hours. Hard daily caps are essential.
    5. **Monitor cost per user.** Some users generate 100x more memory operations. Per-user cost tracking prevents subsidization problems.

    ### What This Notebook Does Not Cover

    - **Horizontal sharding.** Distributing data across multiple nodes by user ID hash. Critical at >100K users but adds complexity (cross-shard queries, rebalancing).
    - **Distributed caching.** Redis Cluster or Memcached for multi-node cache coherency.
    - **Real-time observability.** OpenTelemetry instrumentation, Prometheus metrics, Grafana dashboards.
    - **Backup & recovery.** WAL archiving, point-in-time recovery, cross-region replication.
    - **A/B testing memory systems.** Running two memory configurations side-by-side and measuring downstream task quality.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Further Reading

    - [Redis documentation: Data persistence & TTL](https://redis.io/docs/?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques) - Production caching patterns, TTL configuration, and eviction policies.
    - [pgvector: Open-source vector similarity for Postgres](https://github.com/pgvector/pgvector) - Embedding storage, indexing (IVFFlat, HNSW), and query optimization.
    - [GDPR Article 17: Right to Erasure](https://gdpr-info.eu/art-17-gdpr/?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques) - Legal requirements for data deletion, including derived data like embeddings.
    - [Microsoft Presidio: PII Detection & Anonymization](https://github.com/microsoft/presidio) - Open-source framework for detecting and redacting PII across text, images, and structured data.
    - [OpenTelemetry: Observability Framework](https://opentelemetry.io/docs/?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques) - Instrumentation, tracing, and metrics for production systems.
    - [Neo4j: Graph Database for Knowledge Graphs](https://neo4j.com/docs/?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques) - Production graph storage for entity relationships, traversal queries, and knowledge representation.
    - [Pinecone: Production Vector Database Best Practices](https://docs.pinecone.io/guides/getting-started/overview?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques) - Scaling, sharding, and cost optimization for managed vector databases.
    - [Anthropic: Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques) - Patterns for production agent architectures including memory management.

    ---

    *← Previous: [29 - Memory Benchmarks (LoCoMo)](../29_memory_benchmarks_LoCoMo/) →*
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 🧪 Try It Yourself

    Three small challenges to deepen your understanding. Each should take 10-30 minutes.

    ### Challenge 1: Custom PII pattern
    Extend `PIIHandler` with a new regex pattern for credit card numbers. Add test cases with sample card numbers embedded in conversation text. Verify that `PIIHandler` detects and redacts them while preserving the rest of the message. Check the audit log for the new pattern.

    ### Challenge 2: Tier migration tracking
    Add 30 memories to `TieredMemorySystem` and run `run_maintenance()` 5 times. After each pass, call `retrieve()` for 10 queries to generate access patterns, then run maintenance again. Track how many memories migrate between HOT, WARM, and COLD tiers. Plot the tier populations over each maintenance cycle.

    ### Challenge 3: Budget-constrained eviction
    Set a tight per-user limit in `MemoryBudgetEnforcer` (e.g., 50 memories). Add 100 memories with varied importance scores. Trigger eviction and verify that the evicted memories have the lowest importance. Measure the average importance of surviving vs. evicted memories. This connects to the decay and pruning strategies from 19 Forgetting and Decay.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--30-production-memory-patterns--production-memory-patterns)
    """)
    return



@app.cell(hide_code=True)
def _():
    import marimo as _studio_mo
    studio_notes = _studio_mo.ui.text_area(label="Research notes", placeholder="Record parameters, observations and follow-up questions")
    _studio_mo.vstack([_studio_mo.md("### Research notebook"), studio_notes])
    return (studio_notes,)

if __name__ == "__main__":
    app.run()
