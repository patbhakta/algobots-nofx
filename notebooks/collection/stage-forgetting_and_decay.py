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
    # Forgetting & Decay

    > **Controlled, purposeful information loss. Remembering everything is not a feature. It's a bug.**

    Think about a kitchen pantry. If you never throw anything out, it fills up with expired items. Finding fresh ingredients gets harder. Old cans push new ones to the back. A regular cleanup (checking dates, tossing what's stale) keeps the pantry useful.

    It seems paradoxical that a memory system should deliberately forget. But unbounded memory accumulation creates real problems. As a memory store grows without pruning (removing low-value entries), retrieval quality degrades. The agent surfaces stale information alongside current facts. Embedding searches (finding entries by meaning similarity) return increasingly noisy results. Storage and inference costs climb. Worse, old memories can actively mislead. An outdated API endpoint or a superseded project plan sits in memory with the same retrieval score as the correction itself.

    The insight that forgetting is adaptive comes from neuroscience. Richards and Frankland (2017) argued that the brain actively prunes memories unlikely to be useful. This frees capacity and reduces interference between similar memories. Hermann Ebbinghaus quantified this back in 1885 with his forgetting curve. He showed that retention decays exponentially without rehearsal but can be maintained through spaced repetition (reviewing at increasing intervals). These principles translate directly to agent memory systems.

    In this notebook, you'll build a memory store with built-in decay and pruning. Each memory gets a strength score that decreases over time. When the agent retrieves a memory, its strength is reinforced. A background process periodically removes memories that fall below a threshold. The result is a self-regulating system: frequently useful memories persist, while irrelevant ones gracefully fade.

    **By the end you'll understand:**
    - How exponential decay functions model memory strength over time.
    - How retrieval-based reinforcement keeps important memories alive.
    - How pruning thresholds and storage pressure create a self-cleaning memory store.
    - How to tune half-life, boost, and threshold parameters for your use case.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Key Concepts

    - **Ebbinghaus forgetting curve**: The empirical finding that memory retention decays exponentially over time without reinforcement. The formula is `R(t) = e^(-t/S)` where `S` is memory stability. This provides the mathematical basis for all decay-based memory management.

    - **Exponential decay function**: The standard decay model: `S(t) = S_0 * e^(-lambda * t)`. Here `S_0` is the initial strength, `lambda` (the decay rate) controls how fast strength drops, and `t` is time since last access. The half-life (time to reach 50% strength) equals `ln(2) / lambda`.

    - **Half-life**: The time it takes for a memory's strength to drop to half its current value. A 24-hour half-life means an unaccessed memory loses half its strength every day. This is the main tuning knob for decay speed.

    - **Spaced repetition**: A reinforcement schedule where accessing a memory boosts its strength back up. Borrowed from learning science (the Leitner system, the SuperMemo SM-2 algorithm). In our system, each retrieval acts as a "review" that resets the decay clock.

    - **Reinforcement boost**: The amount of strength added when a memory is retrieved. A boost of 0.3 means a memory at strength 0.5 jumps to 0.8 after one retrieval. This rewards memories that prove useful.

    - **Pruning threshold**: A configurable minimum strength below which memories become candidates for removal. Memories below this value are either archived (soft delete, recoverable) or permanently removed (hard delete).

    - **Storage pressure**: When the memory store approaches capacity limits, the system can dynamically lower the pruning threshold or increase the decay rate. This triggers more aggressive forgetting to free space.

    - **Cosine similarity**: A measure of how similar two embedding vectors (lists of numbers encoding meaning) are. It ranges from -1 (opposite) to 1 (identical). We use it to find memories whose meaning is closest to a search query.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Architecture

    The forgetting and decay system operates as a continuous background process alongside the main retrieval pipeline. It manages each memory's lifecycle from creation through reinforcement to eventual pruning.

    <p align="center">
      <img src="../../images/diagrams/19_forgetting_and_decay.svg" alt="Forgetting and Decay Architecture" width="720"/>
    </p>

    <details><summary>Mermaid source</summary>

    ```mermaid
    flowchart TD
        subgraph Memory Store
            M1["Memory A<br/>strength: 0.92"]
            M2["Memory B<br/>strength: 0.45"]
            M3["Memory C<br/>strength: 0.08"]
        end

        DE[Decay Engine<br/>exponential / linear] -->|reduces strength| M1
        DE -->|reduces strength| M2
        DE -->|reduces strength| M3

        RET[Retrieval] -->|reinforcement<br/>boost strength| M1
        RET -->|reinforcement<br/>boost strength| M2

        M3 -->|below threshold| PE[Pruning Engine]
        PE -->|soft delete| AR[(Archive)]
        PE -->|hard delete| DEL[Deleted]

        SP[Storage Pressure<br/>Monitor] -->|adjusts threshold| PE

        style DE fill:#ff6b6b,color:#fff
        style RET fill:#51cf66,color:#fff
        style PE fill:#ffa94d,color:#fff
        style SP fill:#845ef7,color:#fff
    ```

    </details>

    **Data flow:** The Decay Engine periodically applies the decay function to all memories, reducing their strength scores. When a memory is retrieved, the Retrieval path boosts its strength back up. The Pruning Engine checks for memories below the threshold and either archives or deletes them. The Storage Pressure Monitor watches overall memory volume and tightens the pruning threshold when capacity limits approach.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Setup

    Install dependencies and configure API access. You'll need an `OPENAI_API_KEY` environment variable for embeddings and chat completions.
    """)
    return


@app.cell
def _():
    # '%pip install -q openai python-dotenv matplotlib numpy' command supported automatically in marimo
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Import the OpenAI SDK, standard library modules, and visualization tools. The API key loads from a `.env` file.
    """)
    return


