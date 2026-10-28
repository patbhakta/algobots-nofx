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
    # Memory Evaluation

    > **Building a memory system is only half the battle. Measuring whether it actually works is the other half. Memory evaluation gives you the metrics and tooling to answer: Does retrieval find the right memories? Does the agent use them faithfully? Are outdated facts being served? Are contradictions lurking in the store?**

    Most teams build memory systems, deploy them, and hope for the best. When users complain that "the bot forgot what I said" or "it keeps giving me outdated info," there's no systematic way to diagnose the problem. Memory evaluation fills this gap with quantitative metrics and automated scoring.

    Think of it like grading a student's open-book exam. The student (your agent) has access to notes (memories). You want to know: Did they find the right notes? Did they use them accurately? Did they pick up-to-date information rather than old drafts?

    This notebook implements a **lightweight evaluation harness** (a test framework) covering four key dimensions:
    1. **Retrieval quality:** Recall@K, Precision@K, and Mean Reciprocal Rank (MRR).
    2. **Faithfulness:** Does the agent's response accurately reflect retrieved memories, without hallucination (making things up)?
    3. **Temporal accuracy:** When facts have been updated, does retrieval prefer the latest version?
    4. **Contradiction rate:** What fraction of stored memories conflict with each other?

    **By the end of this notebook you'll be able to:**
    - Build synthetic evaluation datasets with ground-truth annotations.
    - Compute retrieval metrics against known-relevant memories.
    - Use LLM-as-judge patterns (where a language model scores quality) for faithfulness and contradiction scoring.
    - Run a full evaluation pipeline and interpret the results.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Key Concepts

    - **Recall@K:** Of all memories relevant to a query, what fraction appear in the top-K retrieved results? High recall means the system doesn't miss important context. Example: if 2 memories are relevant and both appear in the top 5, recall@5 = 1.0.
    - **Precision@K:** Of the top-K retrieved memories, what fraction are actually relevant? High precision means the system doesn't pollute context with irrelevant memories. Example: if 2 of 5 retrieved memories are relevant, precision@5 = 0.4.
    - **Mean Reciprocal Rank (MRR):** The average of 1/rank for the first relevant memory across all queries. It measures how quickly the system surfaces the best match. If the first relevant result is always at position 1, MRR = 1.0.
    - **Faithfulness:** Does the agent's response accurately reflect the retrieved memories, without adding unsupported claims? We evaluate this via LLM-as-judge (asking a model to score accuracy).
    - **Temporal accuracy:** When multiple versions of a fact exist (e.g., old address and new address), does retrieval prefer the most recent? This is critical for agents that track evolving user state.
    - **Contradiction rate:** What fraction of stored memories contain mutually conflicting information? Unchecked contradictions cause inconsistent agent behavior.
    - **LLM-as-judge:** Using a language model to score subjective qualities (faithfulness, contradiction) that rule-based metrics can't capture. Research shows it correlates well with human judgment when properly prompted.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Architecture

    <p align="center">
      <img src="../../images/diagrams/28_memory_evaluation.svg" alt="diagram" width="720"/>
    </p>

    <details><summary>Mermaid source</summary>

    ```mermaid
    flowchart TD
        subgraph Inputs["Evaluation Inputs"]
            MS[("Memory Store\n─────────\nrecords\ntimestamps\nsupersedes")]
            ED["Eval Dataset\n─────────\nqueries\nrelevant_ids\nexpected answers"]
        end

        subgraph Pipeline["Eval Harness"]
            direction TB
            R["Retrieval Metrics\nRecall@K \u00b7 Precision@K \u00b7 MRR"]
            F["Faithfulness Scorer\n(LLM-as-Judge)"]
            T["Temporal Accuracy\nChecker"]
            C["Contradiction\nDetector"]
        end

        subgraph Report["Eval Report"]
            S["Aggregate Scores"]
            D["Per-Query Detail"]
            V["Visualizations"]
        end

        MS --> R & T & C
        ED --> R & F
        R --> S
        F --> S
        T --> S
        C --> S
        S --> D --> V

        style MS fill:#4f46e5,color:#fff
        style ED fill:#059669,color:#fff
        style S fill:#d97706,color:#fff
    ```

    </details>
    """)
    return


@app.cell
def _():
    # Install required packages (run once)
    # '%pip install -q anthropic python-dotenv matplotlib numpy' command supported automatically in marimo
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    We load the API key and set up the Anthropic client. You need an `ANTHROPIC_API_KEY` in your `.env` file.
    """)
    return


