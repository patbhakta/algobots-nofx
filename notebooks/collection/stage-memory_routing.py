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
    # Memory Routing

    > **Direct every memory read and write to the right specialized store using an intelligent dispatcher.**

    Think of a large office with separate filing cabinets. One holds client conversations. Another holds company policies. A third holds step-by-step procedures. When someone needs to file a document or retrieve one, they first decide *which cabinet* to open. That decision is routing.

    As agent memory systems grow, they split into specialized stores. You might keep an **episodic** store for conversation histories, a **semantic** store for factual knowledge, and a **procedural** store for learned skills. Each store has its own data format and retrieval strategy. The challenge: how does the agent know which store to use for a given piece of information?

    Without explicit routing, agents dump everything into one big store. They lose the benefits of specialization. **Memory routing** solves this by adding a dispatcher layer between the agent and its stores. For writes, the dispatcher classifies incoming content (is this a fact, a procedure, or an experience?) and sends it to the right store. For reads, it analyzes the query's intent and searches the relevant store or stores. When multiple stores match, it merges and re-ranks the results.

    **In this notebook you'll build:**
    1. Three specialized memory stores (episodic, semantic, procedural).
    2. An LLM-powered router that classifies content and queries by type.
    3. Write and read pipelines that direct operations to the correct store.
    4. A fallback strategy for ambiguous queries that span multiple stores.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Key Concepts

    - **Memory type classification**: Sorting incoming content into categories like episodic, semantic, or procedural. The classifier can be an LLM call, keyword rules, or a small trained model.
    - **Episodic memory**: Memories of events and experiences. "Yesterday's meeting," "the user's last request," or "the error that happened at 3 PM."
    - **Semantic memory**: Memories of facts and general knowledge. "The API rate limit is 1,000 requests per minute." "Python uses indentation for blocks."
    - **Procedural memory**: Memories of how to do things. Step-by-step instructions, workflows, and recipes. "To deploy: run tests, open a PR, merge to main."
    - **Read routing**: Analyzing a query's intent to pick which store(s) to search. "What happened yesterday?" routes to episodic. "What's our refund policy?" routes to semantic.
    - **Write routing**: Directing new content to the correct store with the right formatting. A conversation event gets a timestamp. A fact gets entity tags.
    - **Store registry**: A catalog of available memory stores. It maps each memory type to a store with its description and capabilities.
    - **Fallback strategy**: What happens when the router can't classify with confidence. Common options: search all stores and merge results, or default to a general-purpose store.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Architecture

    <p align="center">
      <img src="../../images/diagrams/17_memory_routing.svg" alt="Memory Routing Architecture" width="720"/>
    </p>

    The **Agent** sends every memory operation (read or write) to the **Memory Router**. The router runs a classifier to determine the content type. For writes, it sends the content to the matching specialized store: Episodic (conversations and events), Semantic (facts and knowledge), or Procedural (skills and workflows). For reads, the router may query one or several stores based on the query's intent. Results pass through a **Merge & Re-rank** step that combines and scores items from different stores. The **Store Registry** tells the router what each store contains and how to use it.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Setup

    Install dependencies and configure your API key. You'll need `OPENAI_API_KEY` set in a `.env` file or as an environment variable.
    """)
    return


@app.cell
def _():
    # '%pip install -q openai python-dotenv' command supported automatically in marimo
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Import the OpenAI SDK and standard-library helpers. The API key loads from a `.env` file.
    """)
    return


@app.cell
def _():
    import os
    import json
    from enum import Enum
    from dataclasses import dataclass, field
    from datetime import datetime

    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv()  # reads OPENAI_API_KEY from .env

    client = OpenAI()
    MODEL = "gpt-4o-mini"  # fast and cheap for classification

    assert os.getenv("OPENAI_API_KEY"), "Set OPENAI_API_KEY in your .env file"
    return Enum, MODEL, OpenAI, client, dataclass, datetime, field, json, os


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Implementation

    ### Memory Types and Entries

    We start with the data model. A `MemoryType` enum defines the three categories the router can classify into. A `MemoryEntry` holds the content, its type, a timestamp, and a unique ID.
    """)
    return


@app.cell
def _(Enum, dataclass, datetime, field, os):
    class MemoryType(Enum):
        """The categories of memory our router supports."""
        EPISODIC = "episodic"       # conversations, meetings, events
        SEMANTIC = "semantic"       # facts, definitions, policies
        PROCEDURAL = "procedural"   # step-by-step instructions, workflows


    @dataclass
    class MemoryEntry:
        """A single item stored in one of the memory stores."""
        content: str
        memory_type: MemoryType
        metadata: dict = field(default_factory=dict)
        timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
        id: str = field(default_factory=lambda: os.urandom(8).hex())

        def __repr__(self) -> str:
            preview = self.content[:60] + ("..." if len(self.content) > 60 else "")
            return f"MemoryEntry(type={self.memory_type.value}, content={preview!r})"

    return MemoryEntry, MemoryType


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Memory Stores

    Each store holds entries of one type. The `search` method uses keyword overlap to find relevant entries. In production, you'd swap this for vector search (comparing numeric representations of text meaning) or a database query. For teaching purposes, keyword overlap keeps things transparent.
    """)
    return


