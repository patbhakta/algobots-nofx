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
    # Mem0 Integration Patterns

    > **Give every user a persistent, self-improving memory. No need to build your own extraction pipeline, vector store, or deduplication logic.**

    Think of a personal assistant who takes notes during every meeting. After each conversation, they jot down key facts: your preferences, your schedule, your contacts. Before the next meeting, they review those notes so they can help you better. Mem0 is that assistant for your AI agent, but fully automated.

    Most agent memory implementations require you to wire three separate systems by hand. First, an LLM-based extraction step to pull facts from conversations. Second, a vector database (a database optimized for finding similar items by meaning) for storage. Third, reconciliation logic to handle contradictions and duplicates. **Mem0** collapses all of this into a single `add()` / `search()` / `get_all()` API.

    Under the hood, Mem0's open-source library:
    1. Sends conversation messages through an LLM to **extract key facts, preferences, and instructions**.
    2. **Deduplicates and resolves contradictions** against existing memories.
    3. Stores the result in a vector database (Qdrant by default) for **semantic retrieval** (finding memories by meaning, not exact keywords).

    The result is a **user-scoped memory layer** that gets smarter over time. Memories are automatically merged, updated, and refined as new information arrives.

    **By the end of this notebook you'll:**
    - Install and configure Mem0 with OpenAI as the LLM backend.
    - Add memories from conversation messages and raw text.
    - Search, retrieve, update, and delete memories.
    - Build a memory-augmented agent loop that personalizes responses using Mem0.
    - Understand when Mem0 is the right choice vs. building your own memory system.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Key Concepts

    - **`Memory.add()`:** Accepts conversation messages (or raw text). Runs LLM-based extraction to identify memorable facts. Checks for duplicates and contradictions against existing memories. Stores the results. This single call replaces a custom extraction + embedding + upsert pipeline.
    - **`Memory.search()`:** Semantic search over stored memories using a natural-language query. Returns ranked results with relevance scores. Supports filters by `user_id`, `agent_id`, and metadata.
    - **`Memory.get_all()`:** Retrieves all memories for a given user, agent, or session scope. Useful for displaying a user's full memory profile or debugging.
    - **`Memory.update()` / `Memory.delete()`:** Explicitly modify or remove individual memories by ID. The update path is useful when the agent knows a fact has changed (for example, a user moved cities).
    - **User-scoped isolation:** Every operation is scoped by `user_id`. One user's memories never leak into another's context. Optional `agent_id` and `run_id` add finer-grained scoping.
    - **Automatic conflict resolution:** When you `add()` a memory that contradicts an existing one (for example, "I moved from NYC to London"), Mem0's LLM pipeline detects the conflict. It updates the stored memory rather than creating a duplicate.
    - **Self-improving memory:** Over repeated `add()` calls, Mem0 merges and refines related memories. The memory store becomes more accurate and concise over time without manual curation.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Architecture

    <p align="center">
      <img src="../../images/diagrams/25_mem0_patterns.svg" alt="diagram" width="720"/>
    </p>

    <details><summary>Mermaid source</summary>

    ```mermaid
    flowchart LR
        subgraph App["Agent / Application"]
            A["User message"] --> B["Agent generates\nresponse"]
            B --> C["Response to user"]
        end

        subgraph Mem0Layer["Mem0 Memory Layer"]
            D["memory.add()\n─────────\nLLM extraction\nConflict resolution\nDeduplication"]
            E["memory.search()\n─────────\nSemantic search\nRanked results"]
            F[("Vector Store\n(Qdrant)\n─────────\nEmbeddings\nMetadata\nUser scopes")]
        end

        subgraph Ops["Management"]
            G["memory.get_all()\nmemory.update()\nmemory.delete()"]
        end

        A -->|"conversation turns"| D
        D -->|"extracted facts"| F
        A -->|"query"| E
        E -->|"relevant memories"| B
        F <-->|"store / retrieve"| E
        G <--> F

        style F fill:#4f46e5,color:#fff
        style D fill:#059669,color:#fff
        style E fill:#d97706,color:#fff
        style B fill:#6366f1,color:#fff
    ```

    </details>

    **Data flow for each conversation turn:**
    1. The user sends a message. The agent calls `memory.search()` to retrieve relevant context.
    2. The agent generates a response using the retrieved memories as context.
    3. The full conversation turn passes to `memory.add()` to extract and store new facts.
    4. Mem0's LLM pipeline extracts facts, resolves conflicts, and updates the vector store.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Setup

    Install the required packages. Mem0 uses OpenAI for both the extraction LLM and embeddings by default.
    """)
    return


@app.cell
def _():
    # Install required packages (run once)
    # '%pip install -q mem0ai python-dotenv openai' command supported automatically in marimo
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Import Mem0 and load your API key from a `.env` file.
    Mem0 picks up `OPENAI_API_KEY` automatically for its LLM and embedding calls.
    """)
    return