@app.cell
def _():
    import os
    import json
    from dataclasses import dataclass, field
    from datetime import datetime
    from dotenv import load_dotenv

    load_dotenv()  # reads API keys from .env

    import anthropic
    import numpy as np

    assert os.getenv("ANTHROPIC_API_KEY"), "Set ANTHROPIC_API_KEY in your .env file"

    print("\u2713 API key loaded")
    print(f"\u2713 anthropic version: {anthropic.__version__}")
    return anthropic, dataclass, field, json, np


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Core Implementation

    Our evaluation harness has five components:

    1. **`MemoryRecord`:** A timestamped memory entry with an optional `supersedes` field for temporal tracking. ("Supersedes" means "this newer record replaces an older one.")
    2. **`SimpleMemoryStore`:** A keyword-overlap retrieval store (the system under test). You can swap in your own store.
    3. **Retrieval metrics:** `recall_at_k`, `precision_at_k`, `mrr`, computed against ground-truth relevance labels.
    4. **LLM-as-judge scorers:** `FaithfulnessJudge` and `ContradictionDetector` using Claude for subjective evaluation.
    5. **`MemoryEvalHarness`:** Orchestrates all metrics and produces an aggregate report.
    """)
    return


@app.cell
def _(dataclass, field):
    @dataclass
    class MemoryRecord:
        """A single memory entry with metadata for evaluation."""

        id: str
        content: str
        timestamp: str  # ISO 8601
        tags: list[str] = field(default_factory=list)
        supersedes: str | None = None  # ID of older memory this one replaces

        def __repr__(self) -> str:
            short = self.content[:50] + "..." if len(self.content) > 50 else self.content
            return f"Memory({self.id}: {short})"

    return (MemoryRecord,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    `SimpleMemoryStore` is the retrieval system we'll evaluate. It uses keyword overlap to score relevance. This is intentionally basic. The point of this notebook is to evaluate memory systems, not build a fancy one. You can swap in your own store to test it.
    """)
    return


@app.cell
def _(MemoryRecord):
    class SimpleMemoryStore:
        """A basic memory store with keyword-overlap retrieval.

        This is intentionally simple. The point of this notebook is to
        *evaluate* memory systems, not build a sophisticated one. Replace
        this class with your own store to evaluate it.
        """

        def __init__(self):
            self.records: dict[str, MemoryRecord] = {}

        def add(self, record: MemoryRecord) -> None:
            """Add a memory record to the store."""
            self.records[record.id] = record

        def retrieve(self, query: str, k: int = 5) -> list[MemoryRecord]:
            """Retrieve top-k records by keyword overlap score."""
            query_words = set(query.lower().split())
            scored = []
            for record in self.records.values():
                content_words = set(record.content.lower().split())
                overlap = len(query_words & content_words)
                tag_bonus = sum(1 for t in record.tags if t.lower() in query.lower())
                score = overlap + tag_bonus * 2
                if score > 0:
                    scored.append((score, record))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [r for _, r in scored[:k]]

        def get(self, record_id: str) -> MemoryRecord | None:
            return self.records.get(record_id)

        def get_all(self) -> list[MemoryRecord]:
            return list(self.records.values())

        def get_temporal_pairs(self) -> list[tuple[MemoryRecord, MemoryRecord]]:
            """Find (old, new) pairs where new.supersedes points to old."""
            pairs = []
            for record in self.records.values():
                if record.supersedes and record.supersedes in self.records:
                    old = self.records[record.supersedes]
                    pairs.append((old, record))
            return pairs

        def __len__(self) -> int:
            return len(self.records)


    print("\u2713 MemoryRecord and SimpleMemoryStore defined")
    return (SimpleMemoryStore,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    We build a synthetic dataset: 12 memory records about a user named Alice. The data includes base facts, a contradicting pair (coffee habits), and two temporal updates (job change and city move). The `supersedes` field marks which old record each new record replaces.
    """)
    return


@app.cell
def _(MemoryRecord, SimpleMemoryStore, dataclass):
    # ── Build a synthetic evaluation dataset ──
    # Scenario: personal assistant tracking facts about a user named Alice.

    store = SimpleMemoryStore()

    memories = [
        # Base facts
        MemoryRecord("m01", "Alice works as a software engineer at Google", "2024-01-15", ["work", "job"]),
        MemoryRecord("m02", "Alice lives in San Francisco", "2024-01-15", ["location", "home"]),
        MemoryRecord("m03", "Alice prefers Python for scripting tasks", "2024-02-10", ["programming", "preferences"]),
        MemoryRecord("m04", "Alice enjoys hiking and trail running on weekends", "2024-03-01", ["hobbies", "exercise"]),
        MemoryRecord("m05", "Alice is allergic to peanuts and tree nuts", "2024-01-15", ["health", "allergies"]),
        MemoryRecord("m06", "Alice has a golden retriever named Max", "2024-04-01", ["pets"]),
        MemoryRecord("m07", "Alice is training for the SF marathon in October", "2024-05-15", ["exercise", "goals"]),
        MemoryRecord("m08", "Alice started learning Rust for systems programming", "2024-06-01", ["programming"]),
        # Contradicting pair: coffee habits
        MemoryRecord("m09", "Alice drinks green tea every morning, she switched from coffee", "2024-07-01", ["preferences", "drinks"]),
        MemoryRecord("m10", "Alice loves espresso and drinks three cups daily", "2024-03-15", ["preferences", "drinks"]),
        # Temporal updates (supersede older facts)
        MemoryRecord("m11", "Alice joined Anthropic as a senior engineer in March 2025", "2025-03-01", ["work", "job"], supersedes="m01"),
        MemoryRecord("m12", "Alice moved to New York City in January 2025", "2025-01-15", ["location", "home"], supersedes="m02"),
    ]

    for m in memories:
        store.add(m)

    print(f"\u2713 Memory store built: {len(store)} records")
    print(f"  Temporal pairs: {len(store.get_temporal_pairs())}")
    for old, new in store.get_temporal_pairs():
        print(f"    {old.id} \u2192 {new.id}: \"{old.content[:40]}...\" superseded by \"{new.content[:40]}...\"")


    # ── Evaluation cases: queries with ground-truth relevant memory IDs ──

    @dataclass
    class EvalCase:
        """A single evaluation query with ground-truth annotations."""

        query: str
        relevant_ids: list[str]   # IDs of memories that are relevant
        expected_answer: str       # What a correct response should convey
        temporal_preferred: str | None = None  # ID that should rank highest (newest)

    return EvalCase, store


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Each `EvalCase` pairs a query with the IDs of memories that should be relevant. Some cases also mark a `temporal_preferred` ID: the newer record that should rank above the outdated one. These ground-truth labels let us compute retrieval metrics without guessing.
    """)
    return