@app.cell
def _():
    import os
    import math
    import json
    import uuid
    from dataclasses import dataclass, field
    from datetime import datetime, timedelta

    import numpy as np
    import matplotlib.pyplot as plt
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv()

    openai_client = OpenAI()  # reads OPENAI_API_KEY from environment

    assert os.getenv("OPENAI_API_KEY"), "Set OPENAI_API_KEY in your .env file"
    return (
        dataclass,
        datetime,
        field,
        math,
        np,
        openai_client,
        plt,
        timedelta,
        uuid,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Implementation

    We'll build three components:

    1. **`DecayableMemory`**: A data class that tracks each memory's content, embedding, strength, and access history.
    2. **`DecayEngine`**: Applies exponential decay to strength scores and handles reinforcement on retrieval.
    3. **`ForgettingMemoryStore`**: The main store that ties everything together with search, decay sweeps, and pruning.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Memory Data Model

    Each memory carries metadata that the decay system needs. The `strength` field starts at 1.0 (full strength) and decreases over time. The `access_count` and `last_accessed` fields track how often and how recently the memory was retrieved.
    """)
    return


@app.cell
def _(dataclass, datetime, field, uuid):
    @dataclass
    class DecayableMemory:
        """A memory entry with strength tracking for decay and reinforcement."""

        content: str
        embedding: list[float]
        strength: float = 1.0
        access_count: int = 0
        created_at: datetime = field(default_factory=datetime.utcnow)
        last_accessed: datetime = field(default_factory=datetime.utcnow)
        memory_id: str = field(default_factory=lambda: str(uuid.uuid4()))
        archived: bool = False

        def idle_hours(self, now: datetime | None = None) -> float:
            """Hours since this memory was last accessed."""
            now = now or datetime.utcnow()
            return (now - self.last_accessed).total_seconds() / 3600

        def __repr__(self) -> str:
            preview = self.content[:50] + ("..." if len(self.content) > 50 else "")
            return f"Memory(strength={self.strength:.3f}, accesses={self.access_count}, content='{preview}')"

    return (DecayableMemory,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Decay Engine

    Think of a rechargeable battery that slowly drains when idle. The decay engine models this drain. Every hour that passes without a memory being accessed reduces its strength by a predictable amount. The half-life parameter controls the drain rate.

    The key formula: `strength = current_strength * e^(-lambda * hours_idle)`, where `lambda = ln(2) / half_life_hours`.

    The `reinforce` method is like plugging the battery back in. It adds a configurable boost to the strength and resets the "last accessed" timestamp.
    """)
    return


