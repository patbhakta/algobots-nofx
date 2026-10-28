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
    # Temporal Memory

    > **Give your agent a sense of time: store when things happened and prefer fresh information when it matters.**

    Think of a notebook where every entry has a date written in the margin. When someone asks "what is the project status?", you don't read the entire notebook front to back. You flip to the most recent page. Old entries might still matter, but you weight the newest ones more heavily.

    Standard vector-based retrieval (searching by meaning similarity) treats every memory as equally current. Ask an agent "what is the project status?" and it may return a three-month-old update alongside yesterday's update. It has no signal that the older one is stale. In real-world tasks, *when* something was recorded is often as important as *what* was recorded.

    Temporal memory closes this gap. It attaches structured timestamps to every memory and adds time-awareness to the retrieval pipeline. The core idea draws from cognitive science. Endel Tulving's research on episodic memory (our memory for personal experiences) showed that human recollection is inherently time-stamped. We don't only remember facts. We remember *experiencing* them at particular moments.

    The Generative Agents paper (Park et al., 2023) put this insight into practice. It weighted memory retrieval with a recency score. This gave simulated agents a natural preference for recent events while still allowing important older memories to surface.

    In this notebook you will build a temporal memory system from scratch. You will implement decay functions, time-range filters, recency-weighted retrieval, and timeline construction. By the end, your agent will know not only *what* happened, but *when*.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Key Concepts

    - **Timestamp metadata**: Every memory carries structured time fields. `created_at` records when the memory was stored. `event_time` records when the described event occurred. `last_accessed` tracks the most recent retrieval. These fields enable filtering, sorting, and decay calculations.

    - **Temporal decay function**: A math function that reduces a memory's effective score as it ages. Common choices include exponential decay (`score *= e^(-lambda * age)`) and linear decay. The decay rate controls how fast old memories lose influence.

    - **Half-life**: The time it takes for a memory's recency score to drop to 50%. A half-life of 7 days means a one-week-old memory scores half as much on the recency component as a brand-new one. This is a tunable parameter you set based on your domain.

    - **Recency scoring**: A retrieval-time computation that blends semantic relevance (how well the meaning matches) with temporal freshness (how recent the memory is). When two memories match a query equally well, the more recent one ranks higher.

    - **Time-range query**: Constraining retrieval to a specific time window. For example: "conversations from the past 24 hours" or "events between March 1 and March 15."

    - **"As of" retrieval**: Reconstructing what the agent knew at a specific past timestamp. You exclude all memories created after that point. This is useful for auditing and debugging.

    - **Event timeline**: An ordered sequence of related memories that tells a chronological story. This helps the agent summarize how a situation developed over time.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Architecture

    <p align="center">
      <img src="../../images/diagrams/18_temporal_memory.svg" alt="Temporal Memory Architecture" width="720"/>
    </p>

    <details><summary>Mermaid source</summary>

    ```mermaid
    flowchart LR
        subgraph Storage
            MS[(Memory Store<br/>with timestamps)]
        end

        Q["Query + optional<br/>time constraints"] --> TRF[Time Range<br/>Filter]
        MS --> TRF
        TRF --> SS[Semantic<br/>Scorer]
        TRF --> TS[Temporal Scorer<br/>decay function]
        SS --> CR[Combined<br/>Ranking]
        TS --> CR
        CR --> TopK[Top-K<br/>Results]

        MS --> TL[Timeline<br/>Constructor]
        TL --> ET[Event<br/>Timeline]

        style MS fill:#4a9eff,color:#fff
        style TS fill:#ff6b6b,color:#fff
        style CR fill:#51cf66,color:#fff
    ```

    </details>

    **Data flow:** A query arrives with optional time constraints. The Time Range Filter narrows the candidate set from the Memory Store. Two scorers work in parallel: the Semantic Scorer computes meaning-similarity and the Temporal Scorer computes recency via a decay function. Combined Ranking merges both scores (as a weighted sum) and returns the top-K results. A separate path feeds the Timeline Constructor, which orders related memories chronologically for narrative-style retrieval.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Setup

    Install dependencies and configure API access. We use the OpenAI SDK for embeddings and chat completions.
    """)
    return


@app.cell
def _():
    # '%pip install -q openai python-dotenv numpy' command supported automatically in marimo
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Import all libraries we need. The API key loads from a `.env` file or environment variable.
    """)
    return


