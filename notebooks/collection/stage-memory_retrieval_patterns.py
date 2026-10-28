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
    # Memory Retrieval Patterns

    > **A memory system is only as good as its ability to surface the right information at the right time.**

    Think of a librarian handling a research question. They don't search one catalog. They check the title index for exact matches, browse the shelves for related topics, and ask a colleague for less obvious connections. Each method catches things the others miss. Combining them gives the best answer.

    Storing memories is the easy part. The hard part is retrieval: finding the right memories when the agent needs them. A naive approach works like this. Embed the query (convert it into numbers that capture meaning). Run cosine similarity against all stored memories. Return the top-K results. This works for straightforward cases but breaks down in practice.

    Pure semantic search misses exact keyword matches that matter in technical domains. It returns repetitive results when multiple memories say similar things. It has no way to distinguish highly relevant results from merely related ones when the candidate pool is large.

    **Memory retrieval patterns** are the strategies and algorithms that solve these problems. They draw from decades of information retrieval research. In this notebook, you will build a multi-stage retrieval pipeline from scratch. It combines semantic search, BM25 keyword matching, score fusion, re-ranking, and diversity filtering.

    **By the end you will understand:**
    - How to combine embedding search with keyword search for better recall.
    - How Reciprocal Rank Fusion merges ranked lists from different sources.
    - How MMR (Maximal Marginal Relevance) prevents repetitive results.
    - How HyDE (Hypothetical Document Embeddings) improves query matching.
    - When each pattern helps and when it hurts.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Key Concepts

    - **Embedding**: A list of numbers (a vector) that captures the meaning of a piece of text. Similar meanings produce similar vectors. We use an embedding model to convert text into these vectors.

    - **Cosine similarity**: A measure of how similar two vectors are. It ranges from -1 (opposite) to 1 (identical). For normalized embeddings, cosine similarity equals the dot product.

    - **BM25**: A keyword-matching algorithm from information retrieval. BM25 stands for "Best Matching 25." It scores documents based on term frequency (how often a word appears), inverse document frequency (how rare the word is across all documents), and document length.

    - **Hybrid retrieval**: Running both semantic (embedding-based) and lexical (keyword-based) search, then combining their results. This catches both meaning-based matches and exact keyword matches.

    - **Reciprocal Rank Fusion (RRF)**: A method to merge multiple ranked lists into one. For each document, RRF computes `score = sum(1 / (k + rank))` across all lists. Documents that rank well in multiple sources get the best combined scores.

    - **Maximal Marginal Relevance (MMR)**: An algorithm that selects results by balancing relevance against diversity. At each step, it picks the candidate most relevant to the query but least similar to already-selected results. The formula: `MMR = lambda * sim(doc, query) - (1 - lambda) * max(sim(doc, selected))`.

    - **Cross-encoder re-ranking**: A second-stage model that takes a (query, document) pair as input and produces a precise relevance score. Much more accurate than embedding similarity alone, but too slow for searching large collections. You apply it only to a small candidate set.

    - **HyDE (Hypothetical Document Embeddings)**: A query transformation technique. You ask an LLM to generate a hypothetical answer to the query. Then you embed that answer and search for similar documents. This bridges the vocabulary gap between short queries and longer stored memories.

    - **Token**: A word-piece the LLM processes internally. Roughly 1 token per 4 characters in English. Context windows are measured in tokens.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Architecture

    The retrieval pipeline works as a multi-stage funnel. Each stage narrows the candidate set while increasing quality.

    <p align="center">
      <img src="../../images/diagrams/20_memory_retrieval_patterns.svg" alt="Memory Retrieval Patterns Architecture" width="720"/>
    </p>

    **Data flow:** The query enters at the left. An optional query transformer (HyDE or expansion) rewrites it. The transformed query goes to two indices in parallel: a Semantic Index (embedding-based search) and a BM25 Index (keyword search). Score Fusion (Reciprocal Rank Fusion) combines both ranked lists into one. A metadata filter narrows candidates by time range, memory type, or source. The Re-ranker (a cross-encoder) re-scores the remaining candidates with higher precision. Finally, MMR selects the top-K results while maximizing diversity. These results enter the agent's context window.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Setup

    Install dependencies. We use `openai` for embeddings and chat, `rank_bm25` for lexical search, `numpy` for vector math, and `sentence-transformers` for the cross-encoder re-ranker.
    """)
    return


@app.cell
def _():
    # '%pip install -q openai python-dotenv rank_bm25 numpy sentence-transformers' command supported automatically in marimo
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Import libraries and configure the API client. You need an `OPENAI_API_KEY` in your `.env` file.
    """)
    return