@app.cell
def _(EvalCase):
    eval_cases = [
        EvalCase(
            query="Where does Alice work?",
            relevant_ids=["m01", "m11"],
            expected_answer="Alice works at Anthropic as a senior engineer (as of March 2025).",
            temporal_preferred="m11",
        ),
        EvalCase(
            query="Where does Alice live?",
            relevant_ids=["m02", "m12"],
            expected_answer="Alice lives in New York City (moved in January 2025).",
            temporal_preferred="m12",
        ),
        EvalCase(
            query="What programming languages does Alice use?",
            relevant_ids=["m03", "m08"],
            expected_answer="Alice uses Python for scripting and is learning Rust for systems programming.",
        ),
        EvalCase(
            query="What are Alice\'s hobbies and exercise habits?",
            relevant_ids=["m04", "m07"],
            expected_answer="Alice enjoys hiking, trail running, and is training for the SF marathon.",
        ),
        EvalCase(
            query="Does Alice have any food allergies?",
            relevant_ids=["m05"],
            expected_answer="Yes, Alice is allergic to peanuts and tree nuts.",
        ),
        EvalCase(
            query="Does Alice have any pets?",
            relevant_ids=["m06"],
            expected_answer="Yes, Alice has a golden retriever named Max.",
        ),
        EvalCase(
            query="What does Alice like to drink in the morning?",
            relevant_ids=["m09", "m10"],
            expected_answer="Alice drinks green tea every morning. She switched from coffee.",
            temporal_preferred="m09",
        ),
    ]

    print(f"\n\u2713 Eval dataset built: {len(eval_cases)} test queries")
    for ec in eval_cases:
        print(f"  \u2022 \"{ec.query}\" \u2192 relevant: {ec.relevant_ids}")
    return (eval_cases,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Retrieval Metrics

    These metrics compare the memory store's retrieval results against ground-truth relevance labels. No LLM calls needed here. It's pure computation.
    """)
    return


@app.cell
def _():
    # ── Retrieval Metrics ──

    def recall_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
        """Of all relevant memories, what fraction appear in the top-K retrieved?

        recall@K = |retrieved_top_k \u2229 relevant| / |relevant|
        """
        if not relevant_ids:
            return 1.0
        top_k = set(retrieved_ids[:k])
        relevant = set(relevant_ids)
        return len(top_k & relevant) / len(relevant)


    def precision_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
        """Of the top-K retrieved memories, what fraction are relevant?

        precision@K = |retrieved_top_k \u2229 relevant| / K
        """
        if k == 0:
            return 0.0
        top_k = set(retrieved_ids[:k])
        relevant = set(relevant_ids)
        return len(top_k & relevant) / k


    def mean_reciprocal_rank(retrieved_ids: list[str], relevant_ids: list[str]) -> float:
        """1/rank of the first relevant result. 0 if none found."""
        relevant = set(relevant_ids)
        for i, rid in enumerate(retrieved_ids):
            if rid in relevant:
                return 1.0 / (i + 1)
        return 0.0


    # ── Quick sanity check ──
    print("\u2713 Retrieval metric functions defined\n")

    example_retrieved = ["m11", "m01", "m03", "m06"]
    example_relevant = ["m01", "m11"]

    print(f"Example: retrieved={example_retrieved}, relevant={example_relevant}")
    print(f"  Recall@3:    {recall_at_k(example_retrieved, example_relevant, k=3):.2f}")
    print(f"  Precision@3: {precision_at_k(example_retrieved, example_relevant, k=3):.2f}")
    print(f"  MRR:         {mean_reciprocal_rank(example_retrieved, example_relevant):.2f}")
    return mean_reciprocal_rank, precision_at_k, recall_at_k


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `FaithfulnessJudge` uses Claude to score whether an agent's response is faithful to the retrieved memories. "Faithful" means every claim in the response is backed by at least one source memory. The judge returns a score from 0 to 1, a reasoning sentence, and a list of any unsupported claims.
    """)
    return


