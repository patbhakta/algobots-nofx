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
    # Graph Memory with Graphiti

    > **Transform conversations into a temporal knowledge graph where entities, relationships, and facts evolve over time.**

    Imagine a corkboard covered in index cards connected by colored strings. Each card represents a person, project, or concept. Each string represents a relationship: "manages," "depends on," "works with." Now imagine every string has a date tag showing when you pinned it. If a relationship changes, you don't remove the old string. You add a new one and mark the old one as outdated. That's how a **temporal knowledge graph** works.

    Most memory systems treat each stored fact as an independent point. "Alice is an engineer" lives in one spot. "Alice manages the safety team" lives in another. If you ask "Who reports to Alice's manager?", a flat memory has no way to follow that chain. A **knowledge graph** solves this. It stores information as a network of **entities** (nodes, like people and projects) connected by **relationships** (edges, like "manages" or "works on"). You can traverse those connections to answer multi-step questions.

    **Graphiti**, developed by Zep, adds a critical dimension: **temporality**. Every edge carries timestamps. The timestamps record when a relationship started, when it was last confirmed, and whether it's been invalidated. This lets the agent answer not only "What is true?" but also "What was true last week?" and "Has this fact changed?"

    In this notebook you'll build a Graphiti-backed memory system from scratch. You'll:

    1. Connect to a Neo4j graph database and initialize Graphiti.
    2. Ingest conversation episodes (timestamped dialogue turns) into the knowledge graph.
    3. Search the graph with natural-language queries.
    4. Explore temporal edges to see how facts evolve.
    5. Run community detection to find knowledge clusters.
    6. Wire the graph into an agent loop that answers relational questions.

    **By the end you'll understand:**
    - How Graphiti's ingestion pipeline extracts entities and relationships from raw text.
    - Why temporal edges matter for long-running agents.
    - When graph memory outperforms flat vector stores, and when it doesn't.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Key Concepts

    - **Knowledge graph:** A data structure that stores information as **nodes** (entities like people, projects, tools) connected by **edges** (relationships like "manages" or "depends on"). Think of it as a structured map of facts.
    - **Temporal knowledge graph:** A knowledge graph where every edge carries timestamps. You can query what was true at a specific point in time. Outdated relationships stay in the graph with invalidation markers.
    - **Episode:** A unit of input data fed into Graphiti. Typically one conversation turn or one document chunk. Each episode has a timestamp (called `reference_time`) that anchors it in time.
    - **Entity extraction:** The process where Graphiti's LLM-powered pipeline reads raw text and identifies named entities (people, organizations, tools, locations).
    - **Relationship extraction:** The same pipeline also identifies how entities relate to each other. For example, from "Alice joined the safety team," it extracts the relationship `Alice -> MEMBER_OF -> safety team`.
    - **Entity resolution:** When Graphiti finds an entity that looks like one it already knows, it merges them. "Alice" and "Dr. Alice Chen" might resolve to the same node.
    - **Graph search:** Querying the knowledge graph. Graphiti supports hybrid search that combines semantic similarity (meaning-based matching) with BM25 text retrieval (keyword-based matching).
    - **Multi-hop reasoning:** Following a chain of relationships across several nodes. For example: User -> works at -> Acme Corp -> located in -> San Francisco.
    - **Community detection:** An algorithm that finds clusters of closely connected nodes. These clusters often represent meaningful groups (like "the engineering team" or "project-related tools").
    - **Neo4j:** The graph database that stores Graphiti's data. It uses a query language called Cypher. You don't need to write Cypher directly. Graphiti handles it for you.
    - **Invalidation:** When a fact changes, Graphiti doesn't delete the old edge. It marks the old edge with an `invalid_at` timestamp and creates a new edge. This preserves history.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Architecture

    <p align="center">
      <img src="../../images/diagrams/24_graph_memory_graphiti.svg" alt="Graphiti architecture diagram" width="720"/>
    </p>

    **Data flow:**

    1. **Conversation episodes** (timestamped dialogue turns) enter Graphiti's ingestion pipeline.
    2. The **Episode Processor** passes the text to the **Entity Extractor** and **Relationship Extractor**. Both are LLM-powered.
    3. The **Entity Resolver** merges duplicates, links co-references ("she" to "Alice"), and reconciles new entities with existing nodes.
    4. New nodes and temporal edges get written to **Neo4j**. Changed relationships receive invalidation timestamps on old edges and creation timestamps on new ones.
    5. At query time, the agent uses the **Query Layer**: graph search (hybrid semantic + keyword), community detection (finding clusters), and temporal filtering (scoping results by time).
    6. Retrieved entities, relationships, and facts get injected into the agent's context window as structured text.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Setup

    You'll need three things:

    1. **A running Neo4j instance.** The easiest way is Docker: `docker run -d -p 7687:7687 -p 7474:7474 -e NEO4J_AUTH=neo4j/password neo4j:latest`
    2. **An OpenAI API key.** Graphiti uses OpenAI for entity/relationship extraction and embeddings by default.
    3. **The Python packages** listed below.

    Set these environment variables in a `.env` file:

    ```
    OPENAI_API_KEY=sk-...
    NEO4J_URI=bolt://localhost:7687
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=password
    ```
    """)
    return


@app.cell
def _():
    # '%pip install -q graphiti-core neo4j openai python-dotenv' command supported automatically in marimo
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Import the Graphiti SDK, standard library helpers, and load environment variables.
    """)
    return