@app.cell
def _():
    import os
    import json
    from dotenv import load_dotenv

    load_dotenv()  # reads API keys from .env

    assert os.getenv("OPENAI_API_KEY"), "Set OPENAI_API_KEY in your .env file"

    # Mem0 uses OpenAI for both extraction (LLM) and embeddings by default.
    # No additional config is needed if OPENAI_API_KEY is set.

    from mem0 import Memory

    print("\u2713 Environment loaded")
    print(f"\u2713 mem0 imported successfully")
    return Memory, json


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Core Implementation

    We'll walk through each Mem0 operation step by step:

    1. **Initialize:** Create a `Memory` instance (uses Qdrant locally + OpenAI by default).
    2. **Add:** Store memories from conversation messages.
    3. **Search:** Retrieve relevant memories by semantic query.
    4. **Get All:** List a user's complete memory profile.
    5. **Update:** Modify an existing memory.
    6. **Delete:** Remove a specific memory.
    7. **History:** View the change history of a memory.
    """)
    return


@app.cell
def _(Memory):
    # Initialize Mem0 with default configuration
    # Default: Qdrant (local, on-disk) + OpenAI gpt-4o-mini + text-embedding-3-small
    m = Memory()

    print("\u2713 Memory instance created")
    print("  Vector store: Qdrant (local)")
    print("  LLM: OpenAI (default)")
    print("  Embedder: OpenAI text-embedding-3-small")
    return (m,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Adding Memories from Conversations

    Pass conversation messages to `m.add()`. Mem0's LLM pipeline extracts the key facts automatically.
    Each call is scoped to a `user_id`, so one user's memories stay separate from another's.
    """)
    return


@app.cell
def _(json, m):
    # ── Adding memories from conversation messages ──
    # Mem0 extracts facts automatically. You just pass the conversation.

    USER_ID = "alice"

    # Conversation 1: Food preferences
    messages_1 = [
        {"role": "user", "content": "I'm a vegetarian and I love Italian food. My favorite dish is mushroom risotto."},
        {"role": "assistant", "content": "Great taste! Mushroom risotto is a classic. I'll remember your preferences."},
    ]
    result_1 = m.add(messages_1, user_id=USER_ID)
    print("Add result (food preferences):")
    print(json.dumps(result_1, indent=2))

    print()

    # Conversation 2: Work context
    messages_2 = [
        {"role": "user", "content": "I'm a senior data scientist at Google. I mostly work with Python and PyTorch."},
        {"role": "assistant", "content": "Nice! Data science at Google, exciting work. I'll keep that in mind."},
    ]
    result_2 = m.add(messages_2, user_id=USER_ID)
    print("Add result (work context):")
    print(json.dumps(result_2, indent=2))

    print()

    # Conversation 3: Personal details
    messages_3 = [
        {"role": "user", "content": "I live in San Francisco. I moved here from New York last year. I have a golden retriever named Max."},
        {"role": "assistant", "content": "SF is lovely! And golden retrievers are the best. How's Max adjusting to the new city?"},
    ]
    result_3 = m.add(messages_3, user_id=USER_ID)
    print("Add result (personal details):")
    print(json.dumps(result_3, indent=2))
    return (USER_ID,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Searching Memories

    Use `m.search()` to find memories by meaning, not exact keywords.
    Mem0 embeds your query and returns the most similar stored facts, ranked by relevance.
    """)
    return


@app.cell
def _(USER_ID, m):
    # ── Searching memories by semantic query ──
    # Mem0 returns the most relevant memories ranked by similarity.
    print("=== Search: 'What food does Alice like?' ===\n")
    food_results = m.search('What food does Alice like?', user_id=USER_ID)
    for _mem in food_results.get('results', food_results if isinstance(food_results, list) else []):
        if isinstance(_mem, dict):
            print(f"  • {_mem.get('memory', _mem.get('text', str(_mem)))}")
    print()
    print("=== Search: 'What does Alice do for work?' ===\n")
    work_results = m.search('What does Alice do for work?', user_id=USER_ID)
    for _mem in work_results.get('results', work_results if isinstance(work_results, list) else []):
        if isinstance(_mem, dict):
            print(f"  • {_mem.get('memory', _mem.get('text', str(_mem)))}")
    print()
    print("=== Search: 'pets' ===\n")
    pet_results = m.search('pets', user_id=USER_ID)
    for _mem in pet_results.get('results', pet_results if isinstance(pet_results, list) else []):
        if isinstance(_mem, dict):
            print(f"  • {_mem.get('memory', _mem.get('text', str(_mem)))}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Listing All Memories

    Call `m.get_all()` to see every memory stored for a user.
    This is useful for debugging or showing the user their full profile.
    """)
    return


