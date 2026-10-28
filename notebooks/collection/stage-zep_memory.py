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
    # Zep Memory

    > **A production-grade memory service that extracts facts, classifies dialog, identifies entities, and builds a temporal knowledge graph from your agent's conversations.**

    Think of hiring a personal assistant who sits in on every meeting. This assistant doesn't record conversations word for word. Instead, they write key facts on index cards ("The client's budget is $50k"). They note who was mentioned ("Alice from marketing"). They label each meeting's topic ("Q3 planning"). They draw a diagram showing how people and projects connect. All of this happens in the background while you keep talking.

    That's what **Zep** does for your AI agent. You send messages to Zep, and background pipelines handle the rest. A **dialog classifier** labels each turn's intent and topic. An **entity extractor** identifies people, organizations, and projects. A **fact extractor** pulls structured statements from unstructured text. A **knowledge graph builder** (powered by Graphiti) maps relationships between entities over time.

    Your agent doesn't wait for any of this processing. It keeps responding while Zep works in the background. The result is a memory layer with three retrieval modes: **semantic search** over extracted facts, **graph traversal** over entity relationships, and **assembled context** strings ready for your prompts.

    **By the end of this notebook you'll understand:**
    - How Zep's background pipelines turn raw conversations into structured memory.
    - How to add messages, search facts, and retrieve context with the Zep SDK.
    - How to build an agent loop that uses Zep for persistent, cross-session memory.
    - When Zep is the right choice and when simpler approaches work better.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Key Concepts

    - **Thread**: A conversation container in Zep. Each thread has a unique ID and belongs to a user. Think of it as one chat session. Threads track message history and all knowledge extracted from that history.
    - **Background pipelines**: Automated processes that run after you add messages. They extract facts, identify entities, classify dialog, and build graph relationships. You don't call them directly. They run asynchronously (in the background, without blocking your code).
    - **Fact extraction**: Turning unstructured dialog into structured statements. For example, "I moved to London last March" becomes a queryable record with a timestamp. Facts are the primary unit of Zep's semantic memory.
    - **Entity extraction**: Identifying named entities (people, places, organizations, products) across conversations. Zep deduplicates entities (merges duplicates) and links them across threads. This builds a persistent registry of everything your agent has learned about.
    - **Dialog classification**: Automatic labeling of each conversation turn by intent (question, instruction, feedback), topic, and sentiment. No manual labeling or custom model training needed.
    - **Temporal knowledge graph**: A graph database (powered by Graphiti) that stores relationships between entities with timestamps. "Temporal" means it tracks *when* things were true. This lets you ask "What was true last week?" and see how knowledge changes.
    - **Graph search**: Querying Zep's knowledge graph with natural language. Results are ranked by semantic relevance (how close in meaning your query is to stored facts). You can search over edges (facts), nodes (entities), or episodes (conversation segments).
    - **Assembled context**: A pre-formatted text block that Zep builds from relevant facts, entities, and messages. You inject this directly into your LLM's system prompt. No manual retrieval logic needed.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Architecture

    <p align="center">
      <img src="../../images/diagrams/27_zep_memory.svg" alt="Zep Memory Architecture" width="720"/>
    </p>

    <details><summary>Mermaid source</summary>

    ```mermaid
    flowchart TD
        subgraph App["Agent Application"]
            A["User Messages"] --> B["Zep SDK\n(add_messages)"]
            K["Zep SDK\n(graph.search)"] --> L["Agent Context\nWindow"]
        end

        subgraph ZepService["Zep Service"]
            B --> C["Message Store"]
            C --> D["Background Pipelines"]

            subgraph Pipelines["Async Processing"]
                D --> E["Dialog\nClassifier"]
                D --> F["Entity\nExtractor"]
                D --> G["Fact\nExtractor"]
                D --> H["Knowledge Graph\nBuilder (Graphiti)"]
            end

            subgraph Storage["Zep Storage"]
                I[("Messages +\nFacts +\nEntities +\nGraph")]
            end

            E --> I
            F --> I
            G --> I
            H --> I

            subgraph Search["Search API"]
                J["Semantic Search\n+ Graph Traversal\n+ Temporal Filter"]
            end

            I --> J
        end

        J --> K

        style I fill:#4f46e5,color:#fff
        style E fill:#059669,color:#fff
        style F fill:#059669,color:#fff
        style G fill:#059669,color:#fff
        style H fill:#8b5cf6,color:#fff
        style J fill:#d97706,color:#fff
        style L fill:#6366f1,color:#fff
    ```

    </details>

    **How data flows through Zep:**

    1. Your agent sends user and assistant messages to Zep through the SDK's `add_messages()` method.
    2. Zep stores the messages immediately. Background pipelines begin processing.
    3. The dialog classifier labels each turn. The entity extractor identifies and deduplicates entities. The fact extractor distills structured facts. The knowledge graph builder updates the Graphiti temporal graph.
    4. All extracted data lands in Zep's unified storage layer.
    5. Before generating a response, your agent calls `graph.search()` or `get_user_context()`. Zep returns ranked facts and relevant entities.
    6. Your agent injects the retrieved memory into its context window for personalized responses.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Setup

    Install the Zep Cloud SDK and the Anthropic SDK. You'll also need `python-dotenv` to load API keys from a `.env` file.
    """)
    return


@app.cell
def _():
    # '%pip install -q zep-cloud anthropic python-dotenv' command supported automatically in marimo
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Load environment variables and initialize the Zep and Anthropic clients. You need two API keys:

    - `ZEP_API_KEY`: your Zep Cloud API key (sign up at [getzep.com](https://www.getzep.com?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques))
    - `ANTHROPIC_API_KEY`: your Anthropic API key
    """)
    return