@app.cell
def _():
    import os
    import math
    import json
    import hashlib
    from dataclasses import dataclass, field
    from typing import Optional

    import numpy as np
    from dotenv import load_dotenv
    from openai import OpenAI
    from rank_bm25 import BM25Okapi
    from sentence_transformers import CrossEncoder

    load_dotenv()

    client = OpenAI()  # reads OPENAI_API_KEY from environment
    assert os.getenv("OPENAI_API_KEY"), "Set OPENAI_API_KEY in your .env file"

    EMBEDDING_MODEL = "text-embedding-3-small"
    CHAT_MODEL = "gpt-4o-mini"
    CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    return (
        BM25Okapi,
        CHAT_MODEL,
        CROSS_ENCODER_MODEL,
        CrossEncoder,
        EMBEDDING_MODEL,
        Optional,
        client,
        dataclass,
        field,
        hashlib,
        np,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Implementation

    We will build the retrieval pipeline step by step. Each piece is a standalone component. At the end, we wire them together into a single `HybridRetriever` class.

    ### Step 1: Memory Store

    First, we need a data structure for memories and a store that holds them.
    """)
    return


@app.cell
def _(Optional, dataclass, field, hashlib, np):
    @dataclass
    class Memory:
        """A single memory entry with text, embedding, and metadata."""
        text: str
        memory_id: str = ""
        embedding: Optional[np.ndarray] = field(default=None, repr=False)
        metadata: dict = field(default_factory=dict)
        timestamp: float = 0.0

        def __post_init__(self):
            if not self.memory_id:
                # Deterministic ID from content
                self.memory_id = hashlib.sha256(self.text.encode()).hexdigest()[:12]


    class MemoryStore:
        """In-memory store that keeps memories with their embeddings."""

        def __init__(self):
            self.memories: list[Memory] = []

        def add(self, text: str, metadata: dict | None = None, timestamp: float = 0.0) -> Memory:
            mem = Memory(text=text, metadata=metadata or {}, timestamp=timestamp)
            self.memories.append(mem)
            return mem

        def compute_embeddings(self, embed_fn):
            """Compute embeddings for all memories that lack one."""
            texts_to_embed = []
            indices = []
            for i, mem in enumerate(self.memories):
                if mem.embedding is None:
                    texts_to_embed.append(mem.text)
                    indices.append(i)

            if texts_to_embed:
                embeddings = embed_fn(texts_to_embed)
                for idx, emb in zip(indices, embeddings):
                    self.memories[idx].embedding = emb

        def __len__(self) -> int:
            return len(self.memories)

        def __repr__(self) -> str:
            return f"MemoryStore({len(self.memories)} memories)"

    return Memory, MemoryStore


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 2: Embedding Helper

    We need a function to convert text into embeddings using the OpenAI API. This function handles batching for efficiency.
    """)
    return


@app.cell
def _(EMBEDDING_MODEL, client, np):
    def get_embeddings(texts: list[str], model: str = EMBEDDING_MODEL) -> list[np.ndarray]:
        """Get embeddings for a list of texts using the OpenAI API."""
        response = client.embeddings.create(model=model, input=texts)
        return [np.array(item.embedding, dtype=np.float32) for item in response.data]


    def get_embedding(text: str, model: str = EMBEDDING_MODEL) -> np.ndarray:
        """Get a single embedding."""
        return get_embeddings([text], model=model)[0]

    return get_embedding, get_embeddings


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 3: Semantic Search

    Imagine a bookstore that organizes books by topic on a map. Similar books sit close together. To find relevant books, you locate your query on the map and grab the nearest ones. Semantic search with embeddings works the same way.

    Cosine similarity measures the angle between two vectors. A value of 1.0 means identical direction (same meaning). A value of 0.0 means no relationship.
    """)
    return


@app.cell
def _(Memory, np):
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))


    def semantic_search(
        query_embedding: np.ndarray,
        memories: list[Memory],
        top_k: int = 10,
    ) -> list[tuple[Memory, float]]:
        """Rank memories by cosine similarity to the query embedding.

        Returns a list of (memory, score) tuples sorted by descending score.
        """
        scored = []
        for mem in memories:
            if mem.embedding is not None:
                score = cosine_similarity(query_embedding, mem.embedding)
                scored.append((mem, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    return cosine_similarity, semantic_search


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 4: BM25 Lexical Search

    Think of a card catalog in an old library. You look up an exact title or keyword, and the catalog points you to the right shelf. BM25 works this way. It scores documents based on how well their words match the query words.

    BM25 excels where embeddings struggle: rare technical terms, acronyms, and exact phrases. The `rank_bm25` library gives us a ready-made implementation.
    """)
    return