@app.cell
def _():
    import os
    import asyncio
    import json
    from datetime import datetime, timezone, timedelta
    from dotenv import load_dotenv

    from graphiti_core import Graphiti
    from graphiti_core.nodes import EpisodeType, CommunityNode, EntityNode
    from graphiti_core.edges import EntityEdge

    import openai

    load_dotenv()

    assert os.getenv("OPENAI_API_KEY"), "Set OPENAI_API_KEY in your .env file"

    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
    return (
        EpisodeType,
        Graphiti,
        NEO4J_PASSWORD,
        NEO4J_URI,
        NEO4J_USER,
        datetime,
        openai,
        timezone,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Implementation

    We'll build the graph memory in four steps:

    1. **Initialize** Graphiti and connect to Neo4j.
    2. **Ingest** conversation episodes with evolving facts.
    3. **Search** the graph with natural language.
    4. **Detect communities** to find knowledge clusters.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 1: Initialize Graphiti

    Think of this step like setting up a blank corkboard. You create the board (the Neo4j database), add labels for where things go (indices and constraints), and get your pins ready (the Graphiti client).

    Graphiti needs a running Neo4j instance. `build_indices_and_constraints()` creates the database schema that Graphiti expects: indexes for fast lookups and constraints for data integrity.
    """)
    return


@app.cell
async def _(Graphiti, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER):
    async def initialize_graphiti() -> Graphiti:
        """Connect to Neo4j and prepare the graph schema."""
        graphiti = Graphiti(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        await graphiti.build_indices_and_constraints()
        print(f"Connected to Neo4j at {NEO4J_URI}")
        print("Indices and constraints are ready.")
        return graphiti

    graphiti = await initialize_graphiti()
    return (graphiti,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 2: Ingest Conversation Episodes

    Think of each episode like a diary entry. You write down what happened and when. Over time, your diary tells a story of how things changed. Graphiti reads each entry and pins new cards (entities) and strings (relationships) to the corkboard.

    We'll feed in a realistic multi-session conversation where facts evolve. Alice starts at one company, changes teams, and picks up new projects. Graphiti's pipeline will:

    - Extract entities (Alice, Anthropic, RLHF team, etc.)
    - Extract relationships ("Alice works at Anthropic", "Alice is on the RLHF team")
    - Resolve duplicates ("Alice" mentioned in different episodes maps to the same node)
    - Handle temporal changes (when Alice moves teams, the old edge gets invalidated)
    """)
    return