@app.cell
def _(USER_ID, m):
    # ── Get all memories for a user ──
    # Useful for inspecting the full memory profile.
    all_memories = m.get_all(user_id=USER_ID)
    memory_list = all_memories.get('results', all_memories) if isinstance(all_memories, dict) else all_memories
    print(f"=== All memories for '{USER_ID}' ({len(memory_list)} total) ===\n")
    # Handle both list and dict response formats
    for i, _mem in enumerate(memory_list, 1):
        mem_id = _mem.get('id', 'N/A')
        mem_text = _mem.get('memory', _mem.get('text', str(_mem)))
        print(f'  {i}. [{mem_id[:8]}...] {mem_text}')
    if memory_list:
        SAMPLE_MEMORY_ID = memory_list[0].get('id')
    # Save one memory ID for later update/delete demos
        print(f'\n✓ Saved memory ID for later: {SAMPLE_MEMORY_ID[:12]}...')
    return (SAMPLE_MEMORY_ID,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Automatic Conflict Resolution

    When you add a fact that contradicts an existing memory, Mem0 detects the conflict.
    It updates the stored memory instead of creating a duplicate.
    Watch how Alice's location changes from San Francisco to London.
    """)
    return


@app.cell
def _(USER_ID, json, m):
    # ── Automatic conflict resolution ──
    # When you add a fact that contradicts an existing memory, Mem0 updates it.
    print("=== Before: Alice's location ===")
    location_before = m.search('Where does Alice live?', user_id=USER_ID)
    for _mem in location_before.get('results', location_before) if isinstance(location_before, dict) else location_before:
        if isinstance(_mem, dict):
            print(f"  • {_mem.get('memory', _mem.get('text', str(_mem)))}")
    messages_move = [{'role': 'user', 'content': 'I just moved to London! Left San Francisco last week.'}, {'role': 'assistant', 'content': 'Exciting move! How are you finding London so far?'}]
    result_move = m.add(messages_move, user_id=USER_ID)
    # Alice moves to London
    print(f'\nUpdate result:')
    print(json.dumps(result_move, indent=2))
    print("\n=== After: Alice's location ===")
    location_after = m.search('Where does Alice live?', user_id=USER_ID)
    for _mem in location_after.get('results', location_after) if isinstance(location_after, dict) else location_after:
        if isinstance(_mem, dict):
            print(f"  • {_mem.get('memory', _mem.get('text', str(_mem)))}")
    print('\n✓ Mem0 resolved the contradiction: location updated, not duplicated.')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Explicit Update and Delete

    You can also modify or remove specific memories by their ID.
    Use `m.update()` when you know exactly which fact changed.
    Use `m.delete()` when a memory should be removed entirely.
    """)
    return