@app.cell
def _(DecayableMemory, datetime, math):
    class DecayEngine:
        """Applies time-based exponential decay and retrieval-based reinforcement."""

        def __init__(self, half_life_hours: float=168.0, min_strength: float=0.001):
            self.decay_rate = math.log(2) / half_life_hours  # lambda = ln(2) / half_life gives exactly 50% strength at one half-life
            self.half_life_hours = half_life_hours
            self.min_strength = min_strength

        def compute_decay(self, memory: DecayableMemory, now: datetime | None=None) -> float:
            """Calculate what the strength would be after decay, without modifying the memory."""
            now = now or datetime.utcnow()
            hours_idle = memory.idle_hours(now)
            decayed = memory.strength * math.exp(-self.decay_rate * hours_idle)
            return max(decayed, self.min_strength)

        def apply_decay(self, memory: DecayableMemory, now: datetime | None=None) -> float:
            """Apply decay in place and return the new strength."""
            now = now or datetime.utcnow()
            memory.strength = self.compute_decay(memory, now)
            memory.last_accessed = now
            return memory.strength  # Update last_accessed so the next decay interval starts from here

        def reinforce(self, memory: DecayableMemory, boost: float=0.3, now: datetime | None=None) -> float:
            """Boost strength after retrieval. Caps at 1.0."""
            now = now or datetime.utcnow()
            memory.strength = min(1.0, memory.strength + boost)
            memory.access_count = memory.access_count + 1
            memory.last_accessed = now
            return memory.strength

    return (DecayEngine,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Memory Store with Forgetting

    The `ForgettingMemoryStore` brings decay, retrieval, and pruning together. When you search for memories, it:

    1. Applies decay to update all strength scores.
    2. Ranks memories by a combined score: `cosine_similarity * strength`. This means a highly relevant but decayed memory can be outranked by a moderately relevant but fresh one.
    3. Reinforces the top results (since retrieval proves their usefulness).

    The `prune` method sweeps for memories below the threshold and moves them to an archive list. The `apply_storage_pressure` method tightens the threshold when the store approaches capacity.
    """)
    return


@app.cell
def _(DecayEngine, DecayableMemory, datetime):
    class ForgettingMemoryStore:
        """Memory store with built-in decay, reinforcement, and pruning."""

        def __init__(
            self,
            half_life_hours: float = 168.0,
            prune_threshold: float = 0.1,
            max_memories: int = 1000,
            reinforce_boost: float = 0.3,
        ):
            self.memories: list[DecayableMemory] = []
            self.archive: list[DecayableMemory] = []
            self.decay_engine = DecayEngine(half_life_hours=half_life_hours)
            self.prune_threshold = prune_threshold
            self.max_memories = max_memories
            self.reinforce_boost = reinforce_boost

        def add(self, content: str, embedding: list[float], now: datetime | None = None) -> DecayableMemory:
            """Add a new memory with full initial strength."""
            now = now or datetime.utcnow()
            memory = DecayableMemory(
                content=content,
                embedding=embedding,
                created_at=now,
                last_accessed=now,
            )
            self.memories.append(memory)
            return memory

        def search(
            self,
            query_embedding: list[float],
            top_k: int = 3,
            now: datetime | None = None,
        ) -> list[tuple[DecayableMemory, float]]:
            """Find the most relevant memories. Combines similarity with strength."""
            now = now or datetime.utcnow()

            # Apply decay before scoring
            self.decay_all(now=now)

            scored = []
            for mem in self.memories:
                similarity = self._cosine_similarity(query_embedding, mem.embedding)
                combined = similarity * mem.strength
                scored.append((mem, similarity, combined))

            scored.sort(key=lambda x: x[2], reverse=True)

            results = []
            for mem, _sim, combined in scored[:top_k]:
                self.decay_engine.reinforce(mem, boost=self.reinforce_boost, now=now)
                results.append((mem, combined))
            return results

    return (ForgettingMemoryStore,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The store also needs maintenance methods.
    `decay_all` applies the decay function to every active memory.
    `prune` archives memories that fell below the strength threshold.
    `apply_storage_pressure` tightens that threshold when the store approaches capacity.
    """)
    return