@app.cell
def _(anthropic, json):
    class FaithfulnessJudge:
        """Uses Claude to score whether a response is faithful to retrieved memories.

        Faithfulness = the response only makes claims supported by the source memories.
        A faithful response may omit information but must not hallucinate.
        """

        def __init__(self, model: str = "claude-sonnet-4-20250514"):
            self.client = anthropic.Anthropic()
            self.model = model

        def score(self, query: str, response: str, memories: list[str]) -> dict:
            """Score faithfulness of a response given source memories.

            Returns:
                dict with 'score' (0.0-1.0), 'reasoning', and 'unsupported_claims'
            """
            memories_text = "\n".join(f"  - {m}" for m in memories)

            result = self.client.messages.create(
                model=self.model,
                max_tokens=512,
                system=(
                    "You are an evaluation judge. Score whether a response is faithful to "
                    "the provided source memories. Faithful means: every claim in the response "
                    "is supported by at least one source memory. The response may omit info "
                    "but must NOT add unsupported claims. Return ONLY a JSON object."
                ),
                messages=[{
                    "role": "user",
                    "content": (
                        f"Query: {query}\n\n"
                        f"Source memories:\n{memories_text}\n\n"
                        f"Response to evaluate: {response}\n\n"
                        "Return a JSON object with:\n"
                        '- "score": float 0.0-1.0 (1.0 = fully faithful)\n'
                        '- "reasoning": one sentence explaining the score\n'
                        '- "unsupported_claims": list of claims not supported by source memories\n'
                    ),
                }],
            )

            try:
                text = result.content[0].text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                return json.loads(text)
            except (json.JSONDecodeError, IndexError):
                return {"score": 0.5, "reasoning": "Could not parse judge response", "unsupported_claims": []}


    print("\u2713 FaithfulnessJudge defined (uses Claude as evaluator)")
    return (FaithfulnessJudge,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    `temporal_accuracy_score` checks whether retrieval prefers newer facts over superseded ones. For each eval case with a `temporal_preferred` ID, it verifies that the newer record ranks above the older one in the results.
    """)
    return


@app.cell
def _(EvalCase, SimpleMemoryStore):
    def temporal_accuracy_score(
        store: SimpleMemoryStore,
        eval_cases: list[EvalCase],
        k: int = 5,
    ) -> dict:
        """Check if retrieval prefers newer facts over superseded ones.

        For each eval case with a temporal_preferred ID, check whether
        that ID ranks higher than the older superseded memory.

        Returns:
            dict with 'score' (fraction correct), 'details' per case
        """
        temporal_cases = [ec for ec in eval_cases if ec.temporal_preferred]
        if not temporal_cases:
            return {"score": 1.0, "details": [], "n_cases": 0}

        details = []
        correct = 0
        for ec in temporal_cases:
            retrieved = store.retrieve(ec.query, k=k)
            retrieved_ids = [r.id for r in retrieved]
            preferred = ec.temporal_preferred

            if preferred in retrieved_ids:
                preferred_rank = retrieved_ids.index(preferred)
                is_correct = True
                for rid in ec.relevant_ids:
                    if rid != preferred and rid in retrieved_ids:
                        if retrieved_ids.index(rid) < preferred_rank:
                            is_correct = False
                            break
                if is_correct:
                    correct += 1
            else:
                is_correct = False

            details.append({
                "query": ec.query,
                "preferred": preferred,
                "retrieved_order": retrieved_ids,
                "correct": is_correct,
            })

        return {"score": correct / len(temporal_cases), "details": details, "n_cases": len(temporal_cases)}

    return (temporal_accuracy_score,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `ContradictionDetector` uses Claude to find conflicting statements among stored memories. It batches memories to control API cost, then asks the model to identify pairs that make incompatible claims about the same subject. The contradiction rate is the fraction of all possible pairs that conflict.
    """)
    return