@app.cell
def _():
    import os
    import math
    import json
    import hashlib
    import numpy as np
    from datetime import datetime, timedelta
    from dataclasses import dataclass, field
    from typing import Optional
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv()

    client = OpenAI()  # reads OPENAI_API_KEY from environment
    assert os.getenv("OPENAI_API_KEY"), "Set OPENAI_API_KEY in your .env file"

    EMBED_MODEL = "text-embedding-3-small"
    CHAT_MODEL = "gpt-4o-mini"
    EMBED_DIM = 1536  # dimensions for text-embedding-3-small
    return (
        CHAT_MODEL,
        EMBED_DIM,
        EMBED_MODEL,
        Optional,
        client,
        dataclass,
        datetime,
        field,
        hashlib,
        math,
        np,
        timedelta,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Implementation

    We will build four components:
    1. A `TemporalMemory` dataclass that stores content alongside timestamp metadata.
    2. A `TemporalDecay` class with configurable decay functions (exponential and linear).
    3. A `TemporalMemoryStore` that handles storage, retrieval with combined scoring, time-range queries, and "as of" filtering.
    4. A timeline builder that orders related memories chronologically.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Embedding Helper

    We need a function to convert text into an embedding (a list of numbers that captures meaning). Two texts with similar meaning produce similar embeddings. We use cosine similarity (measuring the angle between two vectors) to compare them.
    """)
    return


@app.cell
def _(EMBED_MODEL, client, np):
    def get_embedding(text: str) -> list[float]:
        """Get an embedding vector for the given text."""
        response = client.embeddings.create(model=EMBED_MODEL, input=text)
        return response.data[0].embedding


    def cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors.

        Returns a value between -1 and 1. Higher means more similar.
        """
        a_arr = np.array(a)
        b_arr = np.array(b)
        dot = np.dot(a_arr, b_arr)
        norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
        if norm == 0:
            return 0.0
        return float(dot / norm)

    return cosine_similarity, get_embedding


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### The TemporalMemory Data Model

    Each memory entry carries three timestamps. `created_at` is when we stored it. `event_time` is when the described event actually occurred (it may differ from storage time). `last_accessed` tracks the most recent retrieval. We also store a unique ID based on content and creation time.
    """)
    return


@app.cell
def _(Optional, dataclass, datetime, field, hashlib):
    @dataclass
    class TemporalMemory:
        """A single memory entry with temporal metadata."""
        content: str
        embedding: list[float]
        created_at: datetime
        event_time: Optional[datetime] = None
        last_accessed: Optional[datetime] = None
        metadata: dict = field(default_factory=dict)
        memory_id: str = ""

        def __post_init__(self):
            if not self.event_time:
                self.event_time = self.created_at
            if not self.last_accessed:
                self.last_accessed = self.created_at
            if not self.memory_id:
                # Deterministic ID from content + timestamp
                raw = f"{self.content}:{self.created_at.isoformat()}"
                self.memory_id = hashlib.sha256(raw.encode()).hexdigest()[:12]

        def age_hours(self, now: datetime) -> float:
            """Hours elapsed since this memory was created."""
            return (now - self.created_at).total_seconds() / 3600

        def __repr__(self) -> str:
            preview = self.content[:60] + ("..." if len(self.content) > 60 else "")
            return f"TemporalMemory(id={self.memory_id}, content='{preview}')"

    return (TemporalMemory,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Temporal Decay Functions

    Think of decay like the freshness of bread. A loaf baked this morning is at peak freshness. Yesterday's loaf is still fine. Last week's loaf is stale. How fast that freshness drops depends on the decay function you choose.

    **Exponential decay** drops the score quickly at first, then more slowly. You parameterize it by a half-life: the time for the score to reach 0.5. This matches the Ebbinghaus forgetting curve from psychology.

    **Linear decay** drops the score at a constant rate until it hits zero. It is simpler and easier to reason about.
    """)
    return