@app.cell
def _(DecayableMemory, ForgettingMemoryStore, datetime, math):
    def decay_all(self, now: datetime | None = None) -> None:
        """Apply decay to every active memory."""
        now = now or datetime.utcnow()
        for mem in self.memories:
            self.decay_engine.apply_decay(mem, now)
    ForgettingMemoryStore.decay_all = decay_all

    def prune(self) -> list[DecayableMemory]:
        """Archive memories whose strength fell below the threshold."""
        survivors = []
        pruned = []
        for mem in self.memories:
            if mem.strength < self.prune_threshold:
                mem.archived = True
                self.archive.append(mem)
                pruned.append(mem)
            else:
                survivors.append(mem)
        self.memories = survivors
        return pruned
    ForgettingMemoryStore.prune = prune

    def apply_storage_pressure(self) -> None:
        """Tighten the prune threshold when approaching capacity."""
        utilization = len(self.memories) / self.max_memories
        if utilization > 0.8:
            pressure = (utilization - 0.8) / 0.2  # 0.0 at 80%, 1.0 at 100%
            self.prune_threshold = 0.1 + (0.5 - 0.1) * pressure
    ForgettingMemoryStore.apply_storage_pressure = apply_storage_pressure

    def get_stats(self) -> dict:
        """Return a summary of the store's current state."""
        strengths = [m.strength for m in self.memories]
        return {
            "active_memories": len(self.memories),
            "archived_memories": len(self.archive),
            "avg_strength": round(sum(strengths) / len(strengths), 4) if strengths else 0,
            "min_strength": round(min(strengths), 4) if strengths else 0,
            "max_strength": round(max(strengths), 4) if strengths else 0,
            "utilization": round(len(self.memories) / self.max_memories, 4),
        }
    ForgettingMemoryStore.get_stats = get_stats

    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)
    ForgettingMemoryStore._cosine_similarity = _cosine_similarity
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Embedding Helper

    We need a function to convert text into embedding vectors. These vectors (lists of numbers that encode the meaning of the text) let us compare memories by meaning rather than exact wording.
    """)
    return


@app.cell
def _(openai_client):
    def get_embedding(text: str) -> list[float]:
        """Get an embedding vector for a text string."""
        response = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return response.data[0].embedding

    return (get_embedding,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Example Run

    Let's build a personal assistant that remembers facts about a user. We'll watch how memories decay over simulated time, how retrieval reinforces important ones, and how pruning cleans up the rest.

    ### Step 1: Seed the Memory Store

    We add seven memories created at different times (6 hours apart) to simulate a realistic accumulation pattern.
    """)
    return


@app.cell
def _(ForgettingMemoryStore, datetime, get_embedding, timedelta):
    store = ForgettingMemoryStore(half_life_hours=24.0, prune_threshold=0.1, max_memories=100, reinforce_boost=0.3)
    memories_data = ["User's name is Alice and she works as a data scientist.", 'Alice is building a recommendation engine for her company.', 'Alice prefers Python over R for data analysis.', 'Alice asked about sushi restaurants in downtown.', "Alice's team has a standup meeting every morning at 9am.", 'Alice mentioned she is allergic to shellfish.', "Alice is reading 'Designing Data-Intensive Applications' by Kleppmann."]  # aggressive decay for demo purposes
    base_time = datetime(2025, 1, 1, 9, 0, 0)
    for _i, _content in enumerate(memories_data):
        _created = base_time + timedelta(hours=_i * 6)
        embedding = get_embedding(_content)
        store.add(_content, embedding, now=_created)
    # Memories from different "sessions," spaced 6 hours apart
    print(f'Added {len(store.memories)} memories to the store.\n')
    for _mem in store.memories:
        print(f'  strength={_mem.strength:.2f} | {_mem.content[:65]}')
    return base_time, store


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 2: Simulate Time and Apply Decay

    Let's jump forward 48 hours and apply decay. With a 24-hour half-life, the oldest memories (created 48+ hours ago) should be at roughly 25% strength. Newer ones will be stronger.
    """)
    return


@app.cell
def _(base_time, store, timedelta):
    # Jump forward 48 hours
    now = base_time + timedelta(hours=48)
    store.decay_all(now=now)
    print(f'After 48 hours (half-life = {store.decay_engine.half_life_hours}h):\n')
    for _mem in sorted(store.memories, key=lambda m: m.strength, reverse=True):
        age_h = (now - _mem.created_at).total_seconds() / 3600
        print(f'  strength={_mem.strength:.4f} | age={age_h:.0f}h | {_mem.content[:55]}')
    return (now,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 3: Retrieve and Reinforce

    Now we search for work-related memories. The search ranks by `similarity * strength` and then reinforces the top results. Watch how retrieved memories jump back up in strength.
    """)
    return