@app.cell
def _(MemoryEntry, MemoryType):
    class MemoryStore:
        """A specialized store for one category of memories."""

        def __init__(self, name: str, memory_type: MemoryType, description: str):
            self.name = name
            self.memory_type = memory_type
            self.description = description
            self.entries: list[MemoryEntry] = []

        def add(self, entry: MemoryEntry) -> None:
            """Append an entry to this store."""
            self.entries.append(entry)

        def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
            """Find entries by keyword overlap with the query."""
            query_words = set(query.lower().split())
            scored = []
            for entry in self.entries:
                content_words = set(entry.content.lower().split())
                overlap = len(query_words & content_words)
                if overlap > 0:
                    scored.append((overlap, entry))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [entry for _, entry in scored[:top_k]]

        def list_all(self) -> list[MemoryEntry]:
            return list(self.entries)

        def __len__(self) -> int:
            return len(self.entries)

        def __repr__(self) -> str:
            return f"{self.name}Store({len(self.entries)} entries)"

    return (MemoryStore,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Now we create one store per memory type.
    Each store gets a name and a description.
    The router will use these descriptions to decide where incoming content belongs.
    """)
    return


@app.cell
def _(MemoryStore, MemoryType):
    # Create one store per memory type
    episodic_store = MemoryStore(
        name="Episodic",
        memory_type=MemoryType.EPISODIC,
        description="Conversations, meetings, events, and personal experiences.",
    )

    semantic_store = MemoryStore(
        name="Semantic",
        memory_type=MemoryType.SEMANTIC,
        description="Facts, definitions, policies, and general knowledge.",
    )

    procedural_store = MemoryStore(
        name="Procedural",
        memory_type=MemoryType.PROCEDURAL,
        description="Step-by-step instructions, workflows, and how-to guides.",
    )

    stores = {
        MemoryType.EPISODIC: episodic_store,
        MemoryType.SEMANTIC: semantic_store,
        MemoryType.PROCEDURAL: procedural_store,
    }

    print("Stores created:", list(stores.values()))
    return (stores,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Memory Router

    The router is the central piece. It takes every read or write request and asks the LLM: "What type of memory is this?" Based on the answer, it directs the operation to the right store.

    The `classify` method sends a short prompt to the LLM. The prompt lists each store with its description, then asks the model to return a JSON array of matching type names. For writes, the router creates a `MemoryEntry` and adds it to the target store. For reads, it searches the matching stores and returns a merged list.

    We also include `read_all_stores` as a **fallback** (a default behavior when the normal path is uncertain). If a query is ambiguous, you can search everywhere and let the results speak for themselves.
    """)
    return