@app.cell
def _(anthropic):
    class ContradictionDetector:
        """Uses Claude to detect contradictions between memories."""

        def __init__(self, model: str = "claude-sonnet-4-20250514"):
            self.client = anthropic.Anthropic()
            self.model = model

    return (ContradictionDetector,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `scan` method batches memories and asks Claude to find contradicting pairs. It processes memories in groups to keep API costs down. Each contradiction includes the IDs of both conflicting memories and an explanation.
    """)
    return


@app.cell
def _(ContradictionDetector, MemoryRecord, json):
    def scan(self, memories: list[MemoryRecord], batch_size: int = 15) -> dict:
        """Scan memory entries for contradictions using LLM-as-judge.

        Batches memories to control cost rather than checking all O(n\u00b2) pairs.

        Returns:
            dict with 'contradiction_rate', 'contradictions' list, 'n_found'
        """
        contents = [f"[{m.id}] ({m.timestamp}) {m.content}" for m in memories]

        # Process in batches
        batches = [contents[i:i + batch_size] for i in range(0, len(contents), batch_size)]

        all_contradictions = []
        for batch in batches:
            memories_text = "\n".join(batch)

            result = self.client.messages.create(
                model=self.model,
                max_tokens=512,
                system=(
                    "You are a contradiction detector. Given a list of memory entries, "
                    "identify any pairs that contradict each other. Two memories contradict "
                    "if they make incompatible claims about the same subject. "
                    "A newer fact superseding an older one IS a contradiction to flag. "
                    "Return ONLY a JSON object."
                ),
                messages=[{
                    "role": "user",
                    "content": (
                        f"Memory entries:\n{memories_text}\n\n"
                        "Return a JSON object with:\n"
                        '- "contradictions": list of objects each with "id_a", "id_b", "explanation"\n'
                        '- "count": number of contradictions found\n'
                        "Use empty list if no contradictions."
                    ),
                }],
            )

            try:
                text = result.content[0].text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                parsed = json.loads(text)
                all_contradictions.extend(parsed.get("contradictions", []))
            except (json.JSONDecodeError, IndexError):
                pass

        n_pairs = len(memories) * (len(memories) - 1) // 2
        return {
            "contradiction_rate": len(all_contradictions) / max(n_pairs, 1),
            "contradictions": all_contradictions,
            "n_found": len(all_contradictions),
            "n_memories": len(memories),
        }

    ContradictionDetector.scan = scan

    print("\u2713 temporal_accuracy_score and ContradictionDetector defined")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `MemoryEvalHarness` orchestrates all four evaluation dimensions into one report. It wires together the retrieval metrics, faithfulness judge, temporal checker, and contradiction detector. The constructor also creates an LLM client for generating test responses from retrieved memories.
    """)
    return


@app.cell
def _(
    ContradictionDetector,
    EvalCase,
    FaithfulnessJudge,
    MemoryRecord,
    SimpleMemoryStore,
    anthropic,
):
    class MemoryEvalHarness:
        """Orchestrates all memory evaluation metrics into a unified report.

        Usage:
            harness = MemoryEvalHarness(store, eval_cases)
            report = harness.run(k=3)
        """

        def __init__(
            self,
            store: SimpleMemoryStore,
            eval_cases: list[EvalCase],
            model: str = "claude-sonnet-4-20250514",
        ):
            self.store = store
            self.eval_cases = eval_cases
            self.faithfulness_judge = FaithfulnessJudge(model=model)
            self.contradiction_detector = ContradictionDetector(model=model)
            self.client = anthropic.Anthropic()
            self.model = model

        def _generate_response(self, query: str, memories: list[MemoryRecord]) -> str:
            """Generate an agent response using retrieved memories."""
            context = "\n".join(f"- {m.content}" for m in memories)
            result = self.client.messages.create(
                model=self.model,
                max_tokens=256,
                system="Answer the user's question using ONLY the provided memories. Be concise.",
                messages=[{"role": "user", "content": f"Memories:\n{context}\n\nQuestion: {query}"}],
            )
            return result.content[0].text

    return (MemoryEvalHarness,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `run` method executes the full evaluation pipeline. It retrieves memories for each query, computes retrieval metrics, generates responses and scores their faithfulness, checks temporal accuracy, and scans for contradictions. It returns a structured report with aggregate scores and per-query details.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    `_eval_retrieval` runs retrieval metrics (Recall@K, Precision@K, MRR) for every eval case. It retrieves memories from the store and compares the result IDs against ground-truth labels. No LLM calls here.
    """)
    return


@app.cell
def _(MemoryEvalHarness, mean_reciprocal_rank, precision_at_k, recall_at_k):
    def _eval_retrieval(self, k: int, verbose: bool) -> tuple[list, list, list, list]:
        """Evaluate retrieval metrics for all eval cases.

        Returns:
            Tuple of (all_recall, all_precision, all_mrr, retrieval_details).
        """
        if verbose:
            print("\n\u2500\u2500 Retrieval Metrics \u2500\u2500")

        retrieval_details = []
        all_recall, all_precision, all_mrr = [], [], []

        for ec in self.eval_cases:
            retrieved = self.store.retrieve(ec.query, k=k)
            retrieved_ids = [r.id for r in retrieved]

            r = recall_at_k(retrieved_ids, ec.relevant_ids, k)
            p = precision_at_k(retrieved_ids, ec.relevant_ids, k)
            m = mean_reciprocal_rank(retrieved_ids, ec.relevant_ids)

            all_recall.append(r)
            all_precision.append(p)
            all_mrr.append(m)

            retrieval_details.append({
                "query": ec.query, "retrieved_ids": retrieved_ids,
                "relevant_ids": ec.relevant_ids,
                "recall_at_k": r, "precision_at_k": p, "mrr": m,
            })

            if verbose:
                status = "\u2713" if r == 1.0 else "\u2717"
                print(f"  {status} \"{ec.query}\"")
                print(f"    Retrieved: {retrieved_ids} | Relevant: {ec.relevant_ids}")
                print(f"    Recall@{k}={r:.2f}  Precision@{k}={p:.2f}  MRR={m:.2f}")

        return all_recall, all_precision, all_mrr, retrieval_details

    MemoryEvalHarness._eval_retrieval = _eval_retrieval
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    `_eval_faithfulness` generates a response from retrieved memories, then asks Claude to judge whether the response is faithful. It scores each query independently and collects any unsupported claims.
    """)
    return