@app.cell
def _(get_embedding, now, store):
    query = 'What does Alice do for work?'
    query_embedding = get_embedding(query)
    results = store.search(query_embedding, top_k=3, now=now)
    print(f"Query: '{query}'\n")
    print('Retrieved and reinforced:')
    for _mem, score in results:
        print(f'  score={score:.4f} | strength={_mem.strength:.4f} | {_mem.content[:60]}')
    print(f'\nAll memories after retrieval:')
    for _mem in sorted(store.memories, key=lambda m: m.strength, reverse=True):
        marker = ' <-- reinforced' if _mem.access_count > 0 else ''
        print(f'  strength={_mem.strength:.4f} | accesses={_mem.access_count} | {_mem.content[:50]}{marker}')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 4: More Decay and Pruning

    Another 48 hours pass (96 total). Non-reinforced memories have been idle for 48-84 hours with a 24-hour half-life. Many will drop below the 0.1 pruning threshold. Reinforced memories stay strong because their "last accessed" timestamp was reset at retrieval time.
    """)
    return


@app.cell
def _(base_time, store, timedelta):
    now_1 = base_time + timedelta(hours=96)
    store.decay_all(now=now_1)
    print('Before pruning:')
    for _mem in sorted(store.memories, key=lambda m: m.strength, reverse=True):
        status = 'SAFE' if _mem.strength >= store.prune_threshold else 'PRUNE'
        print(f'  [{status}] strength={_mem.strength:.4f} | {_mem.content[:55]}')
    _pruned = store.prune()
    print(f'\nPruned {len(_pruned)} memories (threshold={store.prune_threshold}):')
    for _mem in _pruned:
        print(f'  [archived] {_mem.content[:60]}')
    print(f'\nRemaining: {len(store.memories)} active, {len(store.archive)} archived')
    _stats = store.get_stats()
    print(f"Average strength of survivors: {_stats['avg_strength']:.4f}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Visualizing Decay and Reinforcement

    Two plots show the core dynamics:

    1. **Left**: How different half-life values change the decay curve. Shorter half-lives forget faster.
    2. **Right**: How retrieval-based reinforcement keeps a memory alive while an unretrieved memory fades to the pruning threshold.
    """)
    return