@app.cell
def _(BM25Okapi, Memory):
    class BM25Index:
        """Wraps rank_bm25 for lexical search over memories."""

        def __init__(self, memories: list[Memory]):
            self.memories = memories
            # Tokenize by splitting on whitespace and lowercasing
            tokenized = [mem.text.lower().split() for mem in memories]
            self.bm25 = BM25Okapi(tokenized)

        def search(self, query: str, top_k: int = 10) -> list[tuple[Memory, float]]:
            """Search using BM25 scoring. Returns (memory, score) pairs."""
            query_tokens = query.lower().split()
            scores = self.bm25.get_scores(query_tokens)

            # Pair memories with scores and sort descending
            scored = [(self.memories[i], float(scores[i])) for i in range(len(self.memories))]
            scored.sort(key=lambda x: x[1], reverse=True)
            return scored[:top_k]

    return (BM25Index,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 5: Reciprocal Rank Fusion (RRF)

    You asked two friends for restaurant recommendations. Friend A gives you a ranked list. Friend B gives you a different ranked list. Some restaurants appear on both lists, some on only one. How do you combine them?

    RRF solves this. For each item, it sums `1 / (k + rank)` across all lists. Items ranked highly by multiple sources get the best combined scores. The constant `k` (typically 60) prevents top-ranked items from dominating too heavily.
    """)
    return


@app.cell
def _(Memory):
    def reciprocal_rank_fusion(
        *ranked_lists: list[tuple[Memory, float]],
        k: int = 60,
    ) -> list[tuple[Memory, float]]:
        """Merge multiple ranked lists using Reciprocal Rank Fusion.

        Args:
            ranked_lists: Each list contains (memory, score) tuples in rank order.
            k: Smoothing constant. Higher values reduce the impact of rank position.

        Returns:
            Fused list of (memory, rrf_score) sorted descending.
        """
        rrf_scores: dict[str, float] = {}
        memory_lookup: dict[str, Memory] = {}

        for ranked_list in ranked_lists:
            for rank, (mem, _score) in enumerate(ranked_list):
                rrf_scores[mem.memory_id] = rrf_scores.get(mem.memory_id, 0.0) + 1.0 / (k + rank + 1)
                memory_lookup[mem.memory_id] = mem

        # Sort by fused score descending
        fused = [(memory_lookup[mid], score) for mid, score in rrf_scores.items()]
        fused.sort(key=lambda x: x[1], reverse=True)
        return fused

    return (reciprocal_rank_fusion,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 6: Cross-Encoder Re-ranking

    Picture two stages of a job interview. The first stage (resume screening) is fast but rough. The second stage (in-person interview) is slow but accurate. Re-ranking works the same way.

    The first stage (semantic search or BM25) is fast because it compares pre-computed representations. The cross-encoder re-ranker is slow because it reads the query and document together, word by word. But this joint reading produces much more accurate relevance scores.

    We use the `sentence-transformers` library to load a cross-encoder model. It scores each (query, document) pair on a relevance scale.
    """)
    return