@app.cell
def _(datetime, timezone):
    # Realistic conversation episodes with timestamps that show facts evolving
    episodes = [
        {
            "body": "User: My name is Alice Chen. I work at Anthropic as a safety researcher.",
            "timestamp": datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            "description": "User introduction",
        },
        {
            "body": "User: My manager is Bob Martinez. We're both on the RLHF team.",
            "timestamp": datetime(2025, 1, 20, 14, 30, tzinfo=timezone.utc),
            "description": "Team structure details",
        },
        {
            "body": "User: Our team uses PyTorch and we're training a reward model on the Helios cluster.",
            "timestamp": datetime(2025, 2, 5, 9, 0, tzinfo=timezone.utc),
            "description": "Technical stack details",
        },
        {
            "body": "User: I transferred from the RLHF team to the interpretability team last week. My new manager is Carol Park.",
            "timestamp": datetime(2025, 3, 1, 11, 0, tzinfo=timezone.utc),
            "description": "Team change announcement",
        },
        {
            "body": "User: On the interpretability team, we use JAX instead of PyTorch. I'm working on a new project called Lens.",
            "timestamp": datetime(2025, 3, 10, 16, 0, tzinfo=timezone.utc),
            "description": "New team technical details",
        },
        {
            "body": "User: Bob Martinez left Anthropic. He joined OpenAI as a research lead.",
            "timestamp": datetime(2025, 4, 2, 10, 0, tzinfo=timezone.utc),
            "description": "Personnel change",
        },
    ]

    print(f"Prepared {len(episodes)} episodes spanning "
          f"{episodes[0]['timestamp'].strftime('%b %Y')} to "
          f"{episodes[-1]['timestamp'].strftime('%b %Y')}")
    return (episodes,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Now we feed each episode into Graphiti. The `add_episode` method is async. Each call triggers the full extraction pipeline: entity extraction, relationship extraction, entity resolution, and graph updates.

    **Important:** Episodes must be added one at a time, in order. Each episode builds on the context from previous ones.
    """)
    return


@app.cell
async def _(EpisodeType, episodes, graphiti):
    for i, episode in enumerate(episodes):
        result = await graphiti.add_episode(
            name=f"episode_{i:02d}",
            episode_body=episode["body"],
            source=EpisodeType.message,
            source_description=episode["description"],
            reference_time=episode["timestamp"],
        )
        ts = episode["timestamp"].strftime("%Y-%m-%d")
        print(f"Ingested episode {i} ({ts}): {episode['body'][:60]}...")

    print(f"\nAll {len(episodes)} episodes ingested.")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 3: Search the Knowledge Graph

    Think of graph search like asking a librarian who has read every book and remembers how they connect. You ask a natural-language question. The librarian finds the relevant index cards and follows the strings between them.

    Graphiti's `search()` method performs a hybrid search. It combines:
    - **Semantic similarity:** finds edges whose meaning is close to your query.
    - **BM25 text retrieval:** finds edges that share keywords with your query.

    The results are `EntityEdge` objects. Each edge has a `fact` field (a natural-language statement of the relationship) and temporal fields (`valid_at`, `invalid_at`).
    """)
    return


@app.cell
def _(Graphiti):
    async def search_and_display(graphiti_client: Graphiti, query: str, num_results: int = 5):
        """Search the graph and print results with temporal info."""
        print(f"Query: {query}")
        print("-" * 60)

        results = await graphiti_client.search(query, num_results=num_results)

        if not results:
            print("  No results found.")
            return results

        for i, edge in enumerate(results):
            print(f"  [{i+1}] {edge.fact}")
            if edge.valid_at:
                print(f"      Valid from: {edge.valid_at.strftime('%Y-%m-%d')}")
            if edge.invalid_at:
                print(f"      Invalid at: {edge.invalid_at.strftime('%Y-%m-%d')}")
            else:
                print(f"      Status: current")
        print()
        return results

    return (search_and_display,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Let's try a few queries. Notice how the graph captures both current and historical facts.
    """)
    return


@app.cell
async def _(graphiti, search_and_display):
    # Query 1: Current team membership
    await search_and_display(graphiti, "What team is Alice on?")

    # Query 2: Relational question (multi-hop)
    await search_and_display(graphiti, "Who is Alice's manager?")

    # Query 3: Tool/technology query
    await search_and_display(graphiti, "What tools does Alice's team use?")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 4: Explore Temporal Edges

    The real strength of Graphiti shows when facts change. Alice moved from the RLHF team to the interpretability team. Bob left Anthropic. Let's see how the graph represents these changes.

    A temporal edge that has been superseded will have an `invalid_at` timestamp. Current edges will have `invalid_at` set to `None`.
    """)
    return


@app.cell
async def _(graphiti):
    # Search for Bob to see historical vs current facts
    print('=== Bob Martinez: tracking a career change ===')
    bob_results = await graphiti.search('Bob Martinez', num_results=10)
    current_facts = []
    historical_facts = []
    for _edge in bob_results:
        if _edge.invalid_at is not None:
            historical_facts.append(_edge)
        else:
            current_facts.append(_edge)
    print(f'\nCurrent facts ({len(current_facts)}):')
    for _edge in current_facts:
        print(f'  - {_edge.fact}')
    print(f'\nHistorical facts ({len(historical_facts)}):')
    for _edge in historical_facts:
        _valid = _edge.valid_at.strftime('%Y-%m-%d') if _edge.valid_at else '?'
        invalid = _edge.invalid_at.strftime('%Y-%m-%d') if _edge.invalid_at else '?'
        print(f'  - {_edge.fact}  (valid: {_valid} to {invalid})')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 5: Community Detection

    Think of communities like departments in a company. If you look at a company org chart, people who work together form clusters. Community detection finds these clusters automatically by analyzing which nodes are densely connected.

    Graphiti uses the Leiden algorithm to group nodes. The result is a set of `CommunityNode` objects, each with a name and a summary that describes the cluster.
    """)
    return


@app.cell
async def _(graphiti):
    # Build communities from the current graph state
    community_nodes, community_edges = await graphiti.build_communities()

    print(f"Found {len(community_nodes)} communities:\n")
    for community in community_nodes:
        print(f"Community: {community.name}")
        print(f"  Summary: {community.summary[:200]}")
        print()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Example Run: Graph-Powered Agent

    Now let's wire the graph into an agent loop. The agent will:

    1. Receive a user question.
    2. Search the knowledge graph for relevant facts.
    3. Inject those facts into the system prompt.
    4. Call an LLM to generate an answer grounded in the graph.

    This is the core pattern for graph-augmented generation. The graph acts as a structured external memory that the agent consults before every response.
    """)
    return