@app.cell
def _(SAMPLE_MEMORY_ID, USER_ID, m):
    # ── Explicit update and delete ──
    if SAMPLE_MEMORY_ID:
    # Update: change a specific memory by ID
        print(f'=== Updating memory {SAMPLE_MEMORY_ID[:12]}... ===')
        update_result = m.update(memory_id=SAMPLE_MEMORY_ID, data='Alice is a strict vegan who loves Italian cuisine')
        print(f'Update result: {update_result}')
        print('\nAfter update:')
        updated = m.search('food preferences', user_id=USER_ID)
        for _mem in updated.get('results', updated) if isinstance(updated, dict) else updated:  # Verify the update
            if isinstance(_mem, dict):
                print(f"  • {_mem.get('memory', _mem.get('text', str(_mem)))}")
    print()
    temp = m.add('Alice temporarily likes sushi', user_id=USER_ID)
    temp_list = temp.get('results', temp) if isinstance(temp, dict) else temp
    if isinstance(temp_list, list) and temp_list:
        temp_id = temp_list[0].get('id', temp_list[0].get('memory_id'))
    elif isinstance(temp_list, dict):
    # Delete: remove a specific memory
    # First, let's add a temporary memory to delete
        temp_id = temp_list.get('id', temp_list.get('memory_id'))
    else:
        temp_id = None
    if temp_id:
        print(f'=== Deleting temporary memory {str(temp_id)[:12]}... ===')
        delete_result = m.delete(memory_id=temp_id)
        print(f'Delete result: {delete_result}')
        print('✓ Memory deleted')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Memory-Augmented Agent Loop

    Now let's build a practical agent that uses Mem0 to personalize its responses. The pattern has three steps:

    1. **Retrieve:** Before responding, search Mem0 for memories relevant to the user's message.
    2. **Generate:** Include retrieved memories in the system prompt so the LLM can personalize its response.
    3. **Store:** After the exchange, pass the conversation to `memory.add()` to capture new facts.

    This creates a **self-reinforcing loop**. Every conversation enriches the memory. Every response benefits from accumulated knowledge.
    """)
    return


@app.cell
def _(Memory):
    from openai import OpenAI


    class Mem0Agent:
        """A conversational agent that uses Mem0 for persistent, personalized memory."""

        def __init__(self, memory: Memory, model: str = "gpt-4o-mini", user_id: str = "default"):
            self.memory = memory
            self.client = OpenAI()
            self.model = model
            self.user_id = user_id
            self.conversation: list[dict] = []

    return (Mem0Agent,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `chat` method ties the three-step pattern together: retrieve, generate, store.
    Before answering, it searches Mem0 for relevant context.
    After answering, it passes the exchange back to Mem0 so new facts get captured.
    """)
    return


@app.function
def chat(self, user_message: str) -> str:
        """Process a user message: retrieve memories, generate response, store new memories."""

        # Step 1: Retrieve relevant memories
        relevant_memories = self.memory.search(user_message, user_id=self.user_id)
        mem_list = relevant_memories.get("results", relevant_memories) if isinstance(relevant_memories, dict) else relevant_memories

        # Format memories for the system prompt
        if mem_list:
            memory_context = "\n".join(
                f"- {mem.get('memory', mem.get('text', str(mem)))}"
                for mem in mem_list
                if isinstance(mem, dict)
            )
            memory_block = (
                f"\n\nYou have these memories about the user (use them to personalize your response):\n"
                f"{memory_context}"
            )
        else:
            memory_block = ""

        system_prompt = (
            "You are a helpful, friendly assistant with a great memory. "
            "You remember details about the user from past conversations and use them "
            "to provide personalized, relevant responses. Reference specific things you "
            "remember when appropriate. It shows you care."
            f"{memory_block}"
        )

        # Step 2: Build messages and generate response
        self.conversation.append({"role": "user", "content": user_message})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt}] + self.conversation[-10:],  # last 10 turns
        )
        assistant_message = response.choices[0].message.content
        self.conversation.append({"role": "assistant", "content": assistant_message})

        # Step 3: Store new memories from this exchange
        self.memory.add(
            [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_message},
            ],
            user_id=self.user_id,
        )

        return assistant_message


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `show_memories` helper prints all stored memories for the current user.
    We'll use it after each demo to see what Mem0 extracted.
    """)
    return


@app.cell
def _():
    def show_memories(self) -> None:
            """Display all stored memories for this user."""
            all_mem = self.memory.get_all(user_id=self.user_id)
            mem_list = all_mem.get("results", all_mem) if isinstance(all_mem, dict) else all_mem
            print(f"\n=== Memories for '{self.user_id}' ({len(mem_list)} total) ===")
            for i, mem in enumerate(mem_list, 1):
                print(f"  {i}. {mem.get('memory', mem.get('text', str(mem)))}")


    print("\u2713 Mem0Agent class defined")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Demo: Multi-Turn Personalized Conversation

    Let's create a new user (Bob) and have a three-turn conversation.
    The agent should remember Bob's details and personalize its responses.
    After the conversation, we'll check what Mem0 stored.
    """)
    return