@app.cell
def _(CROSS_ENCODER_MODEL, CrossEncoder, Memory):
    class Reranker:
        """Cross-encoder re-ranker using sentence-transformers."""

        def __init__(self, model_name: str = CROSS_ENCODER_MODEL):
            self.model = CrossEncoder(model_name)

        def rerank(
            self,
            query: str,
            candidates: list[tuple[Memory, float]],
            top_k: int | None = None,
        ) -> list[tuple[Memory, float]]:
            """Re-score candidates with the cross-encoder.

            Args:
                query: The search query.
                candidates: List of (memory, initial_score) from earlier stages.
                top_k: Return only this many results. None returns all.

            Returns:
                Re-ranked list of (memory, cross_encoder_score).
            """
            if not candidates:
                return []

            # Build input pairs for the cross-encoder
            pairs = [(query, mem.text) for mem, _ in candidates]
            scores = self.model.predict(pairs)

            # Pair memories with new scores
            reranked = [(candidates[i][0], float(scores[i])) for i in range(len(candidates))]
            reranked.sort(key=lambda x: x[1], reverse=True)

            if top_k is not None:
                reranked = reranked[:top_k]
            return reranked

    return (Reranker,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 7: Maximal Marginal Relevance (MMR)

    Imagine making a playlist. You would not want five sad ballads in a row, even if they are all great songs. You want variety. MMR applies this same idea to search results.

    At each step, MMR picks the candidate most relevant to the query but least similar to what we already selected. The `lambda_param` controls the balance. A value of 1.0 means "pick the most relevant, ignore diversity." A value of 0.0 means "pick the most different from what we already have." Values around 0.5-0.7 work well in practice.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The greedy selection loop is the core of MMR. It picks one result at a time. Each pick maximizes `lambda * relevance - (1 - lambda) * similarity_to_already_picked`. We extract it as a helper so both functions stay short and readable.
    """)
    return


@app.cell
def _(Memory, cosine_similarity, np):
    def _mmr_greedy_select(
        candidates: list[tuple[Memory, float]],
        query_embedding: np.ndarray,
        top_k: int,
        min_score: float,
        score_range: float,
        lambda_param: float,
    ) -> list[tuple[Memory, float]]:
        """Greedy selection loop for MMR.

        At each step, pick the candidate with the highest MMR score:
        lambda * relevance - (1 - lambda) * max_similarity_to_selected.
        """
        remaining = list(range(len(candidates)))
        selected_embeddings: list[np.ndarray] = []
        result = []

        for _ in range(min(top_k, len(candidates))):
            best_idx = -1
            best_mmr = -float("inf")

            for idx in remaining:
                mem, raw_score = candidates[idx]
                if mem.embedding is None:
                    continue

                # Relevance component: normalized score
                relevance = (raw_score - min_score) / score_range

                # Diversity component: max similarity to any already-selected item
                if selected_embeddings:
                    similarities = [
                        cosine_similarity(mem.embedding, sel_emb)
                        for sel_emb in selected_embeddings
                    ]
                    max_sim = max(similarities)
                else:
                    max_sim = 0.0

                mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim

                if mmr_score > best_mmr:
                    best_mmr = mmr_score
                    best_idx = idx

            if best_idx == -1:
                break

            mem, score = candidates[best_idx]
            result.append((mem, best_mmr))
            selected_embeddings.append(mem.embedding)
            remaining.remove(best_idx)

        return result

    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The main `mmr_selection` function normalizes scores to a 0-1 range, then delegates to the greedy loop. Callers only interact with this function.
    """)
    return