@app.cell
def _(math, np, plt):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    hours = np.linspace(0, 120, 300)
    for hl, color in [(12, '#ef4444'), (24, '#f59e0b'), (48, '#10b981'), (168, '#6366f1')]:
        rate = math.log(2) / hl
    # Left plot: decay curves for different half-lives
        strengths = np.exp(-rate * hours)
        ax1.plot(hours, strengths, label=f'half-life = {hl}h', linewidth=2, color=color)
    ax1.axhline(y=0.1, color='#94a3b8', linestyle='--', alpha=0.8, label='prune threshold')
    ax1.set_xlabel('Hours Since Last Access')
    ax1.set_ylabel('Memory Strength')
    ax1.set_title('Decay Curves by Half-Life')
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(-0.05, 1.05)
    rate = math.log(2) / 24
    dt = hours[1] - hours[0]
    reinforce_at = [20, 60]
    plain = np.zeros(len(hours))
    # Right plot: unreinforced vs reinforced memory
    reinforced = np.zeros(len(hours))  # 24-hour half-life
    plain[0] = 1.0
    reinforced[0] = 1.0  # hours when retrieval happens
    for _i in range(1, len(hours)):
        plain[_i] = plain[_i - 1] * math.exp(-rate * dt)
        reinforced[_i] = reinforced[_i - 1] * math.exp(-rate * dt)
        for rt in reinforce_at:
            if abs(hours[_i] - rt) < dt:
                reinforced[_i] = min(1.0, reinforced[_i] + 0.3)
    ax2.plot(hours, plain, label='Never retrieved', linewidth=2, color='#6366f1')
    ax2.plot(hours, reinforced, label='Retrieved at h=20, h=60', linewidth=2, color='#10b981')
    ax2.axhline(y=0.1, color='#94a3b8', linestyle='--', alpha=0.8, label='prune threshold')
    for rt in reinforce_at:
        ax2.axvline(x=rt, color='#10b981', linestyle=':', alpha=0.4)
    ax2.set_xlabel('Hours')
    ax2.set_ylabel('Memory Strength')
    ax2.set_title('Decay vs. Reinforcement (half-life = 24h)')
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.set_ylim(-0.05, 1.05)
    plt.tight_layout()
    plt.show()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### End-to-End: Agent with Forgetting Memory

    Let's wire the memory store into an LLM-powered agent. The agent retrieves relevant memories before responding and stores new interactions as memories. We'll query at different simulated times to see how forgetting affects the agent's responses.
    """)
    return


@app.cell
def _(ForgettingMemoryStore, datetime, get_embedding, openai_client):
    def agent_respond(
        user_message: str,
        store: ForgettingMemoryStore,
        now: datetime | None = None,
    ) -> str:
        """Retrieve memories, call the LLM, and store the new interaction."""
        now = now or datetime.utcnow()

        # Search retrieves top memories and reinforces them
        query_embedding = get_embedding(user_message)
        results = store.search(query_embedding, top_k=3, now=now)

        # Build context from retrieved memories
        if results:
            memory_lines = []
            for mem, score in results:
                memory_lines.append(f"- {mem.content} (strength: {mem.strength:.2f})")
            memory_context = "\n".join(memory_lines)
        else:
            memory_context = "No relevant memories found."

        # Call the LLM with memory context
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant with memory. "
                        "Use the remembered facts below to inform your response.\n\n"
                        f"Remembered facts:\n{memory_context}"
                    ),
                },
                {"role": "user", "content": user_message},
            ],
        )

        assistant_text = response.choices[0].message.content

        # Store this interaction as a new memory
        interaction_text = f"User asked: '{user_message}'"
        store.add(interaction_text, get_embedding(interaction_text), now=now)

        return assistant_text

    return (agent_respond,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Run the agent at three different times. Early on, it remembers most facts. As hours pass without retrieval, some memories decay below the threshold and get pruned.
    """)
    return


