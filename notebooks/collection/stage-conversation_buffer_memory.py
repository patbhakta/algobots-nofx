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
    mo.md("# Conversation Buffer Memory\n\n> **The most basic form of agent memory: store the entire conversation word-for-word.**\n\nEvery AI agent needs memory. Without it, each turn is a blank slate. The agent can't reference what you said a minute ago, let alone hold a coherent multi-turn conversation.\n\nThink of a tape recorder that never pauses. It captures every word, and when the agent needs to reply, it replays the full tape. That's **Conversation Buffer Memory**. It's the foundation that every other memory technique builds on. The idea is straightforward:\n\n1. Keep an ordered list of messages.\n2. Send the *entire* list to the LLM on every turn.\n3. Append the response. Repeat.\n\nThis notebook shows you how to build it from scratch with the **Anthropic SDK** (Anthropic's Python library for calling Claude). You'll visualize the linear token-growth problem with **matplotlib**. You'll also compare the DIY version with **LangChain's built-in ConversationBufferMemory**.\n\n**By the end you'll understand:**\n- Why buffer memory is the default starting point for any agent.\n- How messages accumulate and why cost and latency grow linearly per turn.\n- When this approach breaks down and what to do next.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Key Concepts\n\n- **Message list**: An ordered list of `{role, content}` dicts. Roles are typically `user` and `assistant` (plus an optional `system` prompt).\n- **Role alternation**: The LLM relies on correct role sequencing to know who said what.\n- **Context injection**: The full message list is passed as the prompt on every API call. "Context" means the text the model reads before answering.\n- **Token counting**: Each message consumes tokens (word-pieces the model uses internally). The running total determines cost and whether you\'ll hit the context-window ceiling.\n- **Linear growth**: Every new turn adds tokens. *All* previous tokens are re-sent too. So cumulative token usage grows **O(n²)** across turns, where *n* is the number of turns. This means that doubling the turns roughly quadruples the total cost.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Architecture\n\n<p align="center">\n  <img src="../../images/diagrams/01_conversation_buffer_memory.svg" alt="diagram" width="720"/>\n</p>\n\n<details><summary>Mermaid source</summary>\n\n```mermaid\nsequenceDiagram\n    participant U as User\n    participant B as Buffer Memory\n    participant L as LLM (Claude)\n\n    U->>B: "Hi, I\'m Alice"\n    B->>B: Append {role: user, content: "Hi, I\'m Alice"}\n    B->>L: [msg1]\n    L-->>B: "Hello Alice! How can I help?"\n    B->>B: Append {role: assistant, content: "Hello Alice!..."}\n\n    U->>B: "What\'s my name?"\n    B->>B: Append {role: user, content: "What\'s my name?"}\n    B->>L: [msg1, msg2, msg3]\n    L-->>B: "Your name is Alice."\n    B->>B: Append {role: assistant, content: "Your name is Alice."}\n\n    Note over B: Buffer grows with every turn.<br/>All messages re-sent each call.\n```\n\n</details>')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Setup\n\nInstall dependencies and configure API access.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Import the Anthropic SDK and standard library helpers. The API key loads from a `.env` file.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Implementation\n\nWe'll build a minimal `ConversationBufferMemory` class that:\n1. Stores messages in a plain Python list.\n2. Exposes `add_user_message` / `add_assistant_message` helpers.\n3. Sends the full history to the Anthropic API on each call.\n4. Tracks token usage per turn for visualization later.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("Now we add the `chat` method and utility helpers. The `chat` method is where buffer memory does its work: it appends the user message, sends the **entire** message list to the API, and records token usage. Notice that `messages` (the full list) is passed every time. That's the defining trait of buffer memory.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Example Run\n\nA short multi-turn conversation shows buffer memory in action. The agent remembers everything because it re-reads the whole history every turn.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Inspect the raw message buffer. This is exactly what the LLM receives on each call.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## The Linear Token-Growth Problem\n\nWith buffer memory, **every previous message is re-sent on every turn**. Here's what that looks like:\n\n| Turn | Tokens sent to the LLM |\n|------|----------------------|\n| 1 | the first message only |\n| 2 | messages 1-3 |\n| 3 | messages 1-5 |\n| *n* | messages 1-(2n-1) |\n\nInput tokens per turn grow **linearly** with conversation length. The **cumulative** tokens used across the whole conversation grow **quadratically**. Let's prove it with a longer conversation and a chart.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("Plot input tokens per turn and cumulative usage. You'll see the linear and quadratic growth patterns clearly.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Persistence\n\nA production buffer memory must survive process restarts. The data structure is a list of dicts, so JSON serialization (converting it to a text file format) is straightforward.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## LangChain Comparison\n\nLangChain provides a built-in `ConversationBufferMemory` that does the same thing. Let's see how the framework version compares to our scratch implementation.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('**DIY vs. LangChain: side-by-side:**\n\n| Aspect | Our Implementation | LangChain `ConversationBufferMemory` |\n|--------|-------------------|--------------------------------------|\n| **Data structure** | `list[dict]` with `role`/`content` | `ChatMessageHistory` with typed message objects |\n| **API integration** | Direct `anthropic.Anthropic()` calls | Wrapped in `ConversationChain` |\n| **Token tracking** | Manual via `response.usage` | Available through callbacks |\n| **Persistence** | DIY JSON save/load | Built-in serialization options |\n| **Flexibility** | Full control over prompt assembly | Opinionated chain structure |\n| **Lines of code** | ~50 lines | ~5 lines (the framework does the rest) |\n\n**Takeaway:** LangChain is convenient for prototyping. Building from scratch gives you full control over token budgets, multi-model routing, and non-standard message formats.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Tradeoffs\n\n### When Conversation Buffer Memory Works Well\n- **Short conversations** (under 20 turns) where total tokens stay comfortably within the context window.\n- **Prototyping**: get something working in minutes before optimizing.\n- **Perfect recall required**: no information is ever dropped or summarized.\n\n### When It Breaks Down\n- **Long conversations**: input tokens per turn grow linearly. Cumulative cost grows quadratically.\n- **Cost-sensitive applications**: re-sending the entire history on every call is expensive.\n- **Latency-sensitive applications**: more input tokens means slower responses. Latency is the delay between your request and the model's reply.\n- **Context window limits**: eventually the buffer exceeds the model's maximum (for example, 200k tokens for Claude).\n\n### Cost Example\nConsider a 50-turn conversation where each turn adds ~100 tokens of new content:\n- Turn 1: ~100 input tokens\n- Turn 50: ~5,000 input tokens\n- **Total input tokens across all 50 turns: ~127,500** (vs. ~5,000 if you sent only the latest turn)\n\n### What's Next?\nThe rest of this series addresses these limitations:\n- **[02: Sliding Window Memory](../02_sliding_window_memory/)** keeps only the last *k* messages.\n- **[03: Summary Memory](../03_summary_memory/)** replaces old turns with an LLM-generated summary.\n- **[04: Summary Buffer Memory](../04_summary_buffer_memory/)** is a hybrid: summarize old messages, keep recent ones word-for-word.\n- **[05: Token Buffer Memory](../05_token_buffer_memory/)** trims to a strict token budget.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Further Reading\n\n- [Anthropic Messages API: Multi-turn Conversations](https://docs.anthropic.com/en/docs/build-with-claude/conversational-ai?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques)\n- [LangChain ConversationBufferMemory](https://python.langchain.com/docs/modules/memory/types/buffer?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques)\n- [LlamaIndex Chat Store](https://docs.llamaindex.ai/en/stable/module_guides/storing/chat_stores/?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques)\n- Anthropic\'s 7 Layers of Agent Memory (2026)\n- [Lilian Weng, "LLM Powered Autonomous Agents" (Memory section)](https://lilianweng.github.io/posts/2023-06-23-agent/?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques)\n\n---\n\n*Next up: 02: Sliding Window Memory ->*')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Clean up temporary files created during the demo.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## 🧪 Try It Yourself\n\nThree small challenges to deepen your understanding. Each should take 10-30 minutes.\n\n### Challenge 1: Multi-persona buffer\nCreate two separate `ConversationBufferMemory` instances with different system prompts (e.g., a tutor and a travel planner). Run five turns on each and compare how the buffer contents diverge. Pay attention to how the system prompt affects token counts.\n\n### Challenge 2: Measure the cost curve\nExtend the token-growth demo to 20 turns. Record `input_tokens` per turn, compute the cumulative cost in dollars (use Anthropic pricing for Claude Sonnet), and print a summary table. Compare the total cost against a hypothetical system that sends only the last 5 messages.\n\n### Challenge 3: Swap in a database backend\nReplace the JSON-based `save_conversation()` / `load_conversation()` with a SQLite backend. Store each message as a row with columns for role, content, and timestamp. Verify round-trip persistence still works. This prepares you for the patterns in 21 Cross-Session Memory.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--01-conversation-buffer-memory--conversation-buffer-memory)\n')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# SETUP (run separately): %pip install -q anthropic python-dotenv matplotlib langchain langchain-anthropic\n\nimport os\nimport json\nimport copy\nfrom dotenv import load_dotenv\n\nload_dotenv()  # reads ANTHROPIC_API_KEY from .env\n\nimport anthropic\n\nassert os.getenv("ANTHROPIC_API_KEY"), "Set ANTHROPIC_API_KEY in your .env file"\n\nclass ConversationBufferMemory:\n    """Minimal conversation buffer memory built on the Anthropic SDK."""\n\n    def __init__(\n        self,\n        model: str = "claude-sonnet-4-20250514",\n        system_prompt: str | None = None,\n        max_tokens: int = 1024,\n    ):\n        self.client = anthropic.Anthropic()\n        self.model = model\n        self.system_prompt = system_prompt\n        self.max_tokens = max_tokens\n\n        # Core data structure: the message buffer\n        self.messages: list[dict] = []\n\n        # Bookkeeping for the token-growth demo\n        self.turn_token_usage: list[dict] = []\n\n    # ── Message helpers ──────────────────────────────────────────────\n    def add_user_message(self, content: str) -> None:\n        self.messages.append({"role": "user", "content": content})\n\n    def add_assistant_message(self, content: str) -> None:\n        self.messages.append({"role": "assistant", "content": content})\n\n\n    # ── Chat ─────────────────────────────────────────────────────────\n    def chat(self, user_input: str) -> str:\n        """Send a message and get a response. The *entire* buffer is sent."""\n        self.add_user_message(user_input)\n\n        kwargs = dict(\n            model=self.model,\n            max_tokens=self.max_tokens,\n            messages=self.messages,   # <-- full history every time\n        )\n        if self.system_prompt:\n            kwargs["system"] = self.system_prompt\n\n        response = self.client.messages.create(**kwargs)\n\n        assistant_text = response.content[0].text\n        self.add_assistant_message(assistant_text)\n\n        # Record token usage for this turn\n        self.turn_token_usage.append({\n            "turn": len(self.turn_token_usage) + 1,\n            "input_tokens": response.usage.input_tokens,\n            "output_tokens": response.usage.output_tokens,\n        })\n\n        return assistant_text\n\n    # ── Utilities ────────────────────────────────────────────────────\n    def get_history(self) -> list[dict]:\n        return copy.deepcopy(self.messages)\n\n    def clear(self) -> None:\n        self.messages.clear()\n        self.turn_token_usage.clear()\n\n    def __len__(self) -> int:\n        return len(self.messages)\n\n    def __repr__(self) -> str:\n        return f"ConversationBufferMemory({len(self.messages)} messages)"\n\nmemory = ConversationBufferMemory(\n    system_prompt="You are a helpful, concise assistant. Keep replies under 2 sentences.",\n)\n\n# Multi-turn conversation\nexchanges = [\n    "Hi! My name is Alice and I\'m a machine-learning engineer.",\n    "I\'m working on a project about agent memory. Any tips?",\n    "What\'s my name and what do I do?",  # recall test\n]\n\nfor msg in exchanges:\n    print(f"👤 User:  {msg}")\n    reply = memory.chat(msg)\n    print(f"🤖 Agent: {reply}\\n")\n\nprint(f"Buffer now contains {len(memory)} messages.")\n\n# Peek at the raw message buffer\nfor i, msg in enumerate(memory.get_history()):\n    role_label = "USER" if msg["role"] == "user" else "ASST"\n    # Truncate long messages for display\n    preview = msg["content"][:80] + ("..." if len(msg["content"]) > 80 else "")\n    print(f"  [{i}] {role_label}: {preview}")\n\n# Run a longer conversation to see the growth curve\nmemory_demo = ConversationBufferMemory(\n    system_prompt="You are a helpful assistant. Keep answers to 1-2 sentences.",\n)\n\ndemo_messages = [\n    "Hello! I\'m Bob.",\n    "I live in San Francisco.",\n    "I have a golden retriever named Max.",\n    "My favorite programming language is Python.",\n    "I work at a startup that builds AI tools.",\n    "We\'re building a chatbot with memory capabilities.",\n    "Our team has 12 engineers.",\n    "We use Claude as our primary LLM.",\n    "What do you know about me so far?",\n    "Summarize everything you remember about me in a list.",\n]\n\nfor msg in demo_messages:\n    reply = memory_demo.chat(msg)\n\nprint(f"Completed {len(memory_demo.turn_token_usage)} turns.")\nprint("\\nToken usage per turn:")\nfor t in memory_demo.turn_token_usage:\n    print(f"  Turn {t[\'turn\']:2d}: {t[\'input_tokens\']:5d} input tokens, {t[\'output_tokens\']:4d} output tokens")\n\nimport matplotlib.pyplot as plt\nimport numpy as np\n\nturns = [t["turn"] for t in memory_demo.turn_token_usage]\ninput_tokens = [t["input_tokens"] for t in memory_demo.turn_token_usage]\ncumulative = np.cumsum(input_tokens)\n\nfig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))\n\n# Left: input tokens per turn (linear growth)\nax1.bar(turns, input_tokens, color="#6366f1", alpha=0.85)\nax1.set_xlabel("Turn")\nax1.set_ylabel("Input Tokens")\nax1.set_title("Input Tokens per Turn (Linear Growth)")\nax1.set_xticks(turns)\n\n# Right: cumulative input tokens (quadratic growth)\nax2.plot(turns, cumulative, "o-", color="#f43f5e", linewidth=2, markersize=6)\nax2.fill_between(turns, cumulative, alpha=0.15, color="#f43f5e")\nax2.set_xlabel("Turn")\nax2.set_ylabel("Cumulative Input Tokens")\nax2.set_title("Cumulative Token Usage (Quadratic Growth)")\nax2.set_xticks(turns)\n\nplt.tight_layout()\nplt.savefig("token_growth.png", dpi=150, bbox_inches="tight")\nplt.show()\n\nprint(f"\\nTotal input tokens across all turns: {int(cumulative[-1]):,}")\nprint(f"If using a window/summary approach, this could be drastically reduced.")\n\ndef save_conversation(memory: ConversationBufferMemory, path: str) -> None:\n    """Persist the message buffer to a JSON file."""\n    with open(path, "w") as f:\n        json.dump(memory.get_history(), f, indent=2)\n    print(f"Saved {len(memory)} messages → {path}")\n\n\ndef load_conversation(path: str, **kwargs) -> ConversationBufferMemory:\n    """Restore a ConversationBufferMemory from a JSON file."""\n    with open(path) as f:\n        messages = json.load(f)\n    mem = ConversationBufferMemory(**kwargs)\n    mem.messages = messages\n    print(f"Loaded {len(messages)} messages ← {path}")\n    return mem\n\n\n# Demo round-trip\nsave_conversation(memory, "conversation.json")\nloaded = load_conversation(\n    "conversation.json",\n    system_prompt="You are a helpful, concise assistant. Keep replies under 2 sentences.",\n)\n\n# Verify the loaded memory still works\nreply = loaded.chat("Remind me - what project was I working on?")\nprint(f"\\n🤖 Agent (from loaded memory): {reply}")\n\nfrom langchain_anthropic import ChatAnthropic\nfrom langchain.memory import ConversationBufferMemory as LCBufferMemory\nfrom langchain.chains import ConversationChain\n\nllm = ChatAnthropic(model="claude-sonnet-4-20250514", max_tokens=1024)\n\nlc_memory = LCBufferMemory(return_messages=True)\n\nchain = ConversationChain(\n    llm=llm,\n    memory=lc_memory,\n    verbose=False,\n)\n\n# Same conversation\nprint("👤:", "Hi, my name is Charlie.")\nprint("🤖:", chain.predict(input="Hi, my name is Charlie."), "\\n")\n\nprint("👤:", "I\'m building a knowledge graph for my company.")\nprint("🤖:", chain.predict(input="I\'m building a knowledge graph for my company."), "\\n")\n\nprint("👤:", "What\'s my name and what am I building?")\nprint("🤖:", chain.predict(input="What\'s my name and what am I building?"), "\\n")\n\n# Inspect LangChain\'s internal buffer\nprint("--- LangChain buffer contents ---")\nfor msg in lc_memory.chat_memory.messages:\n    role = msg.__class__.__name__.replace("Message", "")\n    preview = msg.content[:80] + ("..." if len(msg.content) > 80 else "")\n    print(f"  {role}: {preview}")\n\nfor f in ["conversation.json", "token_growth.png"]:\n    if os.path.exists(f):\n        os.remove(f)', language="python", label="Recovered notebook code")
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