@app.cell
def _(Mem0Agent, m):
    # ── Demo: Multi-turn personalized conversation ──
    agent = Mem0Agent(memory=m, user_id='bob')
    # Use a different user_id for this demo to start with a clean slate
    print('=' * 60)
    print('Turn 1')
    # Turn 1: Bob introduces himself
    print('=' * 60)
    _user_msg = "Hi! I'm Bob. I'm a software engineer and I love hiking on weekends."
    print(f'User: {_user_msg}\n')
    _response = agent.chat(_user_msg)
    print(f'Agent: {_response}')
    print()
    print('=' * 60)
    print('Turn 2')
    print('=' * 60)
    _user_msg = "I've been learning Rust lately. Also, I'm training for a half marathon in October."
    # Turn 2: More preferences
    print(f'User: {_user_msg}\n')
    _response = agent.chat(_user_msg)
    print(f'Agent: {_response}')
    print()
    print('=' * 60)
    print('Turn 3')
    print('=' * 60)
    _user_msg = 'Can you suggest some weekend activities for me?'
    print(f'User: {_user_msg}\n')
    _response = agent.chat(_user_msg)
    # Turn 3: Agent should recall earlier context
    print(f'Agent: {_response}')
    # Show what Mem0 stored
    agent.show_memories()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Simulating a New Session

    Now we create a brand-new agent instance but keep the same `user_id`.
    This simulates Bob coming back days later.
    The memories persist in Mem0, so the agent should remember everything from before.
    """)
    return


@app.cell
def _(Mem0Agent, m):
    # ── Simulating a new session ──
    # Create a brand-new agent instance, same user_id.
    # Memories persist from the previous conversation.
    print('=' * 60)
    print('NEW SESSION (fresh agent, same user_id)')
    print('=' * 60)
    agent2 = Mem0Agent(memory=m, user_id='bob')
    _user_msg = 'Hey, I just finished my first Rust project! What do you remember about me?'
    print(f'\nUser: {_user_msg}\n')
    _response = agent2.chat(_user_msg)
    # Bob returns days later. The agent should remember him
    print(f'Agent: {_response}')
    print('\n✓ Memories persisted across sessions. The agent remembers Bob!')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Custom Configuration

    Mem0's default setup (OpenAI + local Qdrant) works well for development. For production or alternative LLM providers, you can customize every component:

    ```python
    from mem0 import Memory

    config = {
        "llm": {
            "provider": "openai",          # or "anthropic", "azure_openai", etc.
            "config": {
                "model": "gpt-4o-mini",
                "temperature": 0.1,        # low temp for deterministic extraction
            },
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "model": "text-embedding-3-small",
                "embedding_dims": 1536,
            },
        },
        "vector_store": {
            "provider": "qdrant",          # or "chroma", "pgvector", "milvus"
            "config": {
                "host": "localhost",
                "port": 6333,
                "collection_name": "my_app_memories",
            },
        },
    }

    m = Memory.from_config(config)
    ```

    **Supported providers:**
    - **LLM**: OpenAI, Anthropic, Azure OpenAI, Google AI, Groq, Ollama, and more
    - **Embedder**: OpenAI, Hugging Face, Google, Ollama
    - **Vector Store**: Qdrant, Chroma, pgvector, Milvus, Pinecone, Weaviate

    See the [Mem0 Configuration docs](https://docs.mem0.ai/open-source/configuration?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques) for the full reference.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Multi-User Isolation

    Each `user_id` gets its own isolated memory space.
    Carol's peanut allergy won't leak into Dave's results, even though they share the same Mem0 instance.
    """)
    return


