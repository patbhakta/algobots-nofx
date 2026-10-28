import marimo
app = marimo.App(width="medium")

@app.cell
def _():
    import marimo as mo
    return (mo,)

@app.cell
def _(mo):
    mo.md("## Recovered sequential notebook\nThe original conversion failed graph validation. Edit the recovered code and press Run. Dependencies and provider credentials must be available in this runtime.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("# Memory with Tools (Memory-as-a-Tool)\n\n> **Give the agent callable memory tools (`save_memory`, `search_memory`, `update_memory`, `delete_memory`) and let it decide when and what to remember.**\n\nThink of a librarian who decides what books to shelve, which ones to look up for you, and which outdated ones to discard. The librarian doesn't follow a fixed routine. They use their judgment based on what you ask. Memory-as-a-Tool gives an AI agent the same kind of control over its own memory. The analogy breaks down in one way: the agent also writes the books (it creates facts from conversations).\n\nMost agent memory systems operate invisibly. A framework intercepts every message, embeds it, and stuffs retrieved chunks into the prompt. The agent has no say in what gets stored. It can't update stale facts. It can't choose to forget.\n\nThis works for basic chatbots. But it breaks down when the agent needs to be selective. For example: storing a user's dietary restriction while ignoring small talk. Or correcting a previously saved fact.\n\nThe **Memory-as-a-Tool** pattern flips the model. Memory operations become tool schemas (structured descriptions of callable functions). The LLM decides during generation whether to call `save_memory`, `search_memory`, `update_memory`, or `delete_memory`. This uses the same tool-use loop that powers every modern agent. The memory tools sit alongside other tools like web search or code execution.\n\nThis notebook shows you how to build it from scratch with the **Anthropic SDK** (Anthropic's Python library for calling Claude). You'll define four memory tools, build a vector-backed memory store, and wire up the agentic tool-use loop.\n\n**By the end you'll understand:**\n- How to define memory operations as tool schemas.\n- How to build a memory store with embedding-based semantic search.\n- How the agentic loop dispatches tool calls and feeds results back.\n- When agent-driven memory beats hidden pipeline memory.\n")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Key Concepts\n\n- **Tool schema**: A structured description of a callable function. It includes the tool's name, what it does, and what inputs it expects (as a JSON Schema). The LLM reads these schemas and decides which tools to call.\n- **Memory CRUD**: The four core operations for managing stored data. CRUD stands for Create, Read, Update, Delete. Here we expose them as `save_memory`, `search_memory`, `update_memory`, and `delete_memory`.\n- **Agentic tool-use loop**: The cycle where the LLM generates a response, optionally requests a tool call, receives the result, and continues generating. This loop repeats until the model produces a final text response with no tool calls.\n- **`tool_use` / `tool_result` blocks**: In Anthropic's API, when the model wants to call a tool, it emits a `tool_use` content block. Your code executes the tool and returns a `tool_result` block. These blocks sit inside the normal message list.\n- **Embedding**: A list of numbers (a vector) that captures the meaning of a piece of text. Similar texts produce vectors that point in similar directions. We use embeddings to find memories that match a search query.\n- **Cosine similarity**: A way to measure how similar two vectors are. It computes the cosine of the angle between them. A value of 1.0 means identical direction. A value of 0.0 means unrelated.\n- **Semantic search**: Finding stored items by meaning rather than exact keyword match. We embed the query, then find stored memories whose embeddings have the highest cosine similarity.\n- **Agent-driven memory**: The LLM decides on its own when to store, retrieve, modify, or discard information. No external heuristics force memory writes on every turn.\n")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Architecture\n\n<p align="center">\n  <img src="../../images/diagrams/23_memory_with_tools.svg" alt="Memory with Tools architecture diagram" width="720"/>\n</p>\n\nThe diagram shows the full flow:\n\n1. The user sends a message. The system prompt includes tool definitions for all four memory tools.\n2. The LLM generates a response. If it decides memory is relevant, it emits a `tool_use` block (for example, `search_memory({"query": "dietary restrictions"})`).\n3. Your application executes the tool call against the memory store and returns a `tool_result` block.\n4. The LLM sees the result. It can make another tool call (chaining) or produce a final text response.\n5. After responding, the LLM may also call `save_memory` to store new facts. All of this happens within the same turn.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Setup\n\nInstall dependencies and configure API access. You'll need an `ANTHROPIC_API_KEY` environment variable (your secret key for calling the Anthropic API). We also use `numpy` for cosine similarity calculations in the memory store.\n")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Import the Anthropic SDK and standard library helpers. The API key loads from a `.env` file.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Implementation\n\nWe'll build the Memory-as-a-Tool system in four steps:\n\n1. Define the four memory tool schemas.\n2. Build a `MemoryStore` backend with embedding-based search.\n3. Write a tool dispatcher that routes tool calls to memory operations.\n4. Wire up the agentic loop that drives the whole system.\n")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Step 1: Define Memory Tool Schemas\n\nEach tool schema tells the LLM what the tool does and what inputs it expects. Anthropic's format uses `input_schema` with standard JSON Schema. Clear descriptions guide the model on when to call each tool.\n")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Now we define the `update_memory` and `delete_memory` tools.\nThese let the agent correct stale facts and remove information the user wants forgotten.\nTogether with `save_memory` and `search_memory`, they form a complete CRUD interface.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Step 2: Build the Memory Store\n\nThink of a filing cabinet where each folder has a label written in invisible ink. To find the right folder, you describe what you're looking for, and a helper compares your description against every label. That's semantic search.\n\nOur `MemoryStore` converts text into vectors (lists of numbers that capture meaning). When you search, we embed the query and find stored memories with the highest cosine similarity.\n\nFor this prototype, we use a lightweight hash-based embedding. In production, swap it for a real embedding model like `voyage-3`, `text-embedding-3-small`, or a sentence-transformer. Each memory gets a unique ID, a timestamp, optional tags, and its embedding vector.\n")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('The `search` method is where semantic retrieval happens.\nIt embeds the query, then compares it against every stored memory using cosine similarity (a measure of how similar two vectors are).\nResults come back ranked by relevance, with the best matches first.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('The remaining CRUD methods handle updates, deletes, and listing.\nWhen you update a memory, the embedding gets recalculated so future searches reflect the new content.\nThe `list_all` method strips out embeddings for clean display.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Step 3: Tool Dispatcher\n\nThe dispatcher is the bridge between the LLM's tool calls and the memory store. When the LLM emits a `tool_use` block, we read the tool name and inputs, call the right method on `MemoryStore`, and format the result as a string.\n")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Step 4: System Prompt\n\nThe system prompt guides the model's memory behavior. It tells the model when to save, search, update, and delete. Without clear instructions, the model might ignore the memory tools or use them at the wrong times.\n")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Step 5: The Agentic Tool-Use Loop\n\nThink of a phone call where you can put someone on hold to look something up. The caller (user) asks a question. You (the agent) pause the conversation, check your files, come back, and answer. If you need more information, you can pause again. The call ends when you give a final answer.\n\nThe agentic loop works the same way. The LLM generates a response. If it includes a `tool_use` block, we execute the tool and feed the result back. The loop continues until the model produces a final `end_turn` response.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Example Run\n\nLet's run a multi-turn conversation that exercises all four memory operations. We'll:\n1. Share some personal facts (the agent should save them).\n2. Ask a question that requires memory recall (the agent should search).\n3. Correct a fact (the agent should update).\n4. Ask the agent to forget something (the agent should delete).\n")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("Let's inspect what's in the memory store after this conversation.\n")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Tool Chaining\n\nOne strength of this pattern is that the agent can chain tool calls in a single turn. For example, it might search for an old fact, find it's outdated, and update it. All before sending a final response. Let's see this in action.\n")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Tradeoffs\n\n### When Memory-as-a-Tool Works Well\n\n- **Selective memory**: The agent stores only what matters. A food preference gets saved. "How\'s the weather?" does not. This keeps the memory store clean and relevant.\n- **Self-correcting**: The agent can search, find stale facts, and update them in one turn. Pipeline-based memory systems often store duplicates or contradictions.\n- **Transparent**: Every memory operation shows up as a tool call. You can log, audit, and debug exactly what the agent remembered and when.\n- **Composable**: Memory tools sit alongside other tools. The agent can search memory, call a weather API, and save the result. All in one turn.\n\n### When It Breaks Down\n\n- **LLM reliability**: The agent might forget to save something important. Or it might save too much. The quality of memory management depends on the model\'s judgment.\n- **Latency**: Each tool call adds a round trip. If the agent chains three memory operations before answering, that\'s three extra API calls. This adds latency (the delay between the user\'s question and the final answer).\n- **Token cost**: Tool definitions consume tokens in every request. Four tool schemas add roughly 500-800 tokens to each call. For short conversations, this overhead may not be worth it.\n- **No background processing**: The agent only manages memory during active turns. It won\'t consolidate or clean up memories between conversations unless you build that separately.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Further Reading\n\n- [Anthropic Tool Use Documentation](https://docs.anthropic.com/en/docs/build-with-claude/tool-use?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques): Official guide to defining tools, processing `tool_use`/`tool_result` blocks, and building agentic loops with Claude.\n- [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques): OpenAI\'s equivalent pattern for exposing callable functions to GPT models during generation.\n- [Packer et al., "MemGPT: Towards LLMs as Operating Systems," 2023 (arXiv:2310.08560)](https://arxiv.org/abs/2310.08560): The foundational paper on treating memory management as agent actions. Describes explicit read/write tools for a virtual memory hierarchy.\n- [Anthropic: Building Effective Agents (2025)](https://www.anthropic.com/engineering/building-effective-agents?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques): Architectural patterns for production agents, including tool design principles.\n- [Zep Memory Tools Integration](https://docs.getzep.com?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques): A production memory service that exposes memory as tool-callable APIs with automatic fact extraction.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('*\\u2190 Previous: [22 - Multi-Agent Shared Memory](../22_multi_agent_shared_memory/) \\u00b7 Next: [24 - Graph Memory with Graphiti](../24_graph_memory_graphiti/) \\u2192*\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## 🧪 Try It Yourself\n\nThree small challenges to deepen your understanding. Each should take 10-30 minutes.\n\n### Challenge 1: Memory tagging tool\nAdd a fifth tool, `tag_memory`, to `memory_tools` that lets the agent assign a topic label to a stored memory. Update `dispatch_tool()` and `MemoryStore` to support tags. Run a conversation and verify the agent uses tags to categorize its memories.\n\n### Challenge 2: Tool usage frequency analysis\nRun a 20-turn conversation with `chat_with_memory()`. Count how many times the agent calls each tool (save, search, update, delete). Print a summary table. Identify which turns trigger memory saves vs. searches and whether the agent ever updates or deletes memories unprompted.\n\n### Challenge 3: Agent-controlled vs. automatic memory\nRun the same 15-turn conversation twice: once with the tool-based approach from this notebook, and once with automatic entity extraction from 07 Entity Memory. After each run, ask 10 recall questions. Compare which approach stores more relevant facts and which answers more questions correctly.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--23-memory-with-tools--memory-with-tools)\n')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# SETUP (run separately): %pip install -q anthropic python-dotenv numpy\n\nimport os\nimport json\nimport uuid\nfrom datetime import datetime, timezone\n\nimport numpy as np\nfrom dotenv import load_dotenv\nimport anthropic\n\nload_dotenv()  # reads ANTHROPIC_API_KEY from .env\n\nclient = anthropic.Anthropic()\n\nMODEL = "claude-sonnet-4-20250514"\n\nassert os.getenv("ANTHROPIC_API_KEY"), "Set ANTHROPIC_API_KEY in your .env file"\n\nmemory_tools = [\n    {\n        "name": "save_memory",\n        "description": (\n            "Save an important fact, preference, or piece of information to "\n            "long-term memory. Use this when the user shares something worth "\n            "remembering for future conversations: personal details, preferences, "\n            "goals, or corrections to previous facts."\n        ),\n        "input_schema": {\n            "type": "object",\n            "properties": {\n                "content": {\n                    "type": "string",\n                    "description": "The fact or information to remember.",\n                },\n                "tags": {\n                    "type": "array",\n                    "items": {"type": "string"},\n                    "description": "Optional category tags (e.g. \'preference\', \'personal\', \'work\').",\n                },\n            },\n            "required": ["content"],\n        },\n    },\n    {\n        "name": "search_memory",\n        "description": (\n            "Search long-term memory for facts relevant to a query. Use this "\n            "before answering questions that might benefit from previously stored "\n            "context, such as user preferences or past conversations."\n        ),\n        "input_schema": {\n            "type": "object",\n            "properties": {\n                "query": {\n                    "type": "string",\n                    "description": "The search query describing what to look for.",\n                },\n                "top_k": {\n                    "type": "integer",\n                    "description": "Maximum number of results to return. Defaults to 5.",\n                    "default": 5,\n                },\n            },\n            "required": ["query"],\n        },\n    }\n]\n\nmemory_tools += [\n    {\n        "name": "update_memory",\n        "description": (\n            "Update an existing memory by its ID. Use this when the user corrects "\n            "a previously stored fact or when information changes. Search for the "\n            "memory first to get its ID."\n        ),\n        "input_schema": {\n            "type": "object",\n            "properties": {\n                "memory_id": {\n                    "type": "string",\n                    "description": "The ID of the memory to update.",\n                },\n                "new_content": {\n                    "type": "string",\n                    "description": "The updated fact or information.",\n                },\n            },\n            "required": ["memory_id", "new_content"],\n        },\n    },\n    {\n        "name": "delete_memory",\n        "description": (\n            "Delete a memory by its ID. Use this when stored information is "\n            "no longer true, relevant, or when the user asks you to forget something."\n        ),\n        "input_schema": {\n            "type": "object",\n            "properties": {\n                "memory_id": {\n                    "type": "string",\n                    "description": "The ID of the memory to delete.",\n                },\n            },\n            "required": ["memory_id"],\n        },\n    },\n]\n\nprint(f"Defined {len(memory_tools)} memory tools:")\nfor tool in memory_tools:\n    print(f"  - {tool[\'name\']}: {tool[\'description\'][:60]}...")\n\nclass MemoryStore:\n    """Vector-backed memory store with CRUD operations."""\n\n    def __init__(self):\n        self.memories: dict[str, dict] = {}  # memory_id -> record\n\n    def _simple_embed(self, text: str) -> list[float]:\n        """Lightweight embedding using character-level hashing.\n\n        This is a prototype. It captures word overlap reasonably well\n        for short texts. For production, use a proper embedding model\n        like voyage-3, text-embedding-3-small, or sentence-transformers.\n        """\n        dims = 128\n        vec = np.zeros(dims)\n        words = text.lower().split()\n        for word in words:\n            # Hash each word to a set of dimensions and increment\n            h = hash(word)\n            for i in range(3):  # each word activates 3 dimensions\n                idx = abs(h + i * 7919) % dims\n                vec[idx] += 1.0\n        # Normalize to unit length\n        norm = np.linalg.norm(vec)\n        if norm > 0:\n            vec = vec / norm\n        return vec.tolist()\n\n    def save(self, content: str, tags: list[str] | None = None) -> str:\n        """Store a new memory. Returns the memory ID."""\n        memory_id = str(uuid.uuid4())[:8]\n        self.memories[memory_id] = {\n            "id": memory_id,\n            "content": content,\n            "tags": tags or [],\n            "created_at": datetime.now(timezone.utc).isoformat(),\n            "embedding": self._simple_embed(content),\n        }\n        return memory_id\n\n    def search(self, query: str, top_k: int = 5) -> list[dict]:\n        """Find memories most similar to the query."""\n        if not self.memories:\n            return []\n        query_vec = np.array(self._simple_embed(query))\n        scored = []\n        for mem in self.memories.values():\n            mem_vec = np.array(mem["embedding"])\n            # Cosine similarity (vectors are already normalized)\n            similarity = float(np.dot(query_vec, mem_vec))\n            scored.append((similarity, mem))\n        scored.sort(key=lambda x: x[0], reverse=True)\n        results = []\n        for score, mem in scored[:top_k]:\n            results.append({\n                "id": mem["id"],\n                "content": mem["content"],\n                "tags": mem["tags"],\n                "similarity": round(score, 3),\n                "created_at": mem["created_at"],\n            })\n        return results\n\n    def update(self, memory_id: str, new_content: str) -> bool:\n        """Update an existing memory\'s content. Returns True if found."""\n        if memory_id not in self.memories:\n            return False\n        self.memories[memory_id]["content"] = new_content\n        self.memories[memory_id]["embedding"] = self._simple_embed(new_content)\n        return True\n\n    def delete(self, memory_id: str) -> bool:\n        """Remove a memory by ID. Returns True if found."""\n        if memory_id not in self.memories:\n            return False\n        del self.memories[memory_id]\n        return True\n\n    def list_all(self) -> list[dict]:\n        """Return all memories (without embeddings, for display)."""\n        return [\n            {"id": m["id"], "content": m["content"], "tags": m["tags"]}\n            for m in self.memories.values()\n        ]\n\n\n# Quick test\nstore = MemoryStore()\ntest_id = store.save("Alice is a machine-learning engineer.", tags=["personal"])\nprint(f"Saved memory with ID: {test_id}")\nresults = store.search("What does Alice do for work?")\nprint(f"Search results: {json.dumps(results, indent=2)}")\n\ndef dispatch_tool(tool_name: str, tool_input: dict, store: MemoryStore) -> str:\n    """Execute a memory tool call and return a string result."""\n    if tool_name == "save_memory":\n        memory_id = store.save(\n            content=tool_input["content"],\n            tags=tool_input.get("tags"),\n        )\n        return json.dumps({"status": "saved", "memory_id": memory_id})\n\n    elif tool_name == "search_memory":\n        results = store.search(\n            query=tool_input["query"],\n            top_k=tool_input.get("top_k", 5),\n        )\n        return json.dumps({"results": results, "count": len(results)})\n\n    elif tool_name == "update_memory":\n        success = store.update(\n            memory_id=tool_input["memory_id"],\n            new_content=tool_input["new_content"],\n        )\n        status = "updated" if success else "not_found"\n        return json.dumps({"status": status})\n\n    elif tool_name == "delete_memory":\n        success = store.delete(memory_id=tool_input["memory_id"])\n        status = "deleted" if success else "not_found"\n        return json.dumps({"status": status})\n\n    else:\n        return json.dumps({"error": f"Unknown tool: {tool_name}"})\n\n\n# Quick test: dispatch a save call\nresult = dispatch_tool("save_memory", {"content": "Bob likes Thai food", "tags": ["preference"]}, store)\nprint(f"Dispatch result: {result}")\n\nSYSTEM_PROMPT = """You are a helpful assistant with long-term memory.\n\nYou have four memory tools available:\n\nWHEN TO SAVE:\n- Save when the user shares personal facts, preferences, or important details.\n- Save corrections to previously known information.\n- Do NOT save greetings, small talk, or temporary context.\n\nWHEN TO SEARCH:\n- Search before answering questions that might benefit from prior context.\n- Search when the user asks "do you remember" or references past conversations.\n\nWHEN TO UPDATE:\n- Update when the user corrects a previously stored fact.\n- Search first to find the memory ID, then update it.\n\nWHEN TO DELETE:\n- Delete when stored information is explicitly wrong or the user asks you to forget.\n\nKeep responses concise. When you use memory tools, briefly mention what you did\n(e.g. "I\'ve saved that to memory" or "Let me check my memory")."""\n\nprint("System prompt configured.")\n\ndef chat_with_memory(\n    user_message: str,\n    messages: list[dict],\n    store: MemoryStore,\n) -> tuple[str, list[dict]]:\n    """Send a message through the agentic loop with memory tools.\n\n    Returns the assistant\'s final text and the updated message list.\n    """\n    messages.append({"role": "user", "content": user_message})\n\n    while True:\n        response = client.messages.create(\n            model=MODEL,\n            max_tokens=1024,\n            system=SYSTEM_PROMPT,\n            tools=memory_tools,\n            messages=messages,\n        )\n\n        # Add the assistant\'s full response to history\n        messages.append({"role": "assistant", "content": response.content})\n\n        # If the model didn\'t call any tools, we\'re done\n        if response.stop_reason == "end_turn":\n            # Extract the final text from the response\n            final_text = ""\n            for block in response.content:\n                if block.type == "text":\n                    final_text += block.text\n            return final_text, messages\n\n        # Process each tool call in the response\n        tool_results = []\n        for block in response.content:\n            if block.type == "tool_use":\n                print(f"  [tool] {block.name}({json.dumps(block.input)[:80]})")\n                result = dispatch_tool(block.name, block.input, store)\n                print(f"  [result] {result[:100]}")\n                tool_results.append({\n                    "type": "tool_result",\n                    "tool_use_id": block.id,\n                    "content": result,\n                })\n\n        # Feed tool results back to the model\n        messages.append({"role": "user", "content": tool_results})\n\n\nprint("Agentic loop ready.")\n\n# Fresh memory store and conversation\nstore = MemoryStore()\nmessages = []\n\nexchanges = [\n    "Hi! My name is Alice and I\'m a machine-learning engineer at Anthropic.",\n    "I\'m allergic to peanuts and I prefer vegetarian food.",\n    "What do you remember about me?",\n    "Actually, I moved to a new company. I now work at DeepMind.",\n    "Please forget about my food allergy. I\'d rather not have that stored.",\n    "What do you know about me now?",\n]\n\nfor user_msg in exchanges:\n    print(f"\\n{\'=\'*60}")\n    print(f"User: {user_msg}")\n    print("-" * 60)\n    reply, messages = chat_with_memory(user_msg, messages, store)\n    print(f"\\nAssistant: {reply}")\n\nprint("Current memory store contents:")\nprint("-" * 40)\nfor mem in store.list_all():\n    print(f"  [{mem[\'id\']}] {mem[\'content\']}")\n    if mem[\'tags\']:\n        print(f"           tags: {mem[\'tags\']}")\nprint(f"\\nTotal memories: {len(store.memories)}")\n\n# Continue the same conversation\nuser_msg = "Actually, my name changed too. I go by Ali now, not Alice."\nprint(f"User: {user_msg}")\nprint("-" * 60)\nreply, messages = chat_with_memory(user_msg, messages, store)\nprint(f"\\nAssistant: {reply}")\n\nprint("\\nMemory store after update:")\nfor mem in store.list_all():\n    print(f"  [{mem[\'id\']}] {mem[\'content\']}")', language="python", label="Recovered notebook code")
    run_recovered = mo.ui.run_button(label="Run recovered notebook")
    mo.vstack([recovered_code, run_recovered])
    return recovered_code, run_recovered

@app.cell
def _(mo, recovered_code, run_recovered):
    mo.stop(not run_recovered.value)
    import os
    import subprocess
    import sys
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory(prefix="marimo-recovered-") as _tmp:
        _script = Path(_tmp) / "notebook.py"
        _tail = "\nimport matplotlib.pyplot as _plt\nfrom pathlib import Path as _Path\nfor _n in _plt.get_fignums():\n    _plt.figure(_n).savefig(_Path(" + repr(_tmp) + ") / (str(_n) + '.png'))\n"
        _runner = "import ast, asyncio, inspect\n_result = eval(compile(" + repr(recovered_code.value) + ", '<notebook>', 'exec', flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT))\nif inspect.isawaitable(_result): asyncio.run(_result)\n"
        _script.write_text(_runner + _tail)
        try:
            _run = subprocess.run([sys.executable, str(_script)], capture_output=True, text=True, timeout=90, env={**os.environ, "MPLBACKEND": "Agg"})
            _outputs = [mo.md(f"Exit status: **{_run.returncode}**"), mo.plain_text(_run.stdout + _run.stderr)]
            _outputs += [mo.image(_p.read_bytes()) for _p in sorted(Path(_tmp).glob("*.png"))]
            mo.output.replace(mo.vstack(_outputs))
        except subprocess.TimeoutExpired:
            mo.output.replace(mo.md("Execution exceeded 90 seconds; reduce the workload before retrying."))
    return

if __name__ == "__main__":
    app.run()