@app.cell
def _(Memory, np):
    def mmr_selection(
        query_embedding: np.ndarray,
        candidates: list[tuple[Memory, float]],
        top_k: int = 5,
        lambda_param: float = 0.7,
    ) -> list[tuple[Memory, float]]:
        """Select results using Maximal Marginal Relevance.

        Balances relevance to the query against diversity among selected results.

        Args:
            query_embedding: The embedding vector for the query.
            candidates: Pre-scored (memory, relevance_score) pairs.
            top_k: Number of results to select.
            lambda_param: Balance between relevance (1.0) and diversity (0.0).

        Returns:
            Selected (memory, mmr_score) pairs.
        """
        if not candidates:
            return []

        # Normalize relevance scores to [0, 1]
        scores = [s for _, s in candidates]
        max_score = max(scores) if scores else 1.0
        min_score = min(scores) if scores else 0.0
        score_range = max_score - min_score if max_score != min_score else 1.0

        return _mmr_greedy_select(
            candidates, query_embedding, top_k,
            min_score, score_range, lambda_param,
        )

    return (mmr_selection,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 8: HyDE Query Transformation

    Think of translating between languages. Your query is in "question language" but your documents are in "answer language." HyDE bridges the gap by asking an LLM to write a hypothetical answer. Then it searches using that answer instead of the question.

    This works because the hypothetical answer shares vocabulary and structure with real stored memories. Even if the hypothetical answer is wrong, its embedding lands closer to relevant documents than the original short query would.
    """)
    return


@app.cell
def _(CHAT_MODEL, client):
    def hyde_transform(query: str) -> str:
        """Generate a hypothetical document (answer) for the query using an LLM.

        The hypothetical answer is then embedded for retrieval instead of the
        raw query. This bridges the vocabulary gap between questions and documents.
        """
        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant. Given a question, write a short "
                        "paragraph (3-4 sentences) that would be a good answer. "
                        "Write as if this answer exists in a knowledge base. "
                        "State facts directly. Do not hedge."
                    ),
                },
                {"role": "user", "content": query},
            ],
            max_tokens=200,
            temperature=0.7,
        )
        return response.choices[0].message.content

    return (hyde_transform,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 9: Full Hybrid Retriever

    Now we wire all the components into a single class. The `retrieve` method runs the full pipeline: optional HyDE transform, parallel semantic + BM25 search, RRF fusion, cross-encoder re-ranking, and MMR diversity selection.
    """)
    return


@app.cell
def _(BM25Index, MemoryStore, Reranker, get_embeddings):
    class HybridRetriever:
        """Multi-stage retrieval pipeline combining semantic and lexical search.

        Pipeline stages:
        1. Query transformation (optional HyDE)
        2. Parallel semantic + BM25 retrieval
        3. Reciprocal Rank Fusion
        4. Cross-encoder re-ranking
        5. MMR diversity selection
        """

        def __init__(self, store: MemoryStore, use_reranker: bool = True):
            self.store = store
            self.bm25_index: BM25Index | None = None
            self.reranker = Reranker() if use_reranker else None

        def build_indices(self):
            """Compute embeddings and build the BM25 index."""
            self.store.compute_embeddings(get_embeddings)
            self.bm25_index = BM25Index(self.store.memories)
            print(f"Built indices over {len(self.store)} memories.")

    return (HybridRetriever,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `retrieve` method runs the full pipeline. It chains all stages together: optional HyDE transform, parallel semantic and BM25 search, RRF fusion, cross-encoder re-ranking, and MMR diversity selection. We attach it to the class separately to keep each cell focused on one piece.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    `_retrieve_candidates` handles the first three pipeline stages: optional HyDE transform, parallel semantic and BM25 search, and Reciprocal Rank Fusion. It returns the fused candidate list along with the query embedding.
    """)
    return


@app.cell
def _(
    HybridRetriever,
    Memory,
    get_embedding,
    hyde_transform,
    reciprocal_rank_fusion,
    semantic_search,
):
    def _retrieve_candidates(
        self,
        query: str,
        initial_k: int,
        use_hyde: bool,
    ) -> tuple[list[tuple[Memory, float]], "np.ndarray", str]:
        """Stages 1-3: query transform, parallel retrieval, and RRF fusion.

        Returns:
            Tuple of (fused_results, query_embedding, search_text).
        """
        # Stage 1: Query transformation
        search_text = query
        if use_hyde:
            hypothetical_answer = hyde_transform(query)
            search_text = hypothetical_answer

        # Stage 2: Parallel retrieval
        query_embedding = get_embedding(search_text)
        semantic_results = semantic_search(
            query_embedding, self.store.memories, top_k=initial_k
        )

        # BM25 always uses the original query (keywords matter)
        if self.bm25_index:
            bm25_results = self.bm25_index.search(query, top_k=initial_k)
        else:
            bm25_results = []

        # Stage 3: Reciprocal Rank Fusion
        if bm25_results:
            fused = reciprocal_rank_fusion(semantic_results, bm25_results, k=60)
        else:
            fused = semantic_results

        return fused, query_embedding, search_text

    HybridRetriever._retrieve_candidates = _retrieve_candidates
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `retrieve` method orchestrates the full pipeline. It calls `_retrieve_candidates` for stages 1-3, then applies cross-encoder re-ranking (stage 4) and MMR diversity selection (stage 5).
    """)
    return


