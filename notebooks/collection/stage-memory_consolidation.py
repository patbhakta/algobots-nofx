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
    # Memory Consolidation

    > Periodically review, merge, deduplicate, and strengthen memories. Inspired by how the brain consolidates during sleep.

    Think about cleaning out a messy filing cabinet at the end of each month. You find three folders about the same project, two with contradicting notes. You merge the best parts into one clean folder and toss the duplicates. Without this cleanup, the cabinet becomes unusable.

    The human brain runs a similar process during sleep. It replays recent experiences and strengthens the important ones. It prunes duplicates and weaves new information into existing knowledge. This turns fragile short-term traces into durable long-term memories.

    Agent memory systems face this problem at an accelerated scale. After hundreds of interactions, the store fills with duplicates. The user might mention their job title in five separate conversations. Contradictions creep in too: the user said they prefer Python in March but switched to Rust in June. Without cleanup, retrieval quality drops.

    **Memory consolidation** is a background maintenance process for the agent's memory store. It reviews stored memories, clusters related entries, merges duplicates, and resolves contradictions. The result is a cleaner store that improves with age.

    This notebook shows you how to build a consolidation pipeline from scratch with the **OpenAI SDK**. You'll implement clustering, deduplication, conflict resolution, and importance scoring.

    **By the end you'll understand:**
    - How to cluster related memories by semantic similarity.
    - How to merge duplicates and resolve contradictions with an LLM.
    - How to score memory importance and prune low-value entries.
    - When consolidation helps and when it can go wrong.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Key Concepts

    - **Embedding**: A list of numbers (a vector) that captures the meaning of a piece of text. Texts with similar meanings produce similar embeddings. We use embeddings to measure how related two memories are.
    - **Cosine similarity**: A score between -1 and 1 that measures how close two embeddings point in the same direction. We treat 0.8+ as "related" and 0.92+ as "near-duplicate."
    - **Consolidation trigger**: A condition that starts a consolidation cycle. Common triggers include store size thresholds, time intervals, or manual commands.
    - **Memory merging**: Combining two or more memories about the same fact into one richer entry. Example: merging "User likes Italian food" and "User's favorite cuisine is Italian, especially pasta."
    - **Deduplication**: Finding and removing near-identical memories. You keep the most complete or most recent version.
    - **Conflict resolution**: A strategy for handling contradictory memories. Options include recency-wins (latest version wins), source-priority (user-stated facts beat inferred ones), or LLM-adjudicated (ask the model to decide).
    - **Importance scoring**: Recalculating how valuable each memory is after consolidation. Factors include access frequency, recency, and source reliability.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Architecture

    <p align="center">
      <img src="../../images/diagrams/14_memory_consolidation.svg" alt="Memory Consolidation Architecture" width="720"/>
    </p>

    <details><summary>Mermaid source</summary>

    ```mermaid
    flowchart LR
        MS["Memory Store\n(pre-consolidation)"] --> CT["Consolidation\nTrigger"]
        CT --> CE["Cluster Engine\n(similarity grouping)"]
        CE --> MD["Merge &\nDeduplicate"]
        MD --> CR["Conflict\nResolver"]
        CR --> IS["Importance\nScorer"]
        IS --> CS["Consolidated\nStore"]

        CT -.->|"Trigger conditions:\n- Size threshold\n- Time interval\n- Manual"| CE

        style MS fill:#5a4a2d,stroke:#a84,color:#fff
        style CS fill:#2d5a2d,stroke:#4a9,color:#fff
        style CR fill:#5a2d4a,stroke:#a49,color:#fff
    ```

    </details>

    **Data flow**: The **Consolidation Trigger** fires when conditions are met (store size, elapsed time, or manual request).

    The **Cluster Engine** groups memories by semantic similarity. This produces clusters of related memories.

    Within each cluster, the **Merge & Deduplicate** module combines overlapping entries and removes near-duplicates. The **Conflict Resolver** handles contradictory memories using the configured strategy (recency, source priority, or LLM adjudication).

    The **Importance Scorer** recalculates scores for all surviving memories. The result is a clean **Consolidated Store** that replaces the original.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Setup

    Install dependencies and configure API access.
    """)
    return


@app.cell
def _():
    # '%pip install -q openai python-dotenv numpy' command supported automatically in marimo
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Import the OpenAI SDK and standard library helpers. The API key loads from a `.env` file.
    """)
    return