@app.cell
def _(MemoryEvalHarness):
    def _eval_faithfulness(self, k: int, verbose: bool) -> tuple[list, list]:
        """Evaluate faithfulness for all eval cases using LLM-as-judge.

        Returns:
            Tuple of (all_faith_scores, faithfulness_details).
        """
        if verbose:
            print("\n\u2500\u2500 Faithfulness (LLM-as-Judge) \u2500\u2500")

        faithfulness_details = []
        all_faith = []

        for ec in self.eval_cases:
            retrieved = self.store.retrieve(ec.query, k=k)
            memory_texts = [r.content for r in retrieved]
            response = self._generate_response(ec.query, retrieved)
            faith_result = self.faithfulness_judge.score(ec.query, response, memory_texts)
            faith_score = faith_result.get("score", 0.5)
            all_faith.append(faith_score)

            faithfulness_details.append({
                "query": ec.query, "response": response,
                "score": faith_score,
                "reasoning": faith_result.get("reasoning", ""),
                "unsupported": faith_result.get("unsupported_claims", []),
            })

            if verbose:
                status = "\u2713" if faith_score >= 0.8 else "\u2717"
                print(f"  {status} \"{ec.query}\" \u2192 faithfulness={faith_score:.2f}")
                for claim in faith_result.get("unsupported_claims", []):
                    print(f"    \u26a0 Unsupported: {claim}")

        return all_faith, faithfulness_details

    MemoryEvalHarness._eval_faithfulness = _eval_faithfulness
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `run` method orchestrates the full pipeline. It calls the retrieval and faithfulness helpers above, then runs temporal accuracy and contradiction checks. It returns a structured report with all scores.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `run` method is now a thin orchestrator. It calls helpers for retrieval metrics, faithfulness scoring, temporal accuracy, and contradiction detection. Then it assembles the report.
    """)
    return


@app.cell
def _(MemoryEvalHarness):
    def run(self, k: int = 3, verbose: bool = True) -> dict:
        """Run the full evaluation pipeline.

        Args:
            k: Number of memories to retrieve per query.
            verbose: Print progress during evaluation.

        Returns:
            Dict with aggregate scores and per-query details.
        """
        if verbose:
            print("=" * 60)
            print("MEMORY EVALUATION REPORT")
            print("=" * 60)

        # 1. Retrieval metrics
        all_recall, all_precision, all_mrr, retrieval_details = self._eval_retrieval(k, verbose)

        # 2. Faithfulness
        all_faith, faithfulness_details = self._eval_faithfulness(k, verbose)

        # 3-4. Temporal accuracy and contradiction scan
        temporal, contradictions = self._eval_temporal_and_contradictions(k, verbose)

        return self._build_report(
            k, verbose, all_recall, all_precision, all_mrr,
            retrieval_details, all_faith, faithfulness_details,
            temporal, contradictions,
        )

    MemoryEvalHarness.run = run
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    `_eval_temporal_and_contradictions` checks two things. First, whether retrieval prefers newer facts over superseded ones. Second, whether any stored memories conflict with each other.
    """)
    return


@app.cell
def _(MemoryEvalHarness, temporal_accuracy_score):
    def _eval_temporal_and_contradictions(self, k: int, verbose: bool) -> tuple[dict, dict]:
        """Run temporal accuracy and contradiction checks."""
        if verbose:
            print("\n\u2500\u2500 Temporal Accuracy \u2500\u2500")
        temporal = temporal_accuracy_score(self.store, self.eval_cases, k=k)
        if verbose:
            for d in temporal["details"]:
                status = "\u2713" if d["correct"] else "\u2717"
                print(f"  {status} \"{d['query']}\" \u2192 preferred={d['preferred']}, retrieved={d['retrieved_order']}")

        if verbose:
            print("\n\u2500\u2500 Contradiction Scan \u2500\u2500")
        contradictions = self.contradiction_detector.scan(self.store.get_all())
        if verbose:
            print(f"  Found {contradictions['n_found']} contradiction(s) in {contradictions['n_memories']} memories")
            for c in contradictions["contradictions"]:
                print(f"    \u26a0 {c['id_a']} \u2194 {c['id_b']}: {c.get('explanation', '')}")

        return temporal, contradictions

    MemoryEvalHarness._eval_temporal_and_contradictions = _eval_temporal_and_contradictions
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    `_build_report` gathers all scores into a structured dictionary and prints the summary table. This is the final step in the evaluation pipeline.
    """)
    return


@app.cell
def _(MemoryEvalHarness, np):
    def _build_report(
        self, k, verbose, all_recall, all_precision, all_mrr,
        retrieval_details, all_faith, faithfulness_details,
        temporal, contradictions,
    ) -> dict:
        """Assemble the final evaluation report and print summary."""
        report = {
            "retrieval": {
                "mean_recall_at_k": float(np.mean(all_recall)),
                "mean_precision_at_k": float(np.mean(all_precision)),
                "mean_mrr": float(np.mean(all_mrr)),
                "k": k,
                "details": retrieval_details,
            },
            "faithfulness": {
                "mean_score": float(np.mean(all_faith)),
                "details": faithfulness_details,
            },
            "temporal": temporal,
            "contradictions": contradictions,
        }

        if verbose:
            print("\n" + "=" * 60)
            print("SUMMARY")
            print("=" * 60)
            print(f"  Retrieval Recall@{k}:    {report['retrieval']['mean_recall_at_k']:.2f}")
            print(f"  Retrieval Precision@{k}: {report['retrieval']['mean_precision_at_k']:.2f}")
            print(f"  Mean Reciprocal Rank:    {report['retrieval']['mean_mrr']:.2f}")
            print(f"  Faithfulness:            {report['faithfulness']['mean_score']:.2f}")
            print(f"  Temporal Accuracy:       {report['temporal']['score']:.2f}")
            print(f"  Contradiction Rate:      {report['contradictions']['contradiction_rate']:.2%}")

        return report

    MemoryEvalHarness._build_report = _build_report
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Usage Example: Full Evaluation Pipeline

    Let's run the evaluation harness against our synthetic dataset. The harness will:

    1. Retrieve memories for each query and compute Recall@K, Precision@K, and MRR.
    2. Generate a response from retrieved memories and score its faithfulness via Claude.
    3. Check whether temporal updates rank above superseded facts.
    4. Scan the entire store for contradictions.
    """)
    return