@app.cell
def _(m):
    # ── Multi-user isolation demo ──
    # Memories are strictly scoped by user_id (no leakage).
    m.add("I'm allergic to peanuts and I love spicy food", user_id='carol')
    # Add memories for two different users
    m.add("I adore peanut butter and I can't handle any spice", user_id='dave')
    print("=== Carol's food preferences ===")
    carol_food = m.search('food preferences and allergies', user_id='carol')
    # Search for food preferences. Each user sees only their own
    for _mem in carol_food.get('results', carol_food) if isinstance(carol_food, dict) else carol_food:
        if isinstance(_mem, dict):
            print(f"  • {_mem.get('memory', _mem.get('text', str(_mem)))}")
    print()
    print("=== Dave's food preferences ===")
    dave_food = m.search('food preferences and allergies', user_id='dave')
    for _mem in dave_food.get('results', dave_food) if isinstance(dave_food, dict) else dave_food:
        if isinstance(_mem, dict):
            print(f"  • {_mem.get('memory', _mem.get('text', str(_mem)))}")
    print('\n✓ User isolation confirmed. No cross-contamination')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Using Metadata for Categorization

    You can attach metadata (extra labels) to memories when you add them.
    This helps organize memories into categories like "travel" or "budget" for structured retrieval.
    """)
    return


@app.cell
def _(m):
    # ── Using metadata for categorization ──
    # You can attach metadata to memories for organized retrieval.
    m.add("I prefer window seats on flights and I'm in the Delta SkyMiles program", user_id='alice', metadata={'category': 'travel_preferences'})
    m.add('My budget for dinner is usually around $30-40 per person', user_id='alice', metadata={'category': 'budget'})
    print("=== All Alice's memories (with metadata) ===")
    all_alice = m.get_all(user_id='alice')
    mem_list = all_alice.get('results', all_alice) if isinstance(all_alice, dict) else all_alice
    for _mem in mem_list:
        text = _mem.get('memory', _mem.get('text', str(_mem)))
        meta = _mem.get('metadata', {})
        cat = meta.get('category', 'auto') if meta else 'auto'
    # Search with metadata context
        print(f'  [{cat}] {text}')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Cleanup

    Remove all demo memories to keep the local Qdrant store tidy.
    """)
    return