@app.cell
def _(TemporalMemory, datetime, math):
    class TemporalDecay:
        """Compute recency scores using configurable decay functions."""

        def __init__(self, decay_type: str = "exponential", half_life_hours: float = 168.0):
            """
            Args:
                decay_type: "exponential" or "linear"
                half_life_hours: Time in hours for score to drop to 0.5.
                                 Default 168 = 7 days.
            """
            self.decay_type = decay_type
            self.half_life_hours = half_life_hours
            # For exponential: lambda = ln(2) / half_life
            self.lambda_ = math.log(2) / half_life_hours

        def score(self, memory: TemporalMemory, now: datetime) -> float:
            """Return a recency score between 0.0 and 1.0.

            1.0 means brand-new. 0.0 means fully decayed.
            """
            age_h = memory.age_hours(now)
            if age_h <= 0:
                return 1.0

            if self.decay_type == "exponential":
                return math.exp(-self.lambda_ * age_h)
            elif self.decay_type == "linear":
                # Reaches zero at 2x the half-life
                max_age = 2.0 * self.half_life_hours
                return max(0.0, 1.0 - (age_h / max_age))
            else:
                return 1.0  # no decay

        def __repr__(self) -> str:
            return f"TemporalDecay(type={self.decay_type}, half_life={self.half_life_hours}h)"

    return (TemporalDecay,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### The Temporal Memory Store

    This is the core class. It stores memories and retrieves them with combined semantic and temporal scoring. Key methods:

    - `add()`: Store a new memory with its embedding and timestamps.
    - `query()`: Retrieve the most relevant memories, blending meaning-similarity with recency.
    - `query_time_range()`: Retrieve memories within a specific time window.
    - `query_as_of()`: Reconstruct what the agent knew at a past moment.
    - `build_timeline()`: Order related memories chronologically.
    """)
    return


@app.cell
def _(Optional, TemporalDecay, TemporalMemory):
    class TemporalMemoryStore:
        """Memory store with time-aware retrieval."""

        def __init__(
            self,
            decay: Optional[TemporalDecay] = None,
            recency_weight: float = 0.3,
        ):
            """
            Args:
                decay: Decay function for recency scoring. Defaults to
                       exponential decay with a 7-day half-life.
                recency_weight: How much to weight recency vs. semantic
                                similarity. 0.0 = pure semantic, 1.0 = pure recency.
            """
            self.memories: list[TemporalMemory] = []
            self.decay = decay or TemporalDecay()
            self.recency_weight = recency_weight

    return (TemporalMemoryStore,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Next we add the `add` method for storing new memories, plus three internal scoring helpers.
    `_semantic_scores` computes meaning-similarity. `_recency_scores` computes temporal decay.
    `_combined_scores` blends the two into a single ranking score.
    """)
    return