@app.cell
def _(Graphiti, graphiti, openai):
    class GraphMemoryAgent:
        """An agent that uses Graphiti's knowledge graph as its memory."""

        def __init__(self, graphiti_client: Graphiti, model: str = "gpt-4o-mini"):
            self.graphiti = graphiti_client
            self.openai_client = openai.OpenAI()
            self.model = model

        async def answer(self, question: str, num_facts: int = 10) -> str:
            """Answer a question using facts retrieved from the knowledge graph."""
            # Step 1: Search the graph
            edges = await self.graphiti.search(question, num_results=num_facts)

            # Step 2: Format retrieved facts for the prompt
            if edges:
                facts_text = "\n".join(
                    f"- {edge.fact}"
                    + (f" (valid from {edge.valid_at.strftime('%Y-%m-%d')})"
                       if edge.valid_at else "")
                    + (f" [NO LONGER TRUE as of {edge.invalid_at.strftime('%Y-%m-%d')}]"
                       if edge.invalid_at else "")
                    for edge in edges
                )
            else:
                facts_text = "No relevant facts found in the knowledge graph."

            system_prompt = (
                "You are a helpful assistant with access to a knowledge graph. "
                "Use the retrieved facts below to answer the user's question. "
                "If a fact is marked as no longer true, mention that it changed. "
                "If the facts don't cover the question, say so.\n\n"
                f"Retrieved facts:\n{facts_text}"
            )

            # Step 3: Generate response
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
                max_tokens=512,
            )

            return response.choices[0].message.content

    agent = GraphMemoryAgent(graphiti)
    return (agent,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Let's test the agent with questions that need relational reasoning and temporal awareness. These are the kinds of questions that flat vector stores struggle with.
    """)
    return


@app.cell
async def _(agent):
    test_questions = [
        "What team is Alice currently on, and who is her manager?",
        "Did Alice change teams? What was her previous team?",
        "Where does Bob Martinez work now? Has that changed recently?",
        "What tools and frameworks are used by Alice's current team?",
        "What project is Alice working on?",
    ]

    for question in test_questions:
        print(f"Q: {question}")
        answer = await agent.answer(question)
        print(f"A: {answer}")
        print("-" * 60)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Inspecting the Graph Structure

    Let's look at what Graphiti actually built. We'll search for edges and print the source and target node UUIDs to see the connection structure.
    """)
    return


@app.cell
async def _(graphiti):
    # Get a broad set of edges from the graph
    all_edges = await graphiti.search('Alice Anthropic team project', num_results=15)
    print(f'Found {len(all_edges)} edges in the graph:\n')
    print(f"{'Fact':<65} {'Status':<12} {'Valid From':<12}")
    print('=' * 89)
    for _edge in all_edges:
        fact_display = _edge.fact[:62] + '...' if len(_edge.fact) > 65 else _edge.fact
        status = 'historical' if _edge.invalid_at else 'current'
        _valid = _edge.valid_at.strftime('%Y-%m-%d') if _edge.valid_at else 'unknown'
        print(f'{fact_display:<65} {status:<12} {_valid:<12}')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Adding New Episodes to an Existing Graph

    A key feature of Graphiti is incremental updates. You don't rebuild the graph from scratch when new information arrives. You add episodes, and the pipeline integrates them with the existing graph.
    """)
    return


@app.cell
async def _(EpisodeType, datetime, graphiti, search_and_display, timezone):
    # Add a new episode with updated information
    new_episode = {
        "body": "User: Great news! The Lens project got approved for production deployment. Carol Park presented it to the leadership team.",
        "timestamp": datetime(2025, 5, 15, 9, 0, tzinfo=timezone.utc),
        "description": "Project status update",
    }

    await graphiti.add_episode(
        name="episode_06",
        episode_body=new_episode["body"],
        source=EpisodeType.message,
        source_description=new_episode["description"],
        reference_time=new_episode["timestamp"],
    )
    print("New episode ingested.")

    # Search for updated facts about Lens
    print("\nUpdated facts about the Lens project:")
    await search_and_display(graphiti, "Lens project status")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Cleanup

    Close the Graphiti connection to release the Neo4j resources.
    """)
    return