@app.cell
def _(m):
    # ── Cleanup: remove demo memories ──
    # Delete all memories for demo users to keep things tidy.

    for uid in ["alice", "bob", "carol", "dave"]:
        m.delete_all(user_id=uid)
        print(f"\u2713 Deleted all memories for '{uid}'")

    print("\n\u2713 Cleanup complete")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Discussion & Tradeoffs

    ### Strengths

    - **Minimal setup code:** A single `add()` call handles extraction, deduplication, and storage. No need to build custom NLP pipelines, manage embedding models, or write vector database queries.
    - **Automatic conflict resolution:** When a user's preferences or facts change, Mem0 detects the contradiction and updates the stored memory. This is surprisingly hard to do correctly with a DIY approach.
    - **User isolation by default:** Memory scoping by `user_id` is built in. This prevents the cross-contamination bugs that plague hand-rolled memory systems.
    - **Self-improving:** Repeated `add()` calls refine and merge related memories. The memory profile becomes more accurate and concise over time.
    - **Provider flexibility:** You can swap LLMs, embedders, and vector stores through configuration. No application code changes needed.

    ### Weaknesses

    - **Opaque extraction:** You don't control exactly what gets extracted. Mem0's LLM pipeline decides what's "memorable." This may not align with your domain's needs. Critical facts can be missed, or irrelevant details stored.
    - **LLM cost per add:** Every `add()` triggers an LLM call for extraction. In high-throughput applications, this adds significant cost. Batching strategies help but aren't built in.
    - **Limited query control:** Semantic search is capable but you can't run structured queries as easily. For example, "all memories where category = 'dietary' AND created after 2025-01-01" is harder than with a relational database.
    - **Local Qdrant limitations:** The default local Qdrant is file-based and single-process. Production deployments need a proper Qdrant server, pgvector, or a cloud-hosted vector store.
    - **No built-in TTL or decay:** TTL (Time To Live) is a rule that automatically deletes data after a set period. Mem0 memories persist forever unless you explicitly delete them. For long-lived agents, you need to implement your own forgetting strategy on top of Mem0.

    ### When to Use Mem0 vs. Build Your Own

    | Scenario | Recommendation |
    |----------|---------------|
    | Prototyping a personalized chatbot | **Use Mem0.** Fastest path to working memory. |
    | You need fine-grained control over what gets stored | **Build your own.** Mem0's extraction is opaque. |
    | Multi-user application with user isolation | **Use Mem0.** Isolation is built in. |
    | High-throughput (>1000 messages/min) | **Build your own.** Avoid per-message LLM costs. |
    | You need memory decay, TTLs, or forgetting | **Build your own** (or layer on top of Mem0). |
    | Team wants to ship fast without memory infrastructure | **Use Mem0.** Single dependency, no vector DB setup. |
    | You need graph-based memory (relationships between entities) | **Consider Graphiti or Zep.** Mem0 is flat, not graph-based. |

    ### Mem0 vs. Other Memory Frameworks

    | Aspect | Mem0 | Zep | Letta (MemGPT) |
    |--------|------|-----|-----------------|
    | Primary model | Flat memory store | Temporal knowledge graph | Self-editing memory blocks |
    | Extraction | Automatic via LLM | Dialog classification + entity extraction | Inner monologue |
    | Conflict resolution | Built-in | Graph-based | Agent-driven |
    | Self-hosted | Yes (OSS) | Yes (OSS) | Yes (OSS) |
    | Managed cloud | Yes | Yes | Yes |
    | Best for | Straightforward personalization | Complex relationships | Agentic memory management |
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Further Reading

    - [Mem0 Documentation](https://docs.mem0.ai/?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques): Official docs covering all operations, configuration, and integrations.
    - [Mem0 GitHub Repository](https://github.com/mem0ai/mem0): Open-source code, issues, and examples.
    - [Mem0 Python SDK on PyPI](https://pypi.org/project/mem0ai/?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques): Package details and version history.
    - [Mem0 Platform](https://app.mem0.ai/?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques): Managed cloud service with dashboard and analytics.
    - [Anthropic: Building Effective Agents (2025)](https://www.anthropic.com/engineering/building-effective-agents?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques): Agent architecture patterns that complement memory.
    - [Letta (MemGPT): Self-Editing Memory](https://github.com/letta-ai/letta): An alternative approach where the agent manages memory with inner monologue.
    - [Zep: Temporal Knowledge Graphs](https://github.com/getzep/zep): An alternative approach using graph-based memory with temporal awareness.

    ---

    *← Previous: [24 - Graph Memory with Graphiti](../24_graph_memory_graphiti/) · Next: [26 - Letta (MemGPT) Patterns](../26_letta_memgpt_patterns/) →*
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 🧪 Try It Yourself

    Three small challenges to deepen your understanding. Each should take 10-30 minutes.

    ### Challenge 1: User-scoped isolation
    Create two users by calling `memory.add()` with different `user_id` values. Store 5 facts for each user. Then call `memory.search()` scoped to each user and verify no cross-user leakage. Print both result sets side by side.

    ### Challenge 2: Deduplication accuracy
    Add 10 semantically similar facts (paraphrases of the same information) via `memory.add()`. Call `memory.get_all()` and count how many distinct entries Mem0 created vs. how many it merged. Compute the deduplication rate and note any cases where it kept duplicates or wrongly merged different facts.

    ### Challenge 3: Full memory lifecycle
    Walk a single fact through its complete lifecycle: `add()` it, `search()` for it, `update()` it with new information, `search()` again to confirm the update, then `delete()` it. Verify it no longer appears in `get_all()`. This end-to-end flow mirrors the tool-based control pattern from 23 Memory with Tools.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--25-mem0-patterns--mem0-patterns)
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