@app.cell
def _(
    Optional,
    TemporalMemory,
    TemporalMemoryStore,
    cosine_similarity,
    datetime,
    get_embedding,
):
    def add(
        self,
        content: str,
        created_at: Optional[datetime] = None,
        event_time: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ) -> TemporalMemory:
        """Store a new memory with its embedding and timestamps."""
        now = created_at or datetime.utcnow()
        embedding = get_embedding(content)
        mem = TemporalMemory(
            content=content,
            embedding=embedding,
            created_at=now,
            event_time=event_time or now,
            metadata=metadata or {},
        )
        self.memories.append(mem)
        return mem
    TemporalMemoryStore.add = add

    def _semantic_scores(
        self, query_embedding: list[float], candidates: list[TemporalMemory]
    ) -> list[float]:
        """Compute cosine similarity between query and each candidate."""
        return [cosine_similarity(query_embedding, m.embedding) for m in candidates]
    TemporalMemoryStore._semantic_scores = _semantic_scores

    def _recency_scores(
        self, candidates: list[TemporalMemory], now: datetime
    ) -> list[float]:
        """Compute temporal decay score for each candidate."""
        return [self.decay.score(m, now) for m in candidates]
    TemporalMemoryStore._recency_scores = _recency_scores

    def _combined_scores(
        self,
        semantic: list[float],
        recency: list[float],
        weight: Optional[float] = None,
    ) -> list[float]:
        """Blend semantic and recency scores.

        final = (1 - w) * semantic + w * recency
        """
        w = weight if weight is not None else self.recency_weight
        return [(1 - w) * s + w * r for s, r in zip(semantic, recency)]
    TemporalMemoryStore._combined_scores = _combined_scores
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `query` method is the main retrieval interface.
    It computes both semantic similarity and temporal recency for every memory.
    Then it blends them into a combined score: `(1 - w) * semantic + w * recency`.
    Memories that match the query meaning AND are recent rank highest.
    """)
    return


@app.cell
def _(Optional, TemporalMemoryStore, datetime, get_embedding):
    def query(
        self,
        query_text: str,
        top_k: int = 5,
        now: Optional[datetime] = None,
        recency_weight: Optional[float] = None,
    ) -> list[dict]:
        """Retrieve memories ranked by combined semantic + temporal score.

        Returns a list of dicts with the memory, its scores, and rank.
        """
        if not self.memories:
            return []

        now = now or datetime.utcnow()
        query_emb = get_embedding(query_text)

        semantic = self._semantic_scores(query_emb, self.memories)
        recency = self._recency_scores(self.memories, now)
        combined = self._combined_scores(semantic, recency, recency_weight)

        # Sort by combined score descending
        ranked = sorted(
            zip(self.memories, semantic, recency, combined),
            key=lambda x: x[3],
            reverse=True,
        )

        results = []
        for mem, sem_s, rec_s, comb_s in ranked[:top_k]:
            mem.last_accessed = now
            results.append({
                "memory": mem,
                "semantic_score": round(sem_s, 4),
                "recency_score": round(rec_s, 4),
                "combined_score": round(comb_s, 4),
            })
        return results
    TemporalMemoryStore.query = query
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Two specialized query methods handle time-constrained retrieval.
    `query_time_range` filters memories to a specific window (like "this week").
    `query_as_of` reconstructs what the agent knew at a past timestamp by excluding newer memories.
    """)
    return


@app.cell
def _(TemporalMemoryStore, datetime, get_embedding):
    def query_time_range(
        self,
        query_text: str,
        time_start: datetime,
        time_end: datetime,
        top_k: int = 5,
    ) -> list[dict]:
        """Retrieve memories within a specific time window.

        Filters by event_time, then ranks by semantic similarity.
        """
        query_emb = get_embedding(query_text)

        candidates = [
            m for m in self.memories
            if time_start <= m.event_time <= time_end
        ]
        if not candidates:
            return []

        scores = self._semantic_scores(query_emb, candidates)
        ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)

        return [
            {"memory": m, "semantic_score": round(s, 4)}
            for m, s in ranked[:top_k]
        ]
    TemporalMemoryStore.query_time_range = query_time_range
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    `query_as_of` reconstructs the agent's knowledge at a specific past moment.
    It excludes memories created after the given timestamp.
    This is useful for auditing: "What did the agent know two weeks ago?"
    """)
    return


@app.cell
def _(TemporalMemoryStore, datetime, get_embedding):
    def query_as_of(
        self,
        query_text: str,
        as_of: datetime,
        top_k: int = 5,
    ) -> list[dict]:
        """Retrieve memories as if the current time were `as_of`.

        Excludes any memory created after the as_of timestamp.
        Uses as_of as the reference time for recency scoring.
        """
        query_emb = get_embedding(query_text)

        candidates = [m for m in self.memories if m.created_at <= as_of]
        if not candidates:
            return []

        semantic = self._semantic_scores(query_emb, candidates)
        recency = self._recency_scores(candidates, as_of)
        combined = self._combined_scores(semantic, recency)

        ranked = sorted(
            zip(candidates, semantic, recency, combined),
            key=lambda x: x[3],
            reverse=True,
        )

        return [
            {
                "memory": m,
                "semantic_score": round(s, 4),
                "recency_score": round(r, 4),
                "combined_score": round(c, 4),
            }
            for m, s, r, c in ranked[:top_k]
        ]
    TemporalMemoryStore.query_as_of = query_as_of
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    `build_timeline` finds memories related to a topic and sorts them chronologically.
    This is useful for constructing narratives: "How did project X evolve over the past month?"
    """)
    return