@app.cell
def _():
    import os
    import time
    import uuid
    from dataclasses import dataclass, field

    import numpy as np
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv()  # reads OPENAI_API_KEY from .env

    client = OpenAI()
    MODEL = "gpt-4o-mini"
    EMBEDDING_MODEL = "text-embedding-3-small"

    assert os.getenv("OPENAI_API_KEY"), "Set OPENAI_API_KEY in your .env file"
    return EMBEDDING_MODEL, MODEL, client, dataclass, field, np, time, uuid


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Implementation

    We'll build the consolidation pipeline in five parts:

    1. **Memory data model** and store.
    2. **Embedding helpers** for similarity computation.
    3. **Cluster engine** to group related memories.
    4. **Merge, dedup, and conflict resolution** modules.
    5. **Importance scorer** and the main **consolidator** class.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Memory Data Model

    Each memory stores its content alongside metadata. The `source` field tracks where the memory came from: the user said it directly, the agent inferred it, or a tool produced it. We also track creation time, access count, and an importance score.
    """)
    return


@app.cell
def _(dataclass, field, time, uuid):
    @dataclass
    class Memory:
        content: str
        source: str = "user"  # "user", "inferred", or "tool"
        created_at: float = field(default_factory=time.time)
        last_accessed: float = field(default_factory=time.time)
        access_count: int = 1
        importance: float = 0.5
        id: str = field(default_factory=lambda: str(uuid.uuid4()))
        embedding: list[float] | None = None

        def __repr__(self):
            preview = self.content[:60] + ("..." if len(self.content) > 60 else "")
            return f"Memory(id={self.id[:8]}, importance={self.importance:.2f}, content='{preview}')"

    return (Memory,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Memory Store

    A thin wrapper around a dictionary. It maps memory IDs to Memory objects and supports bulk replacement, which the consolidator uses to swap in the cleaned version.
    """)
    return


@app.cell
def _(Memory):
    class MemoryStore:
        def __init__(self):
            self.memories: dict[str, Memory] = {}

        def add(self, memory: Memory) -> None:
            self.memories[memory.id] = memory

        def get_all(self) -> list[Memory]:
            return list(self.memories.values())

        def remove(self, memory_id: str) -> None:
            self.memories.pop(memory_id, None)

        def replace_all(self, memories: list[Memory]) -> None:
            self.memories = {m.id: m for m in memories}

        def __len__(self) -> int:
            return len(self.memories)

        def __repr__(self) -> str:
            return f"MemoryStore({len(self)} memories)"

    return (MemoryStore,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Embedding and Similarity Helpers

    We need a way to measure how similar two memories are in meaning. The OpenAI embeddings API converts text into a vector (a list of numbers). We then compare vectors using cosine similarity. A score near 1.0 means the texts are very similar.
    """)
    return


@app.cell
def _(EMBEDDING_MODEL, Memory, client, np):
    def embed_texts(texts: list[str]) -> list[list[float]]:
        """Get embeddings for a batch of texts."""
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts,
        )
        return [item.embedding for item in response.data]


    def ensure_embeddings(memories: list[Memory]) -> None:
        """Compute embeddings for memories that don't have them yet."""
        needs_embedding = [m for m in memories if m.embedding is None]
        if not needs_embedding:
            return
        texts = [m.content for m in needs_embedding]
        vectors = embed_texts(texts)
        for memory, vector in zip(needs_embedding, vectors):
            memory.embedding = vector


    def cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two embedding vectors."""
        a_arr, b_arr = np.array(a), np.array(b)
        return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)))

    return cosine_similarity, ensure_embeddings


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Cluster Engine

    Think of clustering as sorting papers into piles on a desk. You read each pair and ask: "Are these about the same topic?" If yes, they go in the same pile.

    The cluster engine compares every pair of memories by cosine similarity. If two memories score above the threshold (default 0.80), they belong to the same cluster. We use a union-find data structure (a way to group items by transitive connections) to build clusters efficiently.
    """)
    return