@app.cell
def _():
    import os
    import time
    import uuid
    from dotenv import load_dotenv

    load_dotenv()  # reads ZEP_API_KEY and ANTHROPIC_API_KEY from .env

    from zep_cloud import Zep, Message
    import anthropic

    assert os.getenv("ZEP_API_KEY"), "Set ZEP_API_KEY in your .env file"
    assert os.getenv("ANTHROPIC_API_KEY"), "Set ANTHROPIC_API_KEY in your .env file"

    zep = Zep(api_key=os.getenv("ZEP_API_KEY"))
    llm = anthropic.Anthropic()
    return Message, llm, time, uuid, zep


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Implementation

    We'll build a memory-augmented agent in five steps:

    1. Create a user and a thread in Zep.
    2. Add conversation messages and let background pipelines process them.
    3. Search for extracted facts using graph search.
    4. Retrieve assembled context for prompt injection.
    5. Wire everything into a reusable agent loop.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 1: Create a User and Thread

    Every conversation in Zep belongs to a user and lives inside a thread. We generate unique IDs so this notebook is safe to run multiple times.
    """)
    return


@app.cell
def _(uuid, zep):
    user_id = f"demo_user_{uuid.uuid4().hex[:8]}"
    thread_id = f"demo_thread_{uuid.uuid4().hex[:8]}"

    zep.user.add(
        user_id=user_id,
        first_name="Alice",
        metadata={"role": "ml_engineer"},
    )
    zep.thread.create(thread_id=thread_id, user_id=user_id)

    print(f"Created user:   {user_id}")
    print(f"Created thread: {thread_id}")
    return thread_id, user_id


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 2: Add Messages

    We'll send a realistic multi-turn conversation to Zep. After calling `add_messages()`, Zep stores the messages and kicks off its background pipelines. The pipelines extract facts, identify entities, classify dialog intent, and update the knowledge graph.

    Processing takes a few seconds. We add a short wait so results are available when we query.
    """)
    return


@app.cell
def _(Message, thread_id, time, zep):
    conversation = [
        Message(role="user", content="Hi! I'm Alice, a machine learning engineer at Acme Corp."),
        Message(role="assistant", content="Nice to meet you, Alice! What are you working on at Acme Corp?"),
        Message(role="user", content="We're building a recommendation system. My team lead is Bob Chen."),
        Message(role="assistant", content="Interesting! What kind of recommendations?"),
        Message(role="user", content="Product recommendations for our e-commerce platform. We use Python and PyTorch."),
        Message(role="assistant", content="Great choices. Are you using collaborative filtering or content-based approaches?"),
        Message(role="user", content=(
            "We started with collaborative filtering but we're moving to a hybrid approach. "
            "Our budget for this quarter is $200k."
        )),
        Message(role="assistant", content="A hybrid approach often gives better results. How large is your dataset?"),
        Message(role="user", content="About 50 million user-product interactions. We also have rich product metadata."),
    ]

    zep.thread.add_messages(thread_id=thread_id, messages=conversation)
    print(f"Added {len(conversation)} messages to thread '{thread_id}'")

    # Wait for background pipelines to process
    print("Waiting for Zep to extract facts and entities...")
    time.sleep(10)
    print("Processing complete.")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 3: Search Extracted Facts

    Zep's graph search lets you query the knowledge graph with natural language. When you search with `scope="edges"`, you get extracted facts (relationships between entities). Each fact includes the original statement and a relevance score.
    """)
    return


@app.cell
def _(user_id, zep):
    queries = ['What technology does Alice use?', "Who is on Alice's team?", 'What is the project budget?']
    for _query in queries:
        results = zep.graph.search(query=_query, user_id=user_id, scope='edges', limit=3)
        print(f'Query: {_query}')
        for _edge in results.edges or []:
            print(f'  -> {_edge.fact}')
        print()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 4: Retrieve Assembled Context

    Instead of searching manually, you can ask Zep for a pre-assembled context string. This string combines relevant facts, entities, and recent messages into a text block. You inject it directly into your LLM's system prompt.

    This is the most common pattern in production. It saves you from writing custom retrieval and ranking logic.
    """)
    return