@app.cell
def _(Optional, TemporalMemory, TemporalMemoryStore, datetime, get_embedding):
    def build_timeline(
        self,
        topic: str,
        time_start: Optional[datetime] = None,
        time_end: Optional[datetime] = None,
        similarity_threshold: float = 0.3,
    ) -> list[TemporalMemory]:
        """Build a chronological timeline of memories related to a topic.

        Retrieves memories whose semantic similarity to the topic exceeds
        the threshold, then sorts them by event_time.
        """
        topic_emb = get_embedding(topic)
        scores = self._semantic_scores(topic_emb, self.memories)

        related = []
        for mem, score in zip(self.memories, scores):
            if score < similarity_threshold:
                continue
            if time_start and mem.event_time < time_start:
                continue
            if time_end and mem.event_time > time_end:
                continue
            related.append(mem)

        return sorted(related, key=lambda m: m.event_time)
    TemporalMemoryStore.build_timeline = build_timeline

    def __len__(self) -> int:
        return len(self.memories)
    TemporalMemoryStore.__len__ = __len__

    def __repr__(self) -> str:
        return f"TemporalMemoryStore({len(self.memories)} memories)"
    TemporalMemoryStore.__repr__ = __repr__
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### LLM-Powered Timeline Summarization

    Once we have an ordered timeline, we can ask the LLM to produce a narrative summary. This turns a list of raw memory entries into a coherent story of how events unfolded.
    """)
    return


@app.cell
def _(CHAT_MODEL, TemporalMemory, client):
    def summarize_timeline(memories: list[TemporalMemory], topic: str) -> str:
        """Use the LLM to produce a narrative summary of a memory timeline."""
        if not memories:
            return "No memories found for this topic."

        entries = []
        for m in memories:
            timestamp = m.event_time.strftime("%Y-%m-%d %H:%M")
            entries.append(f"[{timestamp}] {m.content}")

        timeline_text = "\n".join(entries)

        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant. Summarize the following "
                        "timeline of events into a brief narrative. Focus on how "
                        "the situation evolved over time. Use 3-5 sentences."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Topic: {topic}\n\nTimeline:\n{timeline_text}",
                },
            ],
            max_tokens=300,
        )
        return response.choices[0].message.content

    return (summarize_timeline,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Example Run

    Imagine an agent tracking a software project over several weeks. Team members post updates at different times. The agent needs to answer questions about the project while preferring recent information.

    We create memories with timestamps spread across the past month. Then we test all four retrieval modes: standard query, time-range, "as of", and timeline.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Populate the Memory Store

    We create a memory store with exponential decay (7-day half-life) and add project updates spanning the past 30 days.
    """)
    return


@app.cell
def _(TemporalDecay, TemporalMemoryStore, datetime):
    # Set a fixed "now" so the example is reproducible
    NOW = datetime(2025, 4, 15, 10, 0, 0)

    store = TemporalMemoryStore(
        decay=TemporalDecay(decay_type="exponential", half_life_hours=168),  # 7-day half-life
        recency_weight=0.3,
    )
    return NOW, store


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    We define ten project updates spanning the past 30 days.
    Each entry records what happened and how many days ago it occurred.
    The loop converts `days_ago` into actual timestamps and stores each update.
    """)
    return


@app.cell
def _():
    # Project updates over the past month
    updates = [
        {
            "content": "Project Alpha kicked off. The team decided to build a REST API "
                       "for the new inventory system. Tech stack: Python, FastAPI, PostgreSQL.",
            "days_ago": 30,
        },
        {
            "content": "Database schema design is complete. We have 12 tables covering "
                       "products, orders, customers, and inventory levels.",
            "days_ago": 25,
        },
        {
            "content": "The authentication module is done. We are using JWT tokens with "
                       "24-hour expiry and refresh token rotation.",
            "days_ago": 20,
        },
        {
            "content": "Performance testing revealed the product search endpoint is slow. "
                       "P95 latency is 800ms. The team is investigating indexing strategies.",
            "days_ago": 14,
        },
        {
            "content": "Added a composite index on (category, price, created_at) to the "
                       "products table. Product search P95 latency dropped from 800ms to 120ms.",
            "days_ago": 10,
        },
    ]
    return (updates,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Here are the remaining project updates: sprint review, notifications launch,
    a bug report, the bug fix, and the final status meeting.
    We combine both batches and store them all.
    """)
    return