@app.cell
async def _(graphiti):
    await graphiti.close()
    print("Graphiti connection closed.")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Tradeoffs

    ### When Graph Memory Wins

    - **Relational questions.** "Who manages Alice?" or "What tools does Alice's team use?" require traversing connections. Flat vector stores can't follow relationship chains.
    - **Temporal reasoning.** "What team was Alice on before?" or "Has Bob changed jobs?" need timestamps on relationships. Graphiti tracks when facts became true and when they stopped being true.
    - **Entity-centric recall.** When the agent needs to build a complete picture of one entity (all of Alice's projects, teams, tools, and colleagues), graph traversal collects everything connected to that node.
    - **Long-running agents.** Over weeks or months of conversation, facts change. Graph memory handles these changes gracefully through edge invalidation rather than overwriting.

    ### When Graph Memory Struggles

    - **Infrastructure overhead.** You need a running Neo4j instance. That's a database to deploy, monitor, and back up. Vector stores like ChromaDB can run in-process with no server.
    - **Ingestion latency.** Each `add_episode` call triggers LLM-based extraction. That takes seconds per episode, not milliseconds. For real-time chat with fast responses, you may need to ingest episodes asynchronously in the background.
    - **Extraction quality.** The LLM pipeline can miss entities, hallucinate relationships, or fail to resolve duplicates. The graph is only as good as the extraction.
    - **Cost.** Every episode ingestion makes multiple LLM calls (entity extraction, relationship extraction, resolution). This adds up. A 100-episode conversation might cost several dollars in API calls for extraction alone.
    - **Simple recall.** If your agent only needs "What did the user say about X?", a vector store with embeddings is faster, cheaper, and simpler. Graph memory is overkill for direct fact lookup.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Further Reading

    - [Graphiti GitHub Repository](https://github.com/getzep/graphiti): Open-source code, API reference, and example notebooks for building temporal knowledge graphs from conversations.
    - [Zep Documentation](https://docs.getzep.com?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques): Production deployment guides for Graphiti and the broader Zep memory platform.
    - [Neo4j Graph Database Documentation](https://neo4j.com/docs/?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques): The graph database backend that powers Graphiti. Covers Cypher queries, indexing, and graph algorithms.
    - [Ji et al., "A Survey on Knowledge Graphs," IEEE TNNLS, 2021](https://ieeexplore.ieee.org/document/9416312): Covers knowledge graph construction, embedding methods, and downstream applications.
    - [Packer et al., "MemGPT: Towards LLMs as Operating Systems," 2023 (arXiv:2310.08560)](https://arxiv.org/abs/2310.08560): Related work on agent-managed memory that complements graph-based approaches.
    - [Kang et al., "Zep: A Temporal Knowledge Graph Architecture for Agent Memory," 2025 (arXiv:2501.13956)](https://arxiv.org/abs/2501.13956): The paper behind Graphiti's temporal knowledge graph design.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    *← Previous: [23 - Memory with Tools](../23_memory_with_tools/) · Next: [25 - Mem0 Integration Patterns](../25_mem0_patterns/) →*
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 🧪 Try It Yourself

    Three small challenges to deepen your understanding. Each should take 10-30 minutes.

    ### Challenge 1: Community exploration
    After adding 10 episodes, call `build_communities()` and inspect the resulting community nodes. Print each community's name and the entities it contains. Discuss whether the communities match the topics in your conversation data.

    ### Challenge 2: Graph growth metrics
    After each `add_episode()` call, query the graph for total entity nodes, entity edges, and average node degree. Plot these metrics over the episode sequence. Identify whether the graph grows linearly or accelerates as more cross-references appear.

    ### Challenge 3: Temporal contradiction detection
    Add two episodes that contain contradictory facts about the same entity (e.g., 'Alice works at Acme' then 'Alice works at Globex'). Use `search()` to retrieve facts about Alice and check whether the old edge's `expired_at` timestamp is set. This demonstrates the temporal invalidation ideas explored in 18 Temporal Memory.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--24-graph-memory-graphiti--graph-memory-graphiti)
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