@app.cell
def _(thread_id, zep):
    context_response = zep.thread.get_user_context(thread_id=thread_id)

    print("Assembled context for LLM injection:")
    print("=" * 60)
    print(context_response.context or "(No context available yet)")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 5: Build a Memory-Augmented Agent Loop

    Now we combine everything into a reusable agent class. The pattern is:

    1. The user sends a message.
    2. We add it to Zep and request relevant context back (using `return_context=True`).
    3. We build a system prompt that includes the context.
    4. We call the LLM.
    5. We store the assistant's response in Zep for future reference.

    Because Zep stores memory at the **user level**, facts from one thread carry into other threads for the same user. Your agent remembers across conversations.
    """)
    return


@app.cell
def _(Message):
    class ZepMemoryAgent:
        """An agent that uses Zep for persistent, cross-session memory."""

        def __init__(
            self,
            zep_client,
            llm_client,
            user_id,
            thread_id,
            model="claude-sonnet-4-20250514",
            max_tokens=512,
        ):
            self.zep = zep_client
            self.llm = llm_client
            self.user_id = user_id
            self.thread_id = thread_id
            self.model = model
            self.max_tokens = max_tokens

        def chat(self, user_input):
            """Send a message and get a memory-augmented response."""
            # Add the user message and retrieve relevant context in one call
            add_response = self.zep.thread.add_messages(
                thread_id=self.thread_id,
                messages=[Message(role="user", content=user_input)],
                return_context=True,
            )
            context = add_response.context or ""

            # Build system prompt with Zep's assembled context
            system_prompt = (
                "You are a helpful assistant with memory of past conversations.\n\n"
                "Use the following context to personalize your response. "
                "Reference relevant facts naturally without mentioning the memory system.\n\n"
                f"<context>\n{context}\n</context>"
            )

            # Call the LLM
            response = self.llm.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_input}],
            )
            assistant_text = response.content[0].text

            # Store the assistant's response in Zep
            self.zep.thread.add_messages(
                thread_id=self.thread_id,
                messages=[Message(role="assistant", content=assistant_text)],
            )

            return assistant_text

    return (ZepMemoryAgent,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Example Run

    Let's create a **new thread** for the same user. Even though this is a fresh conversation, the agent can access facts from the previous thread. This is Zep's cross-session memory in action.
    """)
    return


@app.cell
def _(ZepMemoryAgent, llm, user_id, uuid, zep):
    agent_thread_id = f"agent_thread_{uuid.uuid4().hex[:8]}"
    zep.thread.create(thread_id=agent_thread_id, user_id=user_id)

    agent = ZepMemoryAgent(
        zep_client=zep,
        llm_client=llm,
        user_id=user_id,
        thread_id=agent_thread_id,
    )

    # The agent can recall facts from the first thread
    exchanges = [
        "What do you remember about my work?",
        "Who's my team lead?",
        "What's our quarterly budget?",
        "Based on what you know about our project, what papers should I read?",
    ]

    for msg in exchanges:
        print(f"User:  {msg}")
        reply = agent.chat(msg)
        print(f"Agent: {reply}\n")
    return (agent_thread_id,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Comparing Retrieval Modes

    Zep supports different search scopes. Each scope returns a different view of the stored knowledge:

    - **edges**: Extracted facts (relationships between entities). Best for direct recall.
    - **nodes**: Entity summaries. Best for "tell me about X" questions.
    - **auto**: Zep picks the best scope for your query.

    Let's run the same query through each scope to see the difference.
    """)
    return


@app.cell
def _(user_id, zep):
    _query = 'What is Alice working on?'
    print(f"Query: '{_query}'\n")
    fact_results = zep.graph.search(query=_query, user_id=user_id, scope='edges', limit=3)
    # Fact search (edges)
    print('Facts (edges):')
    for _edge in fact_results.edges or []:
        print(f'  - {_edge.fact}')
    node_results = zep.graph.search(query=_query, user_id=user_id, scope='nodes', limit=3)
    print('\nEntities (nodes):')
    for node in node_results.nodes or []:
        print(f'  - {node.name}: {node.summary}')
    # Entity search (nodes)
    auto_results = zep.graph.search(query=_query, user_id=user_id, scope='auto', limit=5)
    print('\nAuto (Zep chooses):')
    if auto_results.edges:
        for _edge in auto_results.edges:
            print(f'  Fact: {_edge.fact}')
    if auto_results.nodes:
        for node in auto_results.nodes:
    # Auto search (Zep picks the best scope)
            print(f'  Entity: {node.name}')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Clean up the demo resources we created.
    """)
    return