@app.cell
def _(MemoryEvalHarness, eval_cases, store):
    harness = MemoryEvalHarness(store, eval_cases)
    report = harness.run(k=3)
    return (report,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    We visualize the results in two panels. The left panel shows aggregate scores for each metric. The right panel breaks down recall and faithfulness per query. This makes it easy to spot which queries the memory system handles well and which ones it struggles with.
    """)
    return


@app.cell
def _(np, report):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # ── Panel 1: Aggregate metric scores ──
    metrics = [
        ("Recall@K", report["retrieval"]["mean_recall_at_k"]),
        ("Precision@K", report["retrieval"]["mean_precision_at_k"]),
        ("MRR", report["retrieval"]["mean_mrr"]),
        ("Faithfulness", report["faithfulness"]["mean_score"]),
        ("Temporal\nAccuracy", report["temporal"]["score"]),
    ]
    names = [m[0] for m in metrics]
    values = [m[1] for m in metrics]
    colors = ["#4f46e5", "#4f46e5", "#4f46e5", "#059669", "#d97706"]

    bars = axes[0].bar(names, values, color=colors, width=0.6, alpha=0.9)
    axes[0].set_ylim(0, 1.15)
    axes[0].set_ylabel("Score", fontsize=12)
    axes[0].set_title("Memory Evaluation Metrics", fontsize=13, fontweight="bold")
    axes[0].axhline(y=1.0, color="gray", linestyle="--", alpha=0.3)
    for bar, val in zip(bars, values):
        axes[0].text(
            bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.03,
            f"{val:.2f}", ha="center", fontweight="bold", fontsize=11,
        )

    # ── Panel 2: Per-query breakdown ──
    queries = [d["query"][:25] + "..." if len(d["query"]) > 25 else d["query"]
               for d in report["retrieval"]["details"]]
    recall_vals = [d["recall_at_k"] for d in report["retrieval"]["details"]]
    faith_vals = [d["score"] for d in report["faithfulness"]["details"]]

    x = np.arange(len(queries))
    width = 0.3
    axes[1].barh(x - width / 2, recall_vals, width, label="Recall@K", color="#4f46e5", alpha=0.85)
    axes[1].barh(x + width / 2, faith_vals, width, label="Faithfulness", color="#059669", alpha=0.85)
    axes[1].set_yticks(x)
    axes[1].set_yticklabels(queries, fontsize=8)
    axes[1].set_xlim(0, 1.15)
    axes[1].set_xlabel("Score", fontsize=11)
    axes[1].set_title("Per-Query Breakdown", fontsize=13, fontweight="bold")
    axes[1].legend(fontsize=9, loc="lower right")
    axes[1].axvline(x=1.0, color="gray", linestyle="--", alpha=0.3)

    plt.tight_layout()
    plt.show()

    # Print contradiction summary
    if report["contradictions"]["contradictions"]:
        print(f"\n\u26a0 {report['contradictions']['n_found']} contradiction(s) detected:")
        for c in report["contradictions"]["contradictions"]:
            print(f"  {c['id_a']} \u2194 {c['id_b']}: {c.get('explanation', '')}")
    else:
        print("\n\u2713 No contradictions detected")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Let's dig into the per-query faithfulness scores. For each query, we see the response the agent generated, the judge's reasoning, and any unsupported claims. This detail helps you understand where faithfulness breaks down.
    """)
    return