@app.cell
def _(Memory, cosine_similarity, ensure_embeddings):
    class ClusterEngine:
        """Groups related memories by embedding similarity."""

        def __init__(self, similarity_threshold: float = 0.80):
            self.similarity_threshold = similarity_threshold

        def cluster(self, memories: list[Memory]) -> list[list[Memory]]:
            """Group memories into clusters using union-find on cosine similarity."""
            ensure_embeddings(memories)
            n = len(memories)

            # Union-find: parent[i] points to the representative of i's group
            parent = list(range(n))

            def find(x: int) -> int:
                while parent[x] != x:
                    parent[x] = parent[parent[x]]  # path compression
                    x = parent[x]
                return x

            def union(x: int, y: int) -> None:
                px, py = find(x), find(y)
                if px != py:
                    parent[px] = py

            # Compare every pair; merge if similarity exceeds threshold
            for i in range(n):
                for j in range(i + 1, n):
                    sim = cosine_similarity(memories[i].embedding, memories[j].embedding)
                    if sim >= self.similarity_threshold:
                        union(i, j)

            # Collect clusters
            clusters: dict[int, list[Memory]] = {}
            for i in range(n):
                root = find(i)
                clusters.setdefault(root, []).append(memories[i])

            return list(clusters.values())

    return (ClusterEngine,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Merge and Deduplicate

    Within a cluster, some memories might be near-duplicates (similarity above 0.92). We identify these groups, then ask the LLM to combine them into a single, richer entry. This keeps the best details from each duplicate.
    """)
    return


@app.cell
def _(Memory, cosine_similarity):
    def find_duplicates(cluster: list[Memory], threshold: float = 0.92) -> list[list[Memory]]:
        """Find groups of near-duplicate memories within a cluster."""
        n = len(cluster)
        if n <= 1:
            return []

        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        for i in range(n):
            for j in range(i + 1, n):
                sim = cosine_similarity(cluster[i].embedding, cluster[j].embedding)
                if sim >= threshold:
                    union(i, j)

        groups: dict[int, list[Memory]] = {}
        for i in range(n):
            root = find(i)
            groups.setdefault(root, []).append(cluster[i])

        # Return only groups with 2+ entries (actual duplicates)
        return [g for g in groups.values() if len(g) > 1]

    return (find_duplicates,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Once we identify duplicate groups, we ask the LLM to merge them. The model sees all versions with their source and date, then writes a single entry that keeps the most specific details from each.
    """)
    return


@app.cell
def _(MODEL, Memory, client, time):
    def merge_memories_with_llm(duplicates: list[Memory]) -> str:
        """Ask the LLM to merge duplicate memories into one clean entry."""
        numbered = "\n".join(
            f"{i+1}. [{m.source}, {time.strftime('%Y-%m-%d', time.localtime(m.created_at))}] {m.content}"
            for i, m in enumerate(duplicates)
        )

        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You merge duplicate memory entries into one concise entry. "
                        "Combine all unique information. Keep the most specific details. "
                        "Return only the merged text, nothing else."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Merge these duplicate memories:\n{numbered}",
                },
            ],
            max_tokens=256,
            temperature=0.0,
        )

        content = response.choices[0].message.content
        return content.strip() if content else duplicates[0].content

    return (merge_memories_with_llm,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Conflict Detection and Resolution

    Duplicates say the same thing. Contradictions say opposite things. "User prefers Python" and "User switched to Rust" can't both be current.

    We use the LLM to detect contradictions within a cluster. Then the `ConflictResolver` picks a winner using one of three strategies:

    - **Recency**: the most recent memory wins.
    - **Source priority**: user-stated facts beat inferences, which beat tool outputs.
    - **LLM-adjudicated**: ask the model to pick the most likely correct version.
    """)
    return


@app.cell
def _(MODEL, Memory, client):
    def detect_contradictions(cluster: list[Memory]) -> list[list[Memory]]:
        """Use the LLM to find contradictory memories in a cluster."""
        if len(cluster) <= 1:
            return []

        numbered = "\n".join(
            f"{i+1}. {m.content}" for i, m in enumerate(cluster)
        )

        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You detect contradictions between memory entries. "
                        "List pairs of entry numbers that contradict each other. "
                        "Format: one pair per line as 'X,Y' (numbers only). "
                        "If no contradictions exist, reply with 'NONE'."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Find contradictions:\n{numbered}",
                },
            ],
            max_tokens=128,
            temperature=0.0,
        )

        text = response.choices[0].message.content or ""
        text = text.strip()
        if text == "NONE" or not text:
            return []

        conflict_groups = []
        for line in text.split("\n"):
            line = line.strip()
            if "," not in line:
                continue
            try:
                parts = [int(x.strip()) - 1 for x in line.split(",")]
                group = [cluster[i] for i in parts if 0 <= i < len(cluster)]
                if len(group) >= 2:
                    conflict_groups.append(group)
            except (ValueError, IndexError):
                continue

        return conflict_groups

    return (detect_contradictions,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `ConflictResolver` picks a winner from contradictory memories. It supports three strategies.
    "Recency" keeps the newest memory. "Source priority" ranks user-stated facts above inferences. "LLM" asks the model to pick the most plausible version.
    """)
    return