@app.cell
def _(agent_thread_id, thread_id, user_id, zep):
    zep.thread.delete(thread_id=thread_id)
    zep.thread.delete(thread_id=agent_thread_id)
    zep.user.delete(user_id=user_id)
    print(f"Deleted user '{user_id}' and associated threads.")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Tradeoffs

    ### When Zep Works Well

    - **Multi-session agents**: Zep stores memory at the user level. Facts from one conversation carry into the next. You don't need to manage memory persistence yourself.
    - **Automatic extraction**: You send raw messages. Zep extracts facts, identifies entities, classifies dialog, and builds a knowledge graph. No custom NLP pipelines required.
    - **Managed infrastructure**: The cloud version handles scaling, indexing, and model updates. Your team focuses on agent logic, not memory infrastructure.
    - **Temporal awareness**: The knowledge graph tracks when facts were true. Your agent can distinguish "user lived in NYC" (past) from "user lives in London" (present).

    ### When It Breaks Down

    - **Extraction accuracy**: Background pipelines use LLMs to extract facts. They can miss nuances, hallucinate facts, or misclassify entities. You can't easily tune the extraction models.
    - **Latency for first query**: Extraction is asynchronous. Facts aren't available the instant you add messages. For real-time applications, there's a brief delay before new knowledge is searchable.
    - **Cost at scale**: Every message triggers LLM-based extraction. At high message volumes, the per-message extraction cost adds up. Simpler techniques (like buffer or window memory) are cheaper per message.
    - **Vendor dependency**: The cloud version requires a Zep account and API key. The open-source version needs self-hosting with specific infrastructure. Either way, you're committing to Zep's data model.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Further Reading

    - [Zep Documentation](https://docs.getzep.com?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques) - Official docs covering threads, memory search, fact extraction, and SDK integration.
    - [Zep GitHub Repository](https://github.com/getzep/zep) - Open-source code for self-hosted deployment and community contributions.
    - [Zep Python SDK (PyPI)](https://pypi.org/project/zep-cloud/?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques) - Package details, version history, and installation instructions.
    - [Graphiti: Temporal Knowledge Graphs](https://github.com/getzep/graphiti) - The graph engine powering Zep's knowledge graph layer.
    - [Anthropic: Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques) - Agent architecture patterns that complement Zep's memory capabilities.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    *← Previous: [26 - Letta (MemGPT) Patterns](../26_letta_memgpt_patterns/) · Next: [28 - Memory Evaluation](../28_memory_evaluation/) →*
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 🧪 Try It Yourself

    Three small challenges to deepen your understanding. Each should take 10-30 minutes.

    ### Challenge 1: Fact extraction audit
    After adding 10 messages to a thread, wait for background processing and retrieve the extracted facts via `graph.search()`. Compare the extracted facts against a hand-written list of ground-truth facts from the messages. Compute precision and recall for the extraction.

    ### Challenge 2: Retrieval method comparison
    For the same set of queries, compare results from `graph.search()` vs. `get_user_context()`. Measure which method returns more relevant information and note the latency difference. Record results in a comparison table.

    ### Challenge 3: Multi-thread topic routing
    Create 3 separate threads in Zep, each for a different topic (e.g., work, hobbies, travel). Add relevant messages to each thread. Query across all three threads and measure whether topic isolation improves retrieval precision. This connects to the routing patterns in 17 Memory Routing.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--27-zep-memory--zep-memory)
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