@app.cell
def _(HybridRetriever, Memory, get_embedding, mmr_selection):
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        use_hyde: bool = False,
        use_reranker: bool = True,
        use_mmr: bool = True,
        lambda_param: float = 0.7,
        initial_k_multiplier: int = 4,
    ) -> list[tuple[Memory, float]]:
        """Run the full retrieval pipeline.

        Args:
            query: The search query.
            top_k: Number of final results.
            use_hyde: Whether to apply HyDE query transformation.
            use_reranker: Whether to apply cross-encoder re-ranking.
            use_mmr: Whether to apply MMR diversity filtering.
            lambda_param: MMR relevance-diversity balance (0.0 to 1.0).
            initial_k_multiplier: How many candidates to fetch in the first
                stage (as a multiple of top_k).

        Returns:
            List of (memory, score) tuples.
        """
        initial_k = top_k * initial_k_multiplier

        # Stages 1-3: candidates via semantic + BM25 + fusion
        fused, query_embedding, search_text = self._retrieve_candidates(
            query, initial_k, use_hyde,
        )

        # Stage 4: Cross-encoder re-ranking
        rerank_candidates = fused[: top_k * 3]
        if use_reranker and self.reranker and rerank_candidates:
            reranked = self.reranker.rerank(
                query, rerank_candidates, top_k=top_k * 2
            )
        else:
            reranked = rerank_candidates

        # Stage 5: MMR diversity selection
        if use_mmr:
            if use_hyde:
                original_query_embedding = get_embedding(query)
            else:
                original_query_embedding = query_embedding
            final = mmr_selection(
                original_query_embedding, reranked,
                top_k=top_k, lambda_param=lambda_param,
            )
        else:
            final = reranked[:top_k]

        return final

    HybridRetriever.retrieve = retrieve
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Example Run

    Let's test the retrieval pipeline with a realistic memory collection. We populate the store with memories about a software project, then run queries that test different retrieval strengths.
    """)
    return


@app.cell
def _(MemoryStore):
    # Create a memory store with diverse project memories
    store = MemoryStore()
    project_memories = ['We chose PostgreSQL as our primary database because it handles JSON well and supports full-text search.', 'The team adopted FastAPI for the backend REST API. It has built-in OpenAPI docs and async support.', 'We use Redis for caching API responses. Cache TTL is set to 300 seconds for most endpoints.', 'Authentication uses JWT tokens with a 24-hour expiry. Refresh tokens last 30 days.', 'The frontend is built with React 18 and TypeScript. We use Zustand for state management.', 'Sprint retrospective on March 15: the team agreed to write integration tests before merging PRs.', 'Alice leads the backend team. Bob handles DevOps. Carol manages the frontend.', 'We deploy to AWS using Terraform. The CI/CD pipeline runs on GitHub Actions.', 'Code reviews require two approvals before merging to the main branch.', 'The on-call rotation is weekly: Alice, Bob, Carol, then Dave.', 'Bug: the /users endpoint returns a 500 error when the email field contains unicode characters.', 'Incident on April 2: Redis cache went down for 40 minutes. Fallback to direct DB queries worked.', 'Memory leak in the WebSocket handler was traced to unclosed connections in the event loop.', 'Performance issue: the search endpoint takes 3 seconds for queries over 100 characters.', 'The message queue uses RabbitMQ. Each microservice has its own exchange and dead-letter queue.', 'Database migrations run automatically on deployment using Alembic.', 'Logs are shipped to Elasticsearch via Fluentd. Kibana dashboards show error rates and latency.', 'The recommendation engine uses cosine similarity over user-item embeddings stored in Pinecone.', 'Product meeting April 10: we decided to prioritize the search feature over the notification system.', 'Architecture review: proposed moving from REST to gRPC for internal service communication.']
    for _i, text in enumerate(project_memories):
        store.add(text, metadata={'source': 'project_log', 'index': _i}, timestamp=float(_i))  # Technical decisions
    print(f'Added {len(store)} memories to the store.')  # Team and process  # Bug reports and incidents  # Architecture notes  # Meeting notes
    return (store,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Build the indices. This computes embeddings for all memories and creates the BM25 index.
    """)
    return