@app.cell
def _(MODEL, Memory, client, time):
    class ConflictResolver:
        """Picks the authoritative memory from a set of contradictions."""

        def __init__(self, strategy: str = "recency"):
            self.strategy = strategy

        def resolve(self, memories: list[Memory]) -> Memory:
            if self.strategy == "recency":
                return self._recency_wins(memories)
            elif self.strategy == "source_priority":
                return self._source_priority(memories)
            elif self.strategy == "llm":
                return self._llm_adjudicate(memories)
            raise ValueError(f"Unknown strategy: {self.strategy}")

        def _recency_wins(self, memories: list[Memory]) -> Memory:
            return max(memories, key=lambda m: m.created_at)

        def _source_priority(self, memories: list[Memory]) -> Memory:
            priority = {"user": 3, "inferred": 2, "tool": 1}
            return max(memories, key=lambda m: (priority.get(m.source, 0), m.created_at))

        def _llm_adjudicate(self, memories: list[Memory]) -> Memory:
            numbered = "\n".join(
                f"{i+1}. [{m.source}, {time.strftime('%Y-%m-%d', time.localtime(m.created_at))}] {m.content}"
                for i, m in enumerate(memories)
            )

            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You resolve contradictory memory entries. "
                            "Pick the entry that is most likely correct and current. "
                            "Consider recency and source reliability. "
                            "Reply with ONLY the entry number."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Which memory is most likely correct?\n{numbered}",
                    },
                ],
                max_tokens=8,
                temperature=0.0,
            )

            try:
                text = response.choices[0].message.content or ""
                chosen_idx = int(text.strip()) - 1
                return memories[max(0, min(chosen_idx, len(memories) - 1))]
            except (ValueError, IndexError):
                return self._recency_wins(memories)

    return (ConflictResolver,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Importance Scoring

    After merging and conflict resolution, we recalculate each memory's importance. The formula weights three factors:

    - **Recency** (40%): newer memories score higher. We use exponential decay.
    - **Access frequency** (30%): memories accessed more often are more valuable.
    - **Source reliability** (30%): user-stated facts score highest.
    """)
    return


@app.cell
def _(Memory, np, time):
    def rescore_importance(memories: list[Memory], decay_rate: float = 0.01) -> None:
        """Recalculate importance scores for all memories."""
        now = time.time()
        source_weights = {"user": 1.0, "inferred": 0.6, "tool": 0.4}
        max_access = max((m.access_count for m in memories), default=1)

        for memory in memories:
            # Exponential time decay (higher = more recent)
            age_hours = (now - memory.created_at) / 3600
            recency = float(np.exp(-decay_rate * age_hours))

            # Normalized access frequency
            frequency = memory.access_count / max_access

            # Source reliability
            source_w = source_weights.get(memory.source, 0.5)

            memory.importance = round(
                0.4 * recency + 0.3 * frequency + 0.3 * source_w, 3
            )

    return (rescore_importance,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### The Consolidator

    This class orchestrates the full pipeline. It checks the trigger condition, clusters memories, merges duplicates, resolves contradictions, rescores importance, and prunes low-value entries.
    """)
    return