@app.cell
def _(MemoryStore, MemoryType, OpenAI, json):
    class MemoryRouter:
        """Routes memory reads and writes to the correct specialized store(s)."""

        def __init__(
            self,
            client: OpenAI,
            model: str,
            stores: dict[MemoryType, MemoryStore],
        ):
            self.client = client
            self.model = model
            self.stores = stores
            self.routing_log: list[dict] = []  # tracks every routing decision

        # ── Classification ───────────────────────────────────────────
        def classify(self, text: str, operation: str) -> list[MemoryType]:
            """Ask the LLM to classify text into one or more memory types."""
            store_lines = "\n".join(
                f"- {mt.value}: {store.description}"
                for mt, store in self.stores.items()
            )

            prompt = (
                f"Classify this {operation} into one or more memory types.\n\n"
                f"Available types:\n{store_lines}\n\n"
                f"Text: {text}\n\n"
                f"Return ONLY a JSON array of matching type names.\n"
                f'Example: ["episodic", "semantic"]\n'
                f"Do not include any other text."
            )

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )

            raw = response.choices[0].message.content.strip()
            # Strip markdown code fences if the model wraps its JSON
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            type_names = json.loads(raw)
            result = [MemoryType(name) for name in type_names]

            # Log every routing decision for debugging
            self.routing_log.append({
                "operation": operation,
                "text_preview": text[:80],
                "routed_to": [t.value for t in result],
            })

            return result

    return (MemoryRouter,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The router also needs `write` and `read` methods.
    `write` classifies content and stores it in the matching store.
    `read` classifies a query, searches matching stores, and returns deduplicated results.
    """)
    return


@app.cell
def _(MemoryEntry, MemoryRouter):
    def write(self, content: str, metadata: dict | None = None) -> list[str]:
        """Classify content and store it in the matching store(s)."""
        types = self.classify(content, operation="write")
        metadata = metadata or {}

        destinations = []
        for memory_type in types:
            entry = MemoryEntry(
                content=content,
                memory_type=memory_type,
                metadata=metadata,
            )
            self.stores[memory_type].add(entry)
            destinations.append(memory_type.value)

        return destinations

    # ── Read routing ─────────────────────────────────────────────
    MemoryRouter.write = write

    def read(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """Classify the query, search matching store(s), return merged results."""
        types = self.classify(query, operation="read")

        all_results = []
        for memory_type in types:
            results = self.stores[memory_type].search(query, top_k=top_k)
            all_results.extend(results)

        # Deduplicate by entry ID (content may exist in multiple stores)
        seen = set()
        unique = []
        for entry in all_results:
            if entry.id not in seen:
                seen.add(entry.id)
                unique.append(entry)

        return unique[:top_k]
    MemoryRouter.read = read
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    For ambiguous queries, `read_all_stores` searches every store and merges results.
    This is the fallback (a safe default when the classifier is unsure).
    `get_stats` returns entry counts per store for monitoring.
    """)
    return


@app.cell
def _(MemoryEntry, MemoryRouter):
    def read_all_stores(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """Search every store. Use when the router cannot classify confidently."""
        all_results = []
        for store in self.stores.values():
            all_results.extend(store.search(query, top_k=top_k))

        seen = set()
        unique = []
        for entry in all_results:
            if entry.id not in seen:
                seen.add(entry.id)
                unique.append(entry)

        return unique[:top_k]

    # ── Stats ────────────────────────────────────────────────────
    MemoryRouter.read_all_stores = read_all_stores

    def get_stats(self) -> dict[str, int]:
        """Return entry counts per store."""
        return {mt.value: len(store) for mt, store in self.stores.items()}
    MemoryRouter.get_stats = get_stats
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Example Run

    Let's use the router end-to-end. We'll store six memories of different types, then query them back. Watch how the router classifies each piece of content and directs it to the right store.
    """)
    return


@app.cell
def _(MODEL, MemoryRouter, client, stores):
    router = MemoryRouter(client=client, model=MODEL, stores=stores)

    # Six memories spanning all three types
    memories_to_store = [
        "In Monday's standup, Alice reported a 2-hour payment API outage over the weekend.",
        "Our API rate limit is 1,000 requests per minute per client.",
        "To deploy to production: run the test suite, open a pull request, get one approval, then merge to main.",
        "During the Q3 review, the team decided to migrate from PostgreSQL to CockroachDB.",
        "The company refund policy allows full refunds within 30 days of purchase.",
        "To reset a user password: verify identity with two security questions, generate a reset token, send the reset email.",
    ]

    print("=== Writing Memories ===\n")
    for content in memories_to_store:
        destinations = router.write(content)
        print(f"Content:  {content[:75]}...")
        print(f"Routed to: {destinations}\n")

    print("Store counts:", router.get_stats())
    return (router,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Now let's query. Each question has a clear intent that maps to one store. The router classifies the query, then searches only the relevant store.
    """)
    return


@app.cell
def _(router):
    queries = ['What happened at the standup meeting?', 'What is our API rate limit?', 'How do I deploy to production?']
    print('=== Reading Memories ===\n')
    for query in queries:
        results = router.read(query)
        print(f'Query: {query}')
        if results:
            for _entry in results:
                print(f'  [{_entry.memory_type.value}] {_entry.content[:80]}')
        else:
            print('  (no results)')
        print()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Inspecting the Routing Log

    Every routing decision is recorded. This log is valuable for debugging misrouted memories and improving the classifier over time.
    """)
    return


@app.cell
def _(router):
    print('=== Routing Log (all decisions so far) ===\n')
    for i, _entry in enumerate(router.routing_log):
        direction = 'WRITE' if _entry['operation'] == 'write' else 'READ '
        targets = ', '.join(_entry['routed_to'])
        print(f'  {i + 1:2d}. [{direction}] -> {targets}')
        print(f"      {_entry['text_preview']}")
        print()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Multi-Store Queries and Fallback

    Some queries are ambiguous. "What do we know about the database?" could touch episodic memory (the migration decision) and semantic memory (database facts). The router might classify it as one type and miss results from another.

    The `read_all_stores` method is a **fan-out fallback**: it searches every store and merges all results. This costs more (one search per store) but guarantees you won't miss anything.
    """)
    return