@app.cell
def _(HybridRetriever, store):
    retriever = HybridRetriever(store, use_reranker=True)
    retriever.build_indices()
    return (retriever,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Query 1: Semantic Query

    Let's search for something that requires understanding meaning, not exact keyword matching.
    """)
    return


@app.cell
def _(retriever):
    _query = 'What database technology do we use and why?'
    _results = retriever.retrieve(_query, top_k=3, use_hyde=False, use_reranker=True, use_mmr=True)
    print(f"Query: '{_query}'\n")
    for _i, (_mem, _score) in enumerate(_results):
        print(f'  {_i + 1}. [score={_score:.4f}] {_mem.text}')
        print()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Query 2: Keyword-Heavy Query

    This query uses exact terms. BM25 should contribute more than semantic search here.
    """)
    return


@app.cell
def _(retriever):
    _query = 'Redis cache TTL'
    _results = retriever.retrieve(_query, top_k=3, use_hyde=False, use_reranker=True, use_mmr=True)
    print(f"Query: '{_query}'\n")
    for _i, (_mem, _score) in enumerate(_results):
        print(f'  {_i + 1}. [score={_score:.4f}] {_mem.text}')
        print()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Comparing Retrieval Strategies

    Let's run the same query through different pipeline configurations to see how each component contributes.
    """)
    return


@app.cell
def _(retriever):
    _query = 'What went wrong in production recently?'
    configurations = [('Semantic only', dict(use_hyde=False, use_reranker=False, use_mmr=False)), ('BM25 + Semantic (RRF)', dict(use_hyde=False, use_reranker=False, use_mmr=False)), ('+ Re-ranking', dict(use_hyde=False, use_reranker=True, use_mmr=False)), ('+ MMR diversity', dict(use_hyde=False, use_reranker=True, use_mmr=True, lambda_param=0.5)), ('+ HyDE', dict(use_hyde=True, use_reranker=True, use_mmr=True, lambda_param=0.5))]
    print(f"Query: '{_query}'\n")
    print('=' * 90)
    for name, config in configurations:
        _results = retriever.retrieve(_query, top_k=3, **config)
        print(f'\n[{name}]')
        for _i, (_mem, _score) in enumerate(_results):
            _preview = _mem.text[:90] + ('...' if len(_mem.text) > 90 else '')
            print(f'  {_i + 1}. [{_score:.4f}] {_preview}')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### The Effect of MMR Lambda

    Let's see how `lambda_param` changes results. Lower lambda means more diversity. Higher lambda means more relevance focus.
    """)
    return