@app.cell
def _(NOW, store, timedelta, updates):
    more_updates = [
        {
            "content": "Sprint review: 85% of planned features are complete. Remaining work "
                       "includes order tracking notifications and admin dashboard.",
            "days_ago": 7,
        },
        {
            "content": "The order tracking notification system is now live. Customers receive "
                       "email and SMS updates when their order status changes.",
            "days_ago": 4,
        },
        {
            "content": "Bug report: some customers receive duplicate notification emails. "
                       "The team is investigating a race condition in the email queue.",
            "days_ago": 2,
        },
        {
            "content": "Fixed the duplicate notification bug. Root cause was a missing "
                       "idempotency key in the email queue consumer. Deployed the fix to production.",
            "days_ago": 1,
        },
        {
            "content": "Project Alpha status meeting: the admin dashboard is 60% complete. "
                       "Launch date is confirmed for May 1st. All critical bugs are resolved.",
            "days_ago": 0,
        },
    ]


    updates.extend(more_updates)

    for update in updates:
        event_time = NOW - timedelta(days=update["days_ago"])
        store.add(
            content=update["content"],
            created_at=event_time,
            event_time=event_time,
        )

    print(f"Stored {len(store)} memories spanning {updates[0]['days_ago']} days.")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Standard Query with Recency Weighting

    We ask about the project status. With recency weighting, the agent should prefer the most recent status update over the kickoff meeting notes, even though both are semantically relevant.
    """)
    return


@app.cell
def _(NOW, store):
    results = store.query('What is the current project status?', top_k=5, now=NOW)
    print("Query: 'What is the current project status?'\n")
    print(f"{'Rank':<6} {'Combined':<10} {'Semantic':<10} {'Recency':<10} {'Age (days)':<12} Content")
    print('-' * 100)
    for _i, _r in enumerate(results, 1):
        _mem = _r['memory']
        _age_days = (NOW - _mem.event_time).days
        _preview = _mem.content[:70] + ('...' if len(_mem.content) > 70 else '')
        print(f"{_i:<6} {_r['combined_score']:<10.4f} {_r['semantic_score']:<10.4f} {_r['recency_score']:<10.4f} {_age_days:<12} {_preview}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Notice how the most recent status meeting (0 days old) ranks highest. The sprint review (7 days old) also ranks well. The original kickoff (30 days old) has high semantic relevance but its recency score drags it down.

    Now let us see what happens if we turn off recency weighting entirely.
    """)
    return


@app.cell
def _(NOW, store):
    results_no_recency = store.query('What is the current project status?', top_k=5, now=NOW, recency_weight=0.0)
    print('Query with recency_weight=0.0 (pure semantic):\n')
    print(f"{'Rank':<6} {'Semantic':<10} {'Age (days)':<12} Content")
    print('-' * 80)
    for _i, _r in enumerate(results_no_recency, 1):  # pure semantic
        _mem = _r['memory']
        _age_days = (NOW - _mem.event_time).days
        _preview = _mem.content[:70] + ('...' if len(_mem.content) > 70 else '')
        print(f"{_i:<6} {_r['semantic_score']:<10.4f} {_age_days:<12} {_preview}")
    print('\nWithout recency weighting, stale updates may outrank current ones.')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Time-Range Query

    Retrieve memories from the past week only. This is useful when the user asks "what happened recently?" or "what changed this sprint?"
    """)
    return


@app.cell
def _(NOW, store, timedelta):
    week_start = NOW - timedelta(days=7)
    results_week = store.query_time_range(query_text='project progress and issues', time_start=week_start, time_end=NOW, top_k=5)
    print(f'Memories from the past 7 days (since {week_start.date()}):\n')
    for _i, _r in enumerate(results_week, 1):
        _mem = _r['memory']
        _date_str = _mem.event_time.strftime('%Y-%m-%d')
        _preview = _mem.content[:90] + ('...' if len(_mem.content) > 90 else '')
        print(f'  {_i}. [{_date_str}] {_preview}')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### "As Of" Query

    Reconstruct what the agent knew on a specific past date. This is useful for auditing ("what did the agent think the status was two weeks ago?") or debugging.
    """)
    return