@app.cell
def _(router):
    ambiguous_query = 'What do we know about the database migration?'
    print(f'Query: {ambiguous_query}\n')
    routed_results = router.read(ambiguous_query)
    # Standard routed read
    print(f'Routed read ({len(routed_results)} results):')
    for _entry in routed_results:
        print(f'  [{_entry.memory_type.value}] {_entry.content[:80]}')
    fallback_results = router.read_all_stores(ambiguous_query)
    print(f'\nFallback read ({len(fallback_results)} results):')
    # Fallback: fan out to all stores
    for _entry in fallback_results:
        print(f'  [{_entry.memory_type.value}] {_entry.content[:80]}')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Tradeoffs

    ### When Memory Routing Works Well

    - **Modularity.** Each store can be optimized independently. You can swap backends, tune retrieval, or change schemas (data formats) without touching other stores.
    - **Retrieval precision.** A specialized store contains only one type of content. Searches return more relevant results because there's less noise to filter out.
    - **Extensibility.** Adding a new memory type (say, a "preference" store for user settings) means creating one new store and registering it. No changes to existing stores or the agent's core logic.

    ### When It Breaks Down

    - **Latency overhead.** Every operation needs a classification call before it reaches the store. With an LLM classifier, that adds 200-500ms per operation. Keyword or embedding-based classifiers are faster but less accurate.
    - **Misrouting.** If the classifier picks the wrong type, a write lands in the wrong store and a read never finds it. Misrouted data is silently lost from the user's perspective. Good logging and fallback strategies reduce this risk.
    - **Ambiguous content.** Some information spans multiple types. "In yesterday's meeting, we set the refund window to 14 days" is both episodic (a meeting event) and semantic (a policy fact). The router must handle multi-label classification, which means the same content may live in multiple stores.
    - **Classifier cost.** Each routing decision consumes tokens. In high-throughput systems, classification costs add up. Consider caching frequent patterns or using a smaller local model.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Further Reading

    - Packer et al., ["MemGPT: Towards LLMs as Operating Systems,"](https://arxiv.org/abs/2310.08560) 2023. Demonstrates routing memory operations between main context and external storage with explicit memory management functions.
    - Zhang et al., ["A Survey on the Memory Mechanism of Large Language Model Based Agents,"](https://arxiv.org/abs/2404.13501) 2024. Categorizes memory types (episodic, semantic, procedural) and their interactions in agent architectures.
    - Lewis et al., ["Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks,"](https://arxiv.org/abs/2005.11401) 2020. The foundational RAG paper. Memory routing generalizes the RAG pattern to multiple specialized stores.
    - Weston et al., ["Memory Networks,"](https://arxiv.org/abs/1410.3916) 2015. Early work on neural networks with explicit memory modules and attention-based routing to memory slots.
    - Park et al., ["Generative Agents: Interactive Simulacra of Human Behavior,"](https://arxiv.org/abs/2304.03442) 2023. Uses distinct memory streams (observations, reflections, plans) with retrieval that weighs recency, importance, and relevance.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    *← Previous: [16 - Self-Reflection Memory](../16_self_reflection_memory/) · Next: [18 - Temporal Memory](../18_temporal_memory/) →*
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 🧪 Try It Yourself

    Three small challenges to deepen your understanding. Each should take 10-30 minutes.

    ### Challenge 1: Routing accuracy benchmark
    Create 20 test memories with hand-labeled types (episodic, semantic, procedural). Run each through `MemoryRouter.classify()` and count correct vs. incorrect classifications. Compute accuracy per type and identify which type the router confuses most.

    ### Challenge 2: Single-store vs. fallback latency
    Run 30 queries using `read()` (targeted single-store lookup) and `read_all_stores()` (search every store). Measure wall-clock time for each query. Compute the average latency difference and the percentage of queries where the fallback finds results the targeted lookup misses.

    ### Challenge 3: Four-store architecture
    Add a fourth `MemoryStore` for procedural knowledge alongside episodic and semantic stores. Update the `classify()` prompt to handle the new type. Route 20 mixed memories through the four-store system and verify correct placement. This directly extends the procedural store from 11 Procedural Memory.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--17-memory-routing--memory-routing)
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