@app.cell
def _(retriever):
    _query = 'Tell me about our infrastructure and deployment'
    lambdas = [0.3, 0.5, 0.7, 0.9]
    print(f"Query: '{_query}'\n")
    for lam in lambdas:
        _results = retriever.retrieve(_query, top_k=4, use_reranker=True, use_mmr=True, lambda_param=lam)
        print(f'lambda={lam}:')
        for _i, (_mem, _score) in enumerate(_results):
            _preview = _mem.text[:85] + ('...' if len(_mem.text) > 85 else '')
            print(f'  {_i + 1}. {_preview}')
        print()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Using Retrieved Memories in a Chat

    Here is how you feed retrieved memories into an LLM call. The retriever finds relevant context, and the LLM uses it to answer.
    """)
    return


@app.cell
def _(CHAT_MODEL, HybridRetriever, client, retriever):
    def answer_with_memory(query: str, retriever: HybridRetriever, top_k: int = 5) -> str:
        """Retrieve relevant memories and use them to answer a query."""
        results = retriever.retrieve(
            query, top_k=top_k, use_hyde=False, use_reranker=True, use_mmr=True
        )

        # Format memories as context
        context_parts = []
        for i, (mem, score) in enumerate(results):
            context_parts.append(f"[Memory {i+1}] {mem.text}")
        context = "\n".join(context_parts)

        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful project assistant. Answer the user's question "
                        "based on the retrieved memories below. If the memories do not contain "
                        "enough information, say so. Keep your answer concise (2-4 sentences).\n\n"
                        f"Retrieved memories:\n{context}"
                    ),
                },
                {"role": "user", "content": query},
            ],
            max_tokens=300,
        )
        return response.choices[0].message.content


    # Test with a few questions
    questions = [
        "Who should I talk to about the CI/CD pipeline?",
        "What happened with the Redis incident?",
        "How does our search feature work?",
    ]

    for q in questions:
        print(f"Q: {q}")
        answer = answer_with_memory(q, retriever)
        print(f"A: {answer}\n")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Tradeoffs

    ### When These Patterns Help

    - **Hybrid retrieval catches what either approach misses alone.** Semantic search handles paraphrases and meaning. BM25 handles exact terms, acronyms, and rare words. Together, recall improves across query types.
    - **MMR prevents repetitive results.** Without diversity filtering, you often get five variations of the same memory. MMR ensures the agent sees a broader view of its stored knowledge.
    - **Re-ranking improves precision in the top results.** The cross-encoder reads query and document together. It catches subtle relevance signals that embedding similarity misses.
    - **HyDE helps with short or ambiguous queries.** When the query does not share vocabulary with stored memories, a hypothetical answer bridges the gap.

    ### When These Patterns Hurt

    - **Latency increases with each pipeline stage.** Embedding lookup takes milliseconds. BM25 is fast too. But the cross-encoder re-ranker adds 50-200ms depending on candidate count. HyDE adds a full LLM call (200-1000ms). For real-time chat, you may need to skip stages.
    - **Complexity grows.** Each component has parameters to tune: RRF's `k`, MMR's `lambda`, the number of candidates passed to each stage. More moving parts means more chances for misconfiguration.
    - **Small memory stores see little benefit.** If you have fewer than 50 memories, a single semantic search with cosine similarity works well enough. The multi-stage pipeline shines when the candidate pool is large (hundreds to thousands of memories).
    - **HyDE can mislead on factual queries.** If the LLM generates a wrong hypothetical answer, the embedding search finds documents similar to that wrong answer. HyDE works best for open-ended queries, not precise factual lookups.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Further Reading

    - Robertson, S., & Zaragoza, H. (2009). ["The Probabilistic Relevance Framework: BM25 and Beyond."](https://doi.org/10.1561/1500000019) *Foundations and Trends in Information Retrieval*, 3(4), 333-389. The definitive reference for BM25.

    - Carbonell, J., & Goldstein, J. (1998). ["The Use of MMR, Diversity-Based Reranking for Reordering Documents and Producing Summaries."](https://doi.org/10.1145/290941.291025) *ACM SIGIR*, 335-336. The original MMR paper.

    - Gao, L., et al. (2022). ["Precise Zero-Shot Dense Retrieval without Relevance Labels (HyDE)."](https://arxiv.org/abs/2212.10496) Shows that generating a hypothetical answer and embedding it improves zero-shot retrieval.

    - Ma, X., et al. (2023). ["Fine-Tuning LLaMA for Multi-Stage Text Retrieval."](https://arxiv.org/abs/2310.08319) Explores LLMs as retrievers and re-rankers in multi-stage pipelines.

    - [Sentence Transformers: Cross-Encoders](https://www.sbert.net/docs/cross_encoder/usage/usage.html) Documentation for the cross-encoder models used in the re-ranking stage.

    - [rank-bm25 on PyPI](https://pypi.org/project/rank-bm25/) The BM25 library used in this notebook for lexical search.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---

    *Previous: [19: Forgetting & Decay](../19_forgetting_and_decay/) | Next: [21: Cross-Session Memory](../21_cross_session_memory/)*
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 🧪 Try It Yourself

    Three small challenges to deepen your understanding. Each should take 10-30 minutes.

    ### Challenge 1: Fusion weight tuning
    In `reciprocal_rank_fusion()`, adjust the relative weight of semantic vs. BM25 results. Try ratios of 0.3/0.7, 0.5/0.5, and 0.7/0.3. For each setting, run 10 queries and measure MRR (Mean Reciprocal Rank). Identify which ratio works best for your data.

    ### Challenge 2: Reranker impact
    Measure Recall@10 and Precision@10 before and after applying the `Reranker`. Run 20 queries and record the position change of the top result after reranking. Compute how often reranking promotes a better result to position 1.

    ### Challenge 3: HyDE for memory retrieval
    Apply `hyde_transform()` to 10 memory queries. Compare the top-5 results from raw queries vs. HyDE-transformed queries using `semantic_search()`. Count how many additional relevant memories the HyDE approach surfaces. Test this with a vector store from 06 Vector Store Memory.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--20-memory-retrieval-patterns--memory-retrieval-patterns)
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