@app.cell
def _(
    ForgettingMemoryStore,
    agent_respond,
    datetime,
    get_embedding,
    timedelta,
):
    demo_store = ForgettingMemoryStore(half_life_hours=24.0, prune_threshold=0.1, max_memories=50, reinforce_boost=0.3)
    seed_memories = ["User's name is Bob. He is a software engineer at a fintech startup.", 'Bob is working on a payment processing microservice written in Go.', "Bob's team uses PostgreSQL for their primary database.", 'Bob mentioned he prefers vim keybindings in VS Code.', 'Bob has a cat named Pixel.']
    base = datetime(2025, 6, 1, 9, 0, 0)
    for _i, _content in enumerate(seed_memories):
        _created = base + timedelta(hours=_i * 8)
        demo_store.add(_content, get_embedding(_content), now=_created)
    queries = [(24, 'What tech stack am I using at work?'), (72, 'Do you remember anything about my pets?'), (168, 'What do you know about me?')]
    # Seed with background knowledge
    for hours_later, question in queries:
        query_time = base + timedelta(hours=hours_later)
        print(f'=== {hours_later} hours later ===')
        print(f'User: {question}')
        reply = agent_respond(question, demo_store, now=query_time)
        print(f'Agent: {reply}')
        _pruned = demo_store.prune()
        if _pruned:
            print(f'  (Pruned {len(_pruned)} faded memories)')
        print()
    _stats = demo_store.get_stats()
    # Ask questions at increasing time offsets
    # Final stats
    print(f"Final state: {_stats['active_memories']} active, {_stats['archived_memories']} archived")  # Prune after each interaction
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Tradeoffs

    ### When Forgetting and Decay Works Well

    - **Long-lived agents** that accumulate thousands of memories over weeks or months. Without decay, retrieval quality degrades as noise increases.
    - **High-turnover environments** where information becomes stale quickly. Project statuses, schedules, prices, and preferences change often. Decay naturally deprioritizes outdated facts.
    - **Cost-sensitive deployments** where storage and embedding search costs grow with memory volume. Pruning keeps the store lean.

    ### When It Breaks Down

    - **Critical information that must never be forgotten.** A user's allergy, a legal requirement, or a safety protocol should not decay. You need an exemption mechanism (pinned memories) on top of the decay system.
    - **Rare but important memories.** A memory accessed once per year (like an annual compliance procedure) would decay and get pruned long before its next use. Access frequency does not always correlate with importance.
    - **Tuning difficulty.** The half-life, boost, and threshold parameters interact in non-obvious ways. Too aggressive a decay loses valuable context. Too slow a decay defeats the purpose. Expect iterative tuning per use case.
    - **Clock sensitivity.** The system depends on accurate timestamps. In distributed systems or when simulating time for testing, clock skew can cause unexpected behavior.

    ### Parameter Tuning Guide

    | Parameter | Low Value Effect | High Value Effect | Typical Range |
    |-----------|-----------------|-------------------|---------------|
    | `half_life_hours` | Aggressive forgetting | Slow forgetting | 24-720 hours |
    | `reinforce_boost` | Weak reinforcement | Strong reinforcement | 0.1-0.5 |
    | `prune_threshold` | Keeps weak memories | Prunes aggressively | 0.05-0.3 |
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Further Reading

    - Ebbinghaus, H. (1885). [*Memory: A Contribution to Experimental Psychology.*](https://psychclassics.yorku.ca/Ebbinghaus/) Translated by Ruger & Bussenius, 1913. The original experimental work establishing the forgetting curve and spacing effect.

    - Zhong, W., et al. (2024). ["MemoryBank: Enhancing Large Language Models with Long-Term Memory."](https://arxiv.org/abs/2305.10250) Applies Ebbinghaus-inspired forgetting to LLM memory. Demonstrates improved long-term conversation quality.

    - Richards, B. A., & Frankland, P. W. (2017). ["The Persistence and Transience of Memory."](https://doi.org/10.1016/j.neuron.2017.04.037) *Neuron*, 94(6), 1071-1084. Argues that biological forgetting optimizes memory for decision-making.

    - Wozniak, P. A., & Gorzelanczyk, E. J. (1994). "Optimization of Repetition Spacing in the Practice of Learning." *Acta Neurobiologiae Experimentalis*, 54, 59-62. The theoretical basis for the SuperMemo SM-2 spaced repetition algorithm.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---

    *Previous: [18: Temporal Memory](../18_temporal_memory/) | Next: [20: Memory Retrieval Patterns](../20_memory_retrieval_patterns/)*
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 🧪 Try It Yourself

    Three small challenges to deepen your understanding. Each should take 10-30 minutes.

    ### Challenge 1: Reinforcement strategies
    Modify the `reinforce()` method in `DecayEngine` to accept a variable boost amount. Test three strategies: fixed boost (0.3), proportional boost (0.2 x current strength), and full reset (strength back to 1.0). Run 10 decay-reinforce cycles for each and plot the strength curves.

    ### Challenge 2: Survival analysis
    Add 20 memories to `ForgettingMemoryStore` and run `decay_all()` plus `prune()` for 20 cycles. After each cycle, record how many memories survive. Plot the survival curve. Measure how half-life and pruning threshold affect median memory lifespan.

    ### Challenge 3: Importance-based decay resistance
    Add an `importance` score to `DecayableMemory`. Modify `DecayEngine.compute_decay()` so high-importance memories decay at half the rate. Run a 30-turn conversation, assign importance scores based on entity mentions, and compare survival rates. This connects to the importance scoring in 14 Memory Consolidation.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--19-forgetting-and-decay--forgetting-and-decay)
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
