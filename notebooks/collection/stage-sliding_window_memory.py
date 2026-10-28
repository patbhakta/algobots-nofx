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
    mo.md("# Sliding Window Memory\n\n> **Keep only the last *k* turns: the most direct way to bound memory cost while staying conversationally coherent.**\n\nIn the [previous notebook](../01_conversation_buffer_memory/conversation_buffer_memory.ipynb) we saw that **Conversation Buffer Memory** stores everything. That causes input tokens to grow linearly per turn and cumulative cost to grow quadratically. For most chat applications, that's wasteful. Users rarely reference something they said 30 turns ago.\n\nImagine a whiteboard that only fits five sticky notes. When you add a sixth, you peel off the oldest one and toss it. **Sliding Window Memory** works the same way. It keeps a fixed-size window of the most recent messages and discards everything older. The last *k* messages are always available, but older messages are gone.\n\n**By the end of this notebook you'll understand:**\n- How to build a deque-based sliding window from scratch with the Anthropic SDK.\n- The precise tradeoff between window size, recall ability, and token cost.\n- How to run a small evaluation that measures recall at different window sizes.\n- When sliding window memory is the right (and wrong) choice.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Key Concepts\n\n- **Window size *k***: The maximum number of messages retained. A larger *k* means better recall but higher token cost.\n- **FIFO eviction**: FIFO stands for "first-in, first-out." When `len(messages) > k`, the oldest message drops from the front. The window "slides" forward.\n- **`collections.deque`**: Python\'s double-ended queue with a `maxlen` parameter. It\'s a natural fit: appending to a full deque automatically discards the oldest item.\n- **Recency bias**: By design, the agent remembers recent context and forgets older context. This is a feature, not a bug, when recent context is what matters most.\n- **Message-count vs. turn-count windows**: A message window of *k* counts each message individually (user or assistant). A turn window of *k* keeps the last *k* user-assistant pairs intact. Turn-count windows avoid orphaned messages (a response without its question).\n- **Constant token cost**: Unlike buffer memory, per-turn token cost is bounded by the window size. This gives you predictable latency and cost.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Architecture\n\n<p align="center">\n  <img src="../../images/diagrams/02_sliding_window_memory.svg" alt="diagram" width="720"/>\n</p>\n\n<details><summary>Mermaid source</summary>\n\n```mermaid\nsequenceDiagram\n    participant U as User\n    participant W as Sliding Window (k=4 messages)\n    participant L as LLM (Claude)\n\n    Note over W: Window: []\n\n    U->>W: "Hi, I\'m Alice" (msg 1)\n    W->>L: [msg1]\n    L-->>W: "Hello Alice!" (msg 2)\n    Note over W: Window: [msg1, msg2]\n\n    U->>W: "I like Python" (msg 3)\n    W->>L: [msg1, msg2, msg3]\n    L-->>W: "Python is great!" (msg 4)\n    Note over W: Window: [msg1, msg2, msg3, msg4] - FULL\n\n    U->>W: "What\'s my name?" (msg 5)\n    Note over W: ⚠ Window full → drop msg1\n    W->>W: Evict msg1, append msg5\n    W->>L: [msg2, msg3, msg4, msg5]\n    L-->>W: "Your name is Alice." (msg 6)\n    Note over W: Drop msg2 → Window: [msg3, msg4, msg5, msg6]\n\n    U->>W: "What language do I like?"\n    Note over W: msg3 ("I like Python") still<br/>in window → agent remembers\n    W->>L: [msg4, msg5, msg6, msg7]\n    L-->>W: "You said you like Python!"\n    Note over W: Eventually msg3 slides out<br/>and that fact is forgotten\n```\n\n</details>')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Setup\n\nImport the Anthropic SDK and standard helpers. We also bring in `deque` from Python\'s `collections` module. A **deque** ("deck") is a double-ended queue that can hold a fixed number of items. When you add one more, the oldest item drops off automatically.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Core Implementation\n\nThe key insight: Python's `collections.deque(maxlen=k)` gives us sliding-window behavior for free. When you `append()` to a full deque, the oldest item on the opposite end drops automatically.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Next we add the `chat` method and inspection helpers. The `chat` method converts the deque to a plain list before sending it to the API. It also records token usage and the current window size for each turn. The inspection helpers let you peek at what the LLM sees (the window) versus the full history.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Usage Example: Watching the Window Slide\n\nLet's use a small window (`k=6` messages, which is 3 turns) and watch what happens as the conversation grows. We'll plant a fact early and then ask about it after it falls out of the window.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("Let's inspect what the LLM currently sees versus what it has forgotten. Messages inside the window are visible to the model. Evicted messages are gone forever.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Eval: Recency vs. Recall at Different Window Sizes\n\nHere's the key question: **how does window size affect the agent's ability to recall facts planted at different points in the conversation?**\n\nWe'll run a controlled experiment:\n1. Plant 5 distinct facts at turns 1-5.\n2. Add filler turns to push older facts out of smaller windows.\n3. Ask the model to recall each fact.\n4. Score recall accuracy at window sizes k = 4, 8, 12, and 20 messages.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Now we define the evaluation function. It plants facts, adds filler turns to push old facts out of small windows, then asks recall questions. Each answer is checked for a keyword to determine whether the agent remembered the fact.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Run the evaluation across four window sizes: 4, 8, 12, and 20 messages. Smaller windows will forget facts planted early in the conversation. Larger windows cost more tokens but recall more.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("Plot the results. The left chart shows recall accuracy at each window size. The right chart shows total token cost. You'll see the core tradeoff: larger windows remember more but spend more tokens.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Build a recall matrix showing which specific facts survived at each window size. This table makes it clear that older facts (planted first) are the first to be forgotten as the window shrinks.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Token Cost: Sliding Window vs. Full Buffer\n\nThe whole point of a sliding window is **bounded, predictable cost**. Let's compare the token growth curves side-by-side.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Discussion and Tradeoffs\n\n### Strengths\n- **Predictable cost**: Token usage per turn is bounded by the window size, regardless of conversation length.\n- **Quick to build**: Python's `deque(maxlen=k)` gives you the whole mechanism in one line.\n- **Good enough for most chats**: Users rarely reference something from 20+ turns ago.\n- **Low latency**: Bounded input size means bounded response time.\n\n### Weaknesses\n- **Hard information cutoff**: Once a message slides out of the window, it's gone. There's no trace, no summary, nothing.\n- **No graceful degradation**: Unlike summary memory, the agent doesn't even know it forgot something.\n- **Orphaned messages**: A message-count window can split a user-assistant pair. That leaves a response without its corresponding question. (Our implementation avoids this by counting messages, but turn-based windows are another option.)\n- **Choosing *k* is tricky**: Too small and it forgets important context. Too large and it defeats the purpose.\n\n### Choosing the Right Window Size\n\n| Window Size | Good For | Watch Out |\n|-------------|----------|-----------|\n| k = 4-6 msgs | Quick Q&A, stateless tasks | Forgets context after 2-3 turns |\n| k = 10-20 msgs | Most chatbots, customer support | Costs rise; may still forget early facts |\n| k = 40+ msgs | Complex multi-step tasks | Approaching buffer memory cost; consider a hybrid |\n\n### Rule of thumb\nStart with `k = 10` (5 complete turns) and adjust based on your recall requirements and budget.\n\n### When to Use Something Else\n- If you need to remember facts from much earlier: use **Summary Memory** or **Entity Memory**.\n- If you need to balance recency with cost but can't afford hard cutoffs: use a **Summary + Buffer Hybrid**.\n- If you need to stay under an exact token budget: use **Token Buffer Memory**.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Further Reading\n\n- [Anthropic Messages API: Multi-turn Conversations](https://docs.anthropic.com/en/docs/build-with-claude/conversational-ai?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques)\n- [LangChain ConversationBufferWindowMemory](https://python.langchain.com/docs/modules/memory/types/buffer_window?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques)\n- [LlamaIndex ChatMemoryBuffer](https://docs.llamaindex.ai/en/stable/api_reference/memory/chat_memory_buffer/?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques)\n- [Lilian Weng, "LLM Powered Autonomous Agents" (Memory section)](https://lilianweng.github.io/posts/2023-06-23-agent/?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques)\n- Python `collections.deque`: [Official docs](https://docs.python.org/3/library/collections.html#collections.deque)\n\n---\n\n*← Previous: 01: Conversation Buffer Memory · Next: [03: Summary Memory](../03_summary_memory/) →*')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## 🧪 Try It Yourself\n\nThree small challenges to deepen your understanding. Each should take 10-30 minutes.\n\n### Challenge 1: Eviction callback\nAdd an `on_evict` callback to `SlidingWindowMemory` that is called with each evicted message. Log evicted messages to a list and print them at the end. This gives you visibility into what the agent forgets.\n\n### Challenge 2: Window size vs. recall heatmap\nRun `run_recall_eval()` with window sizes [2, 4, 6, 8, 10, 16, 20] and plot a heatmap of recall scores by window size and question category. Identify the smallest window that achieves at least 80% recall on identity questions.\n\n### Challenge 3: Sliding window with summary fallback\nWhen a message is evicted from the deque, feed it to an LLM to update a running summary (like 03 Summary Memory). Prepend that summary to the context on each turn. Measure whether this hybrid beats a pure sliding window on the recall benchmark.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--02-sliding-window-memory--sliding-window-memory)\n')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# Install required packages (run once)\n# SETUP (run separately): %pip install -q anthropic python-dotenv matplotlib pandas\n\nimport os\nimport copy\nfrom collections import deque\nfrom dotenv import load_dotenv\n\nload_dotenv()  # reads ANTHROPIC_API_KEY from .env\n\nimport anthropic\n\nassert os.getenv("ANTHROPIC_API_KEY"), "Set ANTHROPIC_API_KEY in your .env file"\nprint("✓ Anthropic API key loaded")\n\nclass SlidingWindowMemory:\n    """Sliding window memory that keeps the last *k* messages."""\n\n    def __init__(\n        self,\n        window_size: int = 10,\n        model: str = "claude-sonnet-4-20250514",\n        system_prompt: str | None = None,\n        max_tokens: int = 1024,\n    ):\n        self.client = anthropic.Anthropic()\n        self.model = model\n        self.system_prompt = system_prompt\n        self.max_tokens = max_tokens\n\n        # The sliding window - a deque with a fixed max length\n        self.window_size = window_size\n        self.messages: deque[dict] = deque(maxlen=window_size)\n\n        # Track all messages for analysis (not sent to the LLM)\n        self.full_history: list[dict] = []\n        self.turn_token_usage: list[dict] = []\n\n\n    # ── Chat ─────────────────────────────────────────────────────\n    def chat(self, user_input: str) -> str:\n        """Send a message; only the last *k* messages are sent to the LLM."""\n        user_msg = {"role": "user", "content": user_input}\n        self.messages.append(user_msg)\n        self.full_history.append(user_msg)\n\n        kwargs = dict(\n            model=self.model,\n            max_tokens=self.max_tokens,\n            messages=list(self.messages),  # deque → list for the API\n        )\n        if self.system_prompt:\n            kwargs["system"] = self.system_prompt\n\n        response = self.client.messages.create(**kwargs)\n        assistant_text = response.content[0].text\n\n        assistant_msg = {"role": "assistant", "content": assistant_text}\n        self.messages.append(assistant_msg)\n        self.full_history.append(assistant_msg)\n\n        self.turn_token_usage.append({\n            "turn": len(self.turn_token_usage) + 1,\n            "input_tokens": response.usage.input_tokens,\n            "output_tokens": response.usage.output_tokens,\n            "window_msgs": len(self.messages),\n        })\n\n        return assistant_text\n\n    # ── Inspection helpers ───────────────────────────────────────\n    def get_window(self) -> list[dict]:\n        """Return the current window contents (what the LLM sees)."""\n        return list(self.messages)\n\n    def get_full_history(self) -> list[dict]:\n        """Return all messages ever sent, including evicted ones."""\n        return copy.deepcopy(self.full_history)\n\n    @property\n    def evicted_count(self) -> int:\n        """Number of messages that have been dropped from the window."""\n        return len(self.full_history) - len(self.messages)\n\n    def clear(self) -> None:\n        self.messages.clear()\n        self.full_history.clear()\n        self.turn_token_usage.clear()\n\n    def __repr__(self) -> str:\n        return (\n            f"SlidingWindowMemory(window={len(self.messages)}/{self.window_size}, "\n            f"total={len(self.full_history)} messages, "\n            f"evicted={self.evicted_count})"\n        )\n\nprint("✓ SlidingWindowMemory class defined")\n\nmem = SlidingWindowMemory(\n    window_size=6,  # 3 full turns (user + assistant each)\n    system_prompt="You are a concise assistant. Reply in 1-2 sentences.",\n)\n\nconversation = [\n    "My name is Alice and I\'m a pilot.",           # turn 1 - plants a fact\n    "I fly Boeing 737s for a regional airline.",    # turn 2 - plants another fact\n    "What\'s the weather like in Seattle today?",   # turn 3 - unrelated filler\n    "What\'s my name and what do I do for work?",   # turn 4 - recall test (turn 1 may be evicted)\n]\n\nfor msg in conversation:\n    print(f"👤 User:  {msg}")\n    reply = mem.chat(msg)\n    print(f"🤖 Agent: {reply}")\n    print(f"   📊 Window: {len(mem.messages)}/{mem.window_size} msgs | Evicted: {mem.evicted_count}")\n    print()\n\n# Inspect what the LLM currently sees vs. what it has forgotten\nprint("=== Messages IN the window (LLM can see) ===")\nfor i, msg in enumerate(mem.get_window()):\n    role = "USER" if msg["role"] == "user" else "ASST"\n    preview = msg["content"][:70] + ("..." if len(msg["content"]) > 70 else "")\n    print(f"  [{i}] {role}: {preview}")\n\nprint(f"\\n=== Evicted messages (LLM cannot see): {mem.evicted_count} ===" )\nevicted = mem.get_full_history()[:mem.evicted_count]\nfor i, msg in enumerate(evicted):\n    role = "USER" if msg["role"] == "user" else "ASST"\n    preview = msg["content"][:70] + ("..." if len(msg["content"]) > 70 else "")\n    print(f"  [{i}] {role}: {preview}")\n\nimport re\n\nFACTS = [\n    ("My name is Elena.", "elena"),\n    ("I was born in Prague.", "prague"),\n    ("My favorite color is teal.", "teal"),\n    ("I have two cats named Salt and Pepper.", "salt"),\n    ("I work as a data scientist at a biotech company.", "data scientist"),\n]\n\nFILLER_MESSAGES = [\n    "Tell me a fun fact about octopuses.",\n    "What\'s the capital of Mongolia?",\n    "How does photosynthesis work in one sentence?",\n    "What year was the Eiffel Tower built?",\n    "Name a famous mathematician.",\n]\n\nRECALL_QUESTIONS = [\n    ("What is my name?", "elena"),\n    ("Where was I born?", "prague"),\n    ("What is my favorite color?", "teal"),\n    ("What are my cats\' names?", "salt"),\n    ("What do I do for work?", "data scientist"),\n]\n\n\n\ndef run_recall_eval(window_size: int) -> dict:\n    """Run the recall eval for a given window size and return scores."""\n    mem = SlidingWindowMemory(\n        window_size=window_size,\n        system_prompt="You are a helpful assistant. Answer concisely.",\n    )\n\n    # Phase 1: Plant facts (5 turns = 10 messages)\n    for fact, _ in FACTS:\n        mem.chat(fact)\n\n    # Phase 2: Filler turns to push old facts out (5 turns = 10 messages)\n    for filler in FILLER_MESSAGES:\n        mem.chat(filler)\n\n    # Phase 3: Ask recall questions and check answers\n    results = {}\n    for question, keyword in RECALL_QUESTIONS:\n        answer = mem.chat(question)\n        recalled = keyword.lower() in answer.lower()\n        results[keyword] = {\n            "question": question,\n            "answer": answer[:100],\n            "recalled": recalled,\n        }\n\n    score = sum(1 for r in results.values() if r["recalled"])\n    return {\n        "window_size": window_size,\n        "score": score,\n        "total": len(RECALL_QUESTIONS),\n        "pct": score / len(RECALL_QUESTIONS) * 100,\n        "details": results,\n        "total_input_tokens": sum(t["input_tokens"] for t in mem.turn_token_usage),\n    }\n\n\n\n# Test multiple window sizes\nWINDOW_SIZES = [4, 8, 12, 20]\neval_results = []\n\nfor k in WINDOW_SIZES:\n    print(f"Running eval with window_size={k}...", end=" ")\n    result = run_recall_eval(k)\n    eval_results.append(result)\n    print(f"Recall: {result[\'score\']}/{result[\'total\']} ({result[\'pct\']:.0f}%)")\n\nprint("\\nDone!")\n\nimport matplotlib.pyplot as plt\nimport numpy as np\n\nfig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))\n\nwindow_sizes = [r["window_size"] for r in eval_results]\nscores = [r["pct"] for r in eval_results]\ntokens = [r["total_input_tokens"] for r in eval_results]\n\n# Left: Recall accuracy vs window size\ncolors = ["#ef4444" if s < 40 else "#f59e0b" if s < 80 else "#22c55e" for s in scores]\nbars = ax1.bar(range(len(window_sizes)), scores, color=colors, alpha=0.85, width=0.6)\nax1.set_xticks(range(len(window_sizes)))\nax1.set_xticklabels([f"k={k}" for k in window_sizes])\nax1.set_ylabel("Recall Accuracy (%)")\nax1.set_title("Recall Accuracy vs. Window Size")\nax1.set_ylim(0, 110)\nax1.axhline(y=100, color="gray", linestyle="--", alpha=0.3)\nfor bar, score in zip(bars, scores):\n    ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,\n             f"{score:.0f}%", ha="center", va="bottom", fontweight="bold")\n\n# Right: Total token cost vs window size\nax2.plot(window_sizes, tokens, "o-", color="#6366f1", linewidth=2, markersize=8)\nax2.fill_between(window_sizes, tokens, alpha=0.1, color="#6366f1")\nax2.set_xlabel("Window Size (k messages)")\nax2.set_ylabel("Total Input Tokens")\nax2.set_title("Total Token Cost vs. Window Size")\nfor x, y in zip(window_sizes, tokens):\n    ax2.annotate(f"{y:,}", (x, y), textcoords="offset points",\n                 xytext=(0, 10), ha="center", fontsize=9)\n\nplt.tight_layout()\nplt.savefig("sliding_window_eval.png", dpi=150, bbox_inches="tight")\nplt.show()\n\nprint("The tradeoff is clear: larger windows recall more but cost more tokens.")\n\nimport pandas as pd\n\n# Build a summary table\nrows = []\nfor r in eval_results:\n    for keyword, detail in r["details"].items():\n        rows.append({\n            "Window Size": r["window_size"],\n            "Fact": keyword,\n            "Recalled?": "✓" if detail["recalled"] else "✗",\n            "Answer (preview)": detail["answer"][:60],\n        })\n\ndf = pd.DataFrame(rows)\n# Pivot so facts are columns and window sizes are rows\npivot = df.pivot(index="Window Size", columns="Fact", values="Recalled?")\nprint("Recall matrix (✓ = remembered, ✗ = forgotten):\\n")\nprint(pivot.to_string())\n\n# Simulate token growth for buffer vs sliding window\n# Using a simple model: each message ≈ 50 tokens, system prompt ≈ 30 tokens\nMSG_TOKENS = 50\nSYS_TOKENS = 30\nNUM_TURNS = 25\nWINDOW_K = 10  # 5 turns\n\nbuffer_input = []\nwindow_input = []\n\nfor turn in range(1, NUM_TURNS + 1):\n    n_msgs = turn * 2  # user + assistant per turn\n    buffer_input.append(SYS_TOKENS + n_msgs * MSG_TOKENS)\n    window_msgs = min(n_msgs, WINDOW_K)\n    window_input.append(SYS_TOKENS + window_msgs * MSG_TOKENS)\n\nturns = list(range(1, NUM_TURNS + 1))\n\nfig, ax = plt.subplots(figsize=(10, 5))\nax.plot(turns, buffer_input, "o-", color="#ef4444", label="Full Buffer", linewidth=2)\nax.plot(turns, window_input, "s-", color="#22c55e", label=f"Sliding Window (k={WINDOW_K})", linewidth=2)\nax.fill_between(turns, window_input, buffer_input, alpha=0.08, color="#ef4444")\nax.set_xlabel("Conversation Turn")\nax.set_ylabel("Input Tokens per API Call")\nax.set_title("Input Tokens per Turn: Full Buffer vs. Sliding Window")\nax.legend()\nax.grid(True, alpha=0.2)\n\n# Annotate the savings at the last turn\nsavings = buffer_input[-1] - window_input[-1]\nax.annotate(\n    f"Savings: {savings:,} tokens/turn",\n    xy=(NUM_TURNS, (buffer_input[-1] + window_input[-1]) / 2),\n    fontsize=11, fontweight="bold", color="#6366f1",\n    ha="right",\n)\n\nplt.tight_layout()\nplt.savefig("buffer_vs_window.png", dpi=150, bbox_inches="tight")\nplt.show()\n\nprint(f"At turn {NUM_TURNS}:")\nprint(f"  Full buffer:    {buffer_input[-1]:,} input tokens")\nprint(f"  Sliding window: {window_input[-1]:,} input tokens")\nprint(f"  Savings:        {savings:,} tokens ({savings/buffer_input[-1]*100:.0f}%)")\n\n# Clean up temp files created during the demo\nimport os\nfor f in ["sliding_window_eval.png", "buffer_vs_window.png"]:\n    if os.path.exists(f):\n        os.remove(f)\n        print(f"Removed {f}")', language="python", label="Recovered notebook code")
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