@app.cell
def _(report):
    # ── Inspect individual faithfulness results ──

    print("=== Per-Query Faithfulness Detail ===\n")
    for detail in report["faithfulness"]["details"]:
        score = detail["score"]
        icon = "\u2713" if score >= 0.8 else "\u2717"
        print(f"{icon} [{score:.2f}] {detail['query']}")
        print(f"  Response: {detail['response'][:120]}...")
        print(f"  Reasoning: {detail['reasoning']}")
        if detail["unsupported"]:
            for claim in detail["unsupported"]:
                print(f"  \u26a0 Unsupported: {claim}")
        print()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Discussion & Tradeoffs

    ### Strengths
    - **Systematic over anecdotal.** Quantitative metrics replace "it seems to work" with measurable scores. Regression testing becomes possible as you iterate on your memory system.
    - **Metric decomposition.** Separating retrieval quality, faithfulness, temporal accuracy, and contradictions lets you pinpoint *where* your system fails, not only *that* it fails.
    - **LLM-as-judge scales.** Automated faithfulness and contradiction scoring runs at any scale, unlike manual review. Studies show LLM judges correlate well with human ratings when properly prompted.
    - **Reusable eval datasets.** Once built, eval datasets serve as regression tests across memory system versions, retrieval algorithm changes, and model upgrades.

    ### Weaknesses
    - **Ground-truth labels are expensive.** Creating eval datasets with known-relevant memory IDs requires manual annotation. Synthetic datasets (like ours) may not reflect real-world distributions.
    - **LLM-as-judge has biases.** The judge model may be lenient, inconsistent, or share blind spots with the generation model. Cross-model judging and calibration help but don't eliminate this.
    - **Keyword retrieval limits.** Our `SimpleMemoryStore` uses keyword overlap, which misses semantic matches. Production systems should evaluate against embedding-based or hybrid retrieval.
    - **Contradiction detection is noisy.** The LLM may flag legitimate updates (e.g., job change) as contradictions, or miss subtle logical conflicts. Threshold tuning is needed.
    - **No downstream task evaluation.** We measure retrieval and faithfulness in isolation. A complete eval would also measure end-to-end task success: does better memory lead to better agent outcomes?

    ### Extending the Harness

    | Extension | Description |
    |-----------|-------------|
    | **Embedding-based retrieval** | Replace keyword overlap with vector similarity for more realistic evaluation |
    | **Human-eval protocol** | Add human ratings alongside LLM-as-judge and measure inter-annotator agreement |
    | **Coverage metric** | Given a conversation, what fraction of extractable facts end up in the memory store? |
    | **Latency tracking** | Measure retrieval and generation latency (response time) alongside quality metrics |
    | **A/B comparison** | Run two memory configurations on the same eval set and compare with statistical tests |
    | **Staleness scoring** | Beyond temporal accuracy, measure how often the agent uses outdated information in responses |
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Further Reading

    - [RAGAS: Evaluation framework for RAG pipelines](https://docs.ragas.io?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques) - Industry-standard metrics for retrieval-augmented generation
    - [Maharana et al., "Evaluating Very Long-Term Conversational Memory of LLM Agents" (2024)](https://arxiv.org/abs/2402.17753) - LoCoMo benchmark for long-term conversational memory
    - [Wu et al., "LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory" (2024)](https://arxiv.org/abs/2410.10813) - Multi-session memory evaluation benchmark
    - [Zheng et al., "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena" (2023)](https://arxiv.org/abs/2306.05685) - Foundational study on using LLMs as automated evaluators
    - [Anthropic: Building Conversational AI](https://docs.anthropic.com/en/docs/build-with-claude/conversational-ai?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques) - Multi-turn conversation patterns with Claude
    - [LangSmith Evaluation](https://docs.smith.langchain.com?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques) - Production evaluation tooling for LLM applications

    ---

    *← Previous: [27 - Zep Memory](../27_zep_memory/) · Next: [29 - Memory Benchmarks (LoCoMo)](../29_memory_benchmarks_LoCoMo/) →*
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 🧪 Try It Yourself

    Three small challenges to deepen your understanding. Each should take 10-30 minutes.

    ### Challenge 1: Custom domain test suite
    Write 10 QA pairs for a domain you care about (e.g., cooking recipes, project management, travel planning). Create `MemoryRecord` entries as ground truth. Run them through `MemoryEvalHarness` with `SimpleMemoryStore` and review the per-question scores.

    ### Challenge 2: Metric correlation analysis
    Run the evaluation harness on 20 questions and collect all metric scores (Recall@K, Precision@K, MRR, token F1, ROUGE-L, `FaithfulnessJudge` score). Compute pairwise Pearson correlation between metrics. Identify which automated metrics best predict the LLM judge score.

    ### Challenge 3: Head-to-head system comparison
    Implement a second retrieval backend (e.g., embedding-based search from 06 Vector Store Memory) with the same interface as `SimpleMemoryStore`. Run both backends through the same `MemoryEvalHarness` test suite. Compare their scores across all metrics and discuss which retrieval approach wins on which question types.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--28-memory-evaluation--memory-evaluation)
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