@app.cell
def _(ClusterEngine, ConflictResolver, MemoryStore, dataclass):
    @dataclass
    class ConsolidationReport:
        memories_before: int = 0
        memories_after: int = 0
        duplicates_merged: int = 0
        conflicts_resolved: int = 0
        clusters_found: int = 0


    class MemoryConsolidator:
        """Runs the full memory consolidation pipeline."""

        def __init__(
            self,
            store: MemoryStore,
            similarity_threshold: float = 0.80,
            duplicate_threshold: float = 0.92,
            conflict_strategy: str = "recency",
            size_trigger: int = 10,
            prune_below: float = 0.15,
        ):
            self.store = store
            self.clusterer = ClusterEngine(similarity_threshold)
            self.resolver = ConflictResolver(conflict_strategy)
            self.duplicate_threshold = duplicate_threshold
            self.size_trigger = size_trigger
            self.prune_below = prune_below
            self.last_run: float = 0.0

        def should_consolidate(self) -> bool:
            """Check whether the store has reached the size trigger."""
            return len(self.store) >= self.size_trigger

    return ConsolidationReport, MemoryConsolidator


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `consolidate` method runs the full pipeline in sequence: embed all memories, cluster them, merge duplicates within each cluster, resolve contradictions, rescore importance, and prune low-value entries. It returns a report summarizing what changed.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The consolidation loop processes each cluster individually. This helper function handles one cluster.
    It merges near-duplicates (memories that are almost identical) and resolves contradictions (memories that disagree).
    Extracting this logic into its own function keeps each piece short and testable.
    """)
    return


@app.cell
def _(Memory, detect_contradictions, find_duplicates, merge_memories_with_llm):
    def _process_single_cluster(cluster, duplicate_threshold, resolver):
        """Process one cluster: merge duplicates and resolve contradictions.

        Returns (surviving_memories, duplicates_merged, conflicts_resolved).
        """
        working = list(cluster)
        dup_count = 0
        conflict_count = 0

        # Merge near-duplicates
        dup_groups = find_duplicates(working, duplicate_threshold)
        for dup_group in dup_groups:
            merged_text = merge_memories_with_llm(dup_group)
            newest = max(dup_group, key=lambda m: m.created_at)
            merged = Memory(
                content=merged_text,
                source=newest.source,
                created_at=newest.created_at,
                last_accessed=max(m.last_accessed for m in dup_group),
                access_count=sum(m.access_count for m in dup_group),
                importance=max(m.importance for m in dup_group),
            )
            dup_ids = {m.id for m in dup_group}
            working = [m for m in working if m.id not in dup_ids]
            working.append(merged)
            dup_count += len(dup_group)

        # Detect and resolve contradictions
        conflicts = detect_contradictions(working)
        for conflict_group in conflicts:
            winner = resolver.resolve(conflict_group)
            loser_ids = {m.id for m in conflict_group if m.id != winner.id}
            working = [m for m in working if m.id not in loser_ids]
            conflict_count += len(loser_ids)

        return working, dup_count, conflict_count

    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Now we define the main `consolidate` method. It embeds all memories, clusters them,
    then calls `_process_single_cluster` for each group. After processing, it rescores importance
    and prunes low-value entries.
    """)
    return