@app.cell
def _(NOW, store, timedelta):
    # What did the agent know 14 days ago?
    as_of_date = NOW - timedelta(days=14)
    results_as_of = store.query_as_of(query_text='What is the project status?', as_of=as_of_date, top_k=3)
    print(f"'As of' query: what did we know on {as_of_date.date()}?\n")
    for _i, _r in enumerate(results_as_of, 1):
        _mem = _r['memory']
        _date_str = _mem.event_time.strftime('%Y-%m-%d')
        print(f"  {_i}. [{_date_str}] (combined={_r['combined_score']:.4f})")
        _preview = _mem.content[:100] + ('...' if len(_mem.content) > 100 else '')
        print(f'     {_preview}')
        print()
    print('Notice: no memories from after the as_of date appear.')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Timeline Construction

    Build a chronological timeline of how the notification system evolved. The store finds related memories and orders them by event time.
    """)
    return


@app.cell
def _(store):
    timeline = store.build_timeline(topic='order notifications and email issues', similarity_threshold=0.25)
    print(f"Timeline: 'order notifications and email issues' ({len(timeline)} entries)\n")
    for _mem in timeline:
        _date_str = _mem.event_time.strftime('%Y-%m-%d')
        print(f'  [{_date_str}] {_mem.content}')
        print()
    return (timeline,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### LLM-Powered Timeline Summary

    Feed the timeline to the LLM and get a narrative summary of how the notification system evolved.
    """)
    return


@app.cell
def _(summarize_timeline, timeline):
    summary = summarize_timeline(timeline, topic="order notification system")
    print("Timeline Summary:\n")
    print(summary)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Comparing Decay Functions

    Let us visualize how exponential and linear decay behave differently. This helps you choose the right decay function for your use case.
    """)
    return


@app.cell
def _(EMBED_DIM, NOW, TemporalDecay, TemporalMemory, np, timedelta):
    # Compare exponential vs linear decay over 30 days
    exp_decay = TemporalDecay(decay_type="exponential", half_life_hours=168)
    lin_decay = TemporalDecay(decay_type="linear", half_life_hours=168)

    hours_range = np.linspace(0, 720, 200)  # 0 to 30 days
    dummy_emb = [0.0] * EMBED_DIM

    exp_scores = []
    lin_scores = []

    for h in hours_range:
        dummy_mem = TemporalMemory(
            content="test",
            embedding=dummy_emb,
            created_at=NOW - timedelta(hours=float(h)),
        )
        exp_scores.append(exp_decay.score(dummy_mem, NOW))
        lin_scores.append(lin_decay.score(dummy_mem, NOW))

    days_range = hours_range / 24

    print("Decay score comparison (exponential vs linear):\n")
    print(f"{'Age (days)':<14} {'Exponential':<14} {'Linear':<14}")
    print("-" * 42)
    for day_mark in [0, 1, 3, 7, 14, 21, 30]:
        idx = int(day_mark * 24 / 720 * 199)
        if idx >= len(exp_scores):
            idx = len(exp_scores) - 1
        print(f"{day_mark:<14} {exp_scores[idx]:<14.4f} {lin_scores[idx]:<14.4f}")

    print("\nExponential decay drops fast initially then levels off.")
    print("Linear decay drops at a constant rate and hits zero at 14 days (2x half-life).")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Using Temporal Memory in a Chat Agent

    Let us wire the temporal memory store into a conversational agent. The agent retrieves relevant memories before answering. Its responses reflect the time-awareness of its memory system.
    """)
    return