@app.cell
def _(
    ConsolidationReport,
    MemoryConsolidator,
    ensure_embeddings,
    rescore_importance,
    time,
):
    def consolidate(self) -> ConsolidationReport:
        """Run a full consolidation cycle."""
        report = ConsolidationReport()
        memories = self.store.get_all()
        report.memories_before = len(memories)

        if len(memories) <= 1:
            report.memories_after = len(memories)
            return report

        # Step 1: Embed all memories
        ensure_embeddings(memories)

        # Step 2: Cluster by similarity
        clusters = self.clusterer.cluster(memories)
        report.clusters_found = len(clusters)

        consolidated = []

        for cluster in clusters:
            if len(cluster) == 1:
                consolidated.append(cluster[0])
                continue

            working, dup_count, conflict_count = _process_single_cluster(
                cluster, self.duplicate_threshold, self.resolver,
            )
            report.duplicates_merged += dup_count
            report.conflicts_resolved += conflict_count
            consolidated.extend(working)

        # Step 5: Rescore importance
        rescore_importance(consolidated)

        # Step 6: Prune low-importance memories
        consolidated = [m for m in consolidated if m.importance >= self.prune_below]

        # Recompute embeddings for any new (merged) memories
        ensure_embeddings(consolidated)

        self.store.replace_all(consolidated)
        self.last_run = time.time()
        report.memories_after = len(consolidated)

        return report


    MemoryConsolidator.consolidate = consolidate
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Example Run

    Let's see consolidation in action. We'll seed a memory store with messy data: duplicates, contradictions, and noise. Then we'll run the consolidator and compare before and after.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    First, we create 12 memories that an agent might accumulate over several days. Some are near-duplicates (three entries about the user's job). Some contradict each other (Python vs. Rust preference). One is low-importance noise.
    """)
    return


@app.cell
def _(Memory, MemoryStore, time):
    store = MemoryStore()

    day = 86400  # seconds in one day
    now = time.time()

    messy_memories = [
        # Three near-duplicates about the user's job
        Memory(
            content="User works as a software engineer at Acme Corp",
            source="user", created_at=now - 7 * day, access_count=3,
        ),
        Memory(
            content="The user is a software engineer working at Acme Corp",
            source="inferred", created_at=now - 5 * day, access_count=1,
        ),
        Memory(
            content="User's occupation: software engineer, employer: Acme Corp",
            source="tool", created_at=now - 3 * day, access_count=2,
        ),
        # Contradictory language preferences
        Memory(
            content="User prefers Python for most programming tasks",
            source="user", created_at=now - 10 * day, access_count=5,
        ),
        Memory(
            content="User recently switched to Rust as their primary language",
            source="user", created_at=now - 1 * day, access_count=2,
        ),
    ]
    return day, messy_memories, now, store


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    We add more memories to the test set: project duplicates, unique facts, a location duplicate,
    and one low-importance noise entry. These give the consolidator a realistic mix to clean up.
    """)
    return


@app.cell
def _(Memory, day, messy_memories, now):
    more_memories = [
        # Two near-duplicates about a project
        Memory(
            content="User is building a chatbot with memory for their startup",
            source="user", created_at=now - 6 * day, access_count=4,
        ),
        Memory(
            content="User's current project: an AI chatbot that remembers conversations",
            source="inferred", created_at=now - 4 * day, access_count=1,
        ),
        # Unique memories (should survive untouched)
        Memory(
            content="User has a golden retriever named Max",
            source="user", created_at=now - 8 * day, access_count=2,
        ),
        Memory(
            content="User lives in San Francisco",
            source="user", created_at=now - 9 * day, access_count=3,
        ),
        Memory(
            content="User prefers morning meetings before 10 AM",
            source="inferred", created_at=now - 2 * day, access_count=1,
        ),
        # Near-duplicate of the location memory
        Memory(
            content="User is based in San Francisco, California",
            source="user", created_at=now - 3 * day, access_count=2,
        ),
        # Low-importance noise
        Memory(
            content="User mentioned the weather was nice today",
            source="inferred", created_at=now - 14 * day, access_count=1,
            importance=0.1,
        ),
    ]

    messy_memories.extend(more_memories)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Now we load all 12 memories into the store and print them out. Notice the duplicates, contradictions, and noise.
    """)
    return


@app.cell
def _(messy_memories, store):
    for _m in messy_memories:
        store.add(_m)
    print(f'Memory store before consolidation: {len(store)} entries\n')
    for _m in store.get_all():
        print(f'  [{_m.source:8s}] {_m.content}')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Now we run consolidation. The consolidator will cluster these memories, merge the duplicates, resolve the Python-vs-Rust contradiction, rescore importance, and prune the weather noise.
    """)
    return


@app.cell
def _(MemoryConsolidator, store):
    consolidator = MemoryConsolidator(
        store=store,
        similarity_threshold=0.80,
        duplicate_threshold=0.90,
        conflict_strategy="recency",
        size_trigger=5,
        prune_below=0.15,
    )

    print(f"Should consolidate? {consolidator.should_consolidate()}")
    print("Running consolidation...\n")

    report = consolidator.consolidate()

    print(f"Memories before:      {report.memories_before}")
    print(f"Memories after:       {report.memories_after}")
    print(f"Clusters found:       {report.clusters_found}")
    print(f"Duplicates merged:    {report.duplicates_merged}")
    print(f"Conflicts resolved:   {report.conflicts_resolved}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Inspect the consolidated store. You should see fewer entries, no duplicates, and the Python preference replaced by Rust.
    """)
    return


@app.cell
def _(store):
    print(f'Consolidated store: {len(store)} entries\n')
    for _m in sorted(store.get_all(), key=lambda m: m.importance, reverse=True):
        print(f'  [importance={_m.importance:.3f}] [{_m.source:8s}] {_m.content}')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Tradeoffs

    ### When Consolidation Works Well

    - **Long-running agents** that accumulate hundreds of memories across sessions. Periodic cleanup keeps the store lean and accurate.
    - **Factual accuracy matters**: contradictory memories cause wrong answers. Consolidation resolves conflicts before they reach the user.
    - **Storage and retrieval costs**: fewer memories means faster similarity search and lower embedding storage costs.
    - **Retrieval quality**: merged, deduplicated memories are more complete. The agent retrieves one rich entry instead of three partial ones.

    ### When It Breaks Down

    - **Lossy by design**: merging and pruning can discard information that matters later. You can't recover a pruned memory.
    - **LLM calls add cost**: merge and conflict resolution require API calls. A store with 10,000 memories could need hundreds of LLM calls per cycle.
    - **Clustering errors**: if the similarity threshold is too low, unrelated memories get merged. Too high, and duplicates slip through. Tuning depends on your domain.
    - **Temporal nuance gets lost**: "User prefers Python" and "User switched to Rust" aren't always contradictions. The user might use Python for scripting and Rust for systems work. Consolidation can oversimplify.
    - **Latency during consolidation**: the process can slow the agent while running. Production systems run it asynchronously or during idle periods.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Further Reading

    - Stickgold & Walker, ["Sleep-Dependent Memory Triage: Evolving Generalization through Selective Processing,"](https://doi.org/10.1038/nn.3303) *Nature Neuroscience*, 2013. Explores how the brain selectively consolidates important memories during sleep.
    - Packer et al., ["MemGPT: Towards LLMs as Operating Systems,"](https://arxiv.org/abs/2310.08560) 2023. Implements memory management including consolidation-like operations within an OS-inspired LLM architecture.
    - Rasch & Born, ["About Sleep's Role in Memory,"](https://doi.org/10.1152/physrev.00032.2012) *Physiological Reviews*, 2013. A thorough review of sleep-based memory consolidation in neuroscience.
    - Zhong et al., ["MemoryBank: Enhancing Large Language Models with Long-Term Memory,"](https://arxiv.org/abs/2305.10250) 2024. Implements forgetting curves and memory updating that parallel consolidation processes.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---

    *← Previous: [13 - Hierarchical Memory Layers](../13_hierarchical_memory_layers/) · Next: [15 - Memory Compaction](../15_memory_compaction/) →*
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 🧪 Try It Yourself

    Three small challenges to deepen your understanding. Each should take 10-30 minutes.

    ### Challenge 1: Clustering threshold sweep
    Vary the similarity threshold in `ClusterEngine` from 0.70 to 0.95 in steps of 0.05. For each threshold, run consolidation on the same memory set and record the number of clusters, merged memories, and orphans. Plot threshold vs. cluster count.

    ### Challenge 2: Before-and-after metrics
    Before and after running `MemoryConsolidator`, measure: total memory count, total token count (sum of all memory content lengths), number of detected contradictions, and number of near-duplicates. Present a clear before/after comparison table.

    ### Challenge 3: Periodic consolidation during conversation
    Wrap `MemoryConsolidator` in a loop that triggers consolidation every 10 conversation turns. Track how memory count, contradiction rate, and retrieval accuracy change across a 50-turn conversation. Compare against the decay-based approach from 19 Forgetting and Decay.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--14-memory-consolidation--memory-consolidation)
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