@app.cell
def _(CHAT_MODEL, NOW, TemporalMemoryStore, client, datetime, store):
    def temporal_agent_respond(
        user_question: str,
        memory_store: TemporalMemoryStore,
        now: datetime,
    ) -> str:
        """An agent that uses temporal memory to answer questions."""
        # Retrieve top-5 memories with recency weighting
        results = memory_store.query(user_question, top_k=5, now=now)

        # Format context for the LLM
        context_entries = []
        for r in results:
            mem = r["memory"]
            age_days = (now - mem.event_time).days
            date_str = mem.event_time.strftime("%Y-%m-%d")
            context_entries.append(
                f"[{date_str}, {age_days} days ago] {mem.content}"
            )
        context_block = "\n\n".join(context_entries)

        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a project assistant with access to timestamped "
                        "memories. Use the provided context to answer the user's "
                        "question. Prefer recent information when relevant. "
                        "Mention dates when they help clarify the answer. "
                        "Keep your response to 3-5 sentences."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Retrieved memories (most relevant first):\n\n"
                        f"{context_block}\n\n"
                        f"Question: {user_question}"
                    ),
                },
            ],
            max_tokens=300,
        )
        return response.choices[0].message.content


    # Test the agent with several questions
    questions = [
        "What is the current status of Project Alpha?",
        "Were there any bugs recently? What happened?",
        "How has the product search performance changed over time?",
    ]

    for q in questions:
        print(f"User: {q}")
        answer = temporal_agent_respond(q, store, NOW)
        print(f"Agent: {answer}\n")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Tradeoffs

    ### When Temporal Memory Works Well

    - **Dynamic environments**: When information becomes outdated regularly (project updates, market data, news). The decay function naturally de-prioritizes stale memories.
    - **Chronological reasoning**: When the agent needs to explain how a situation evolved. The timeline builder produces ordered narratives that a flat vector store cannot.
    - **Auditing and debugging**: "As of" queries let you reconstruct the agent's knowledge state at any past moment. This is valuable for understanding why the agent gave a particular answer.

    ### When It Falls Short

    - **Evergreen knowledge**: Facts that stay true indefinitely (math formulas, company policies, API docs) get unfairly penalized by decay. You need to either exempt certain memories from decay or set a very long half-life.
    - **Tuning complexity**: Choosing the right half-life and recency weight requires experimentation. A half-life that is too short forgets important context. One that is too long defeats the purpose of temporal awareness.
    - **Storage overhead**: Every memory now carries multiple timestamp fields and requires decay computation at query time. For large stores (100k+ entries), the per-query scoring adds latency compared to a pure vector search.
    - **Clock dependency**: The system assumes reliable timestamps. If memories arrive out of order or with incorrect timestamps, the decay scoring produces misleading results.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Further Reading

    - Park, J. S., et al. (2023). ["Generative Agents: Interactive Simulacra of Human Behavior."](https://arxiv.org/abs/2304.03442) The foundational paper demonstrating recency-weighted memory retrieval in simulated agents.

    - Zhong, W., et al. (2024). ["MemoryBank: Enhancing Large Language Models with Long-Term Memory."](https://arxiv.org/abs/2305.10250) Introduces an explicit forgetting curve mechanism inspired by Ebbinghaus, applied to LLM memory.

    - Tulving, E. (2002). ["Episodic Memory: From Mind to Brain."](https://doi.org/10.1146/annurev.psych.53.100901.135114) *Annual Review of Psychology*, 53, 1-25. Foundational cognitive science work on time-stamped human memory.

    - Hassabis, D., & Maguire, E. A. (2007). ["Deconstructing Episodic Memory with Construction."](https://doi.org/10.1016/j.tics.2007.05.001) *Trends in Cognitive Sciences*, 11(7). How humans construct episodic memories, with implications for artificial memory.

    - [OpenAI Embeddings Guide](https://platform.openai.com/docs/guides/embeddings?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques). Reference for the embedding model used in this notebook.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---

    *← Previous: [17: Memory Routing](../17_memory_routing/) · Next: [19: Forgetting & Decay](../19_forgetting_and_decay/) →*
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 🧪 Try It Yourself

    Three small challenges to deepen your understanding. Each should take 10-30 minutes.

    ### Challenge 1: Decay function comparison
    Run the same 10 queries against `TemporalMemoryStore` twice: once with exponential decay and once with linear decay in `TemporalDecay`. Compare the top-5 results for each query. Count how many results differ and identify which decay function favors recent vs. older memories.

    ### Challenge 2: Half-life tuning
    Test half-life values of 1 hour, 6 hours, 24 hours, and 7 days. For each value, run `query()` on 10 time-sensitive questions (where the correct answer changed over time). Record accuracy for each setting and find the half-life that best balances old and new information.

    ### Challenge 3: Temporal knowledge graph
    Combine `TemporalMemoryStore` with the triple extraction from 08 Knowledge Graph Memory. Add `event_time` to each triple so relationships have timestamps. Implement a `query_as_of()` that returns the graph state at a specific point in time. Test with a conversation where facts change.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--18-temporal-memory--temporal-memory)
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
