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
    mo.md("# Summary Buffer Memory\n\n> **A hybrid memory that keeps recent messages word-for-word while summarizing older history.**\n\nThink about how you remember a long phone call with a friend. The last few sentences? You recall them almost word-for-word. That's your short-term memory. The earlier parts? You remember the gist, not the exact words. That's your long-term memory.\n\nSummary Buffer Memory works the same way. It keeps a **buffer zone** of the most recent messages in their original form. Everything older gets compressed into a **running summary**. The LLM receives both pieces on every call: the summary for historical context, and the raw recent messages for precision.\n\nPure buffer memory (storing every message) gives exact recall but costs more tokens with each turn. Pure summary memory (compressing everything) saves tokens but loses recent detail. Summary Buffer Memory combines both strengths. It's especially valuable for customer support bots, coaching agents, and project management assistants. These agents need to remember the full arc of a conversation while responding precisely to the latest message.\n\nThe core engineering challenge is the **transition threshold**: the point where messages age out of the buffer and fold into the summary. Set it too high and you waste tokens. Set it too low and you lose important detail.\n\n**By the end of this notebook you'll understand:**\n- How to build a summary buffer memory from scratch with the OpenAI SDK.\n- How incremental summarization works (updating a summary with newly evicted messages).\n- How to tune the buffer size and observe its effect on token usage.\n- When this technique wins and when it quietly fails.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Key Concepts\n\n- **Buffer zone**: The most recent *k* messages stored word-for-word. These preserve exact wording, nuance, and detail for immediate reasoning.\n- **Running summary**: A short paragraph that captures the key facts and themes from all messages that have aged out of the buffer. The LLM generates this summary.\n- **Context window**: The maximum number of tokens (word-pieces the model uses internally) a model can read in one call. For example, GPT-4o supports up to 128k tokens.\n- **Transition threshold**: The trigger point at which messages move from the buffer into the summary. You can base it on message count or token count.\n- **Incremental summarization**: Instead of re-summarizing the full history each time, we take the existing summary and the newly evicted messages, then produce an updated summary in a single LLM call. This keeps summarization cost low.\n- **Token budget allocation**: The split of available context-window tokens between the summary and the buffer. A typical allocation reserves 20-30% for the summary and 70-80% for recent messages.\n- **Prompt assembly**: The process of stitching together `[system prompt] + [summary] + [recent buffer messages]` into one prompt for the LLM.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Architecture\n\n<p align="center">\n  <img src="../../images/diagrams/04_summary_buffer_memory.svg" alt="Summary Buffer Memory architecture diagram" width="720"/>\n</p>\n\n<details><summary>Mermaid source</summary>\n\n```mermaid\nflowchart LR\n    User["User Message"] --> Buffer["Buffer\\n(recent K messages)"]\n    Buffer --> ThresholdCheck{"Buffer exceeds\\nthreshold?"}\n    ThresholdCheck -- No --> PromptAssembly["Prompt Assembly"]\n    ThresholdCheck -- Yes --> Evict["Evict oldest\\nmessages"]\n    Evict --> Summarizer["Summarizer\\n(LLM call)"]\n    Summarizer --> SummaryStore["Summary Store\\n(running summary)"]\n    SummaryStore --> PromptAssembly\n    Buffer --> PromptAssembly\n    PromptAssembly --> LLM["LLM\\n[summary] + [buffer]"]\n    LLM --> Response["Response"]\n    Response --> Buffer\n```\n\n</details>\n\nHere\'s how the data flows. New user messages enter the buffer. When the buffer exceeds its configured threshold, the oldest messages get evicted. Those evicted messages feed a summarizer LLM call that updates the running summary. The final prompt concatenates the system prompt, the summary, and the recent buffer messages. The LLM responds, and that response goes back into the buffer. The cycle repeats on every turn.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Setup\n\nInstall dependencies and configure API access. You'll need an `OPENAI_API_KEY` environment variable set in a `.env` file.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("Import the OpenAI SDK, `tiktoken` (OpenAI's tokenizer library for counting tokens), and standard library helpers.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Implementation\n\nWe'll build a `SummaryBufferMemory` class that:\n1. Stores recent messages in a buffer (a plain Python list).\n2. Maintains a running summary of older history.\n3. Evicts the oldest messages when the buffer exceeds a token threshold.\n4. Uses an LLM call to fold evicted messages into the summary.\n5. Assembles the final prompt as `[system] + [summary] + [buffer]`.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Token counting helper\n\nWe need a way to count how many tokens a list of messages uses. This tells us when the buffer has grown too large.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### The summarizer\n\nThis function takes the current running summary and a batch of newly evicted messages. It asks the LLM to produce an updated summary that incorporates the new information.\n\nThink of it like updating meeting notes. You have yesterday's notes (the existing summary) and today's discussion points (the evicted messages). You merge them into one concise document.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### The SummaryBufferMemory class\n\nThis is the core of the technique. The class manages two memory regions:\n- **Buffer**: a list of recent messages (word-for-word).\n- **Summary**: a string that captures older history.\n\nWhen you call `chat()`, the class checks whether the buffer exceeds `max_buffer_tokens`. If it does, the oldest messages get evicted and folded into the summary. Then it assembles the full prompt and calls the LLM.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Next we add the eviction and prompt-building logic. `_evict_if_needed` pops the oldest messages from the buffer one at a time, then calls `update_summary` to fold them into the running summary. `_build_messages` stitches together the system prompt, the summary, and the remaining buffer into one prompt for the API.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('The `chat` method ties everything together. It appends the user message, triggers eviction if needed, builds the assembled prompt, and calls the LLM. The response goes back into the buffer for future context.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Finally, we add utility methods for inspecting and resetting the memory. `get_buffer` and `get_summary` let you peek at each region. `get_buffer_token_count` tells you how close the buffer is to the eviction threshold.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Example Run\n\nLet's run a multi-turn conversation and watch the summary buffer in action. We'll use a small buffer threshold (300 tokens) so that evictions happen quickly. In production you'd set this higher.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("Create the memory and run a conversation. We'll print the agent's reply after each turn.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Inspecting the memory state\n\nAfter 9 turns, some messages have been evicted and summarized. Let's look at what's in each region.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Eviction log\n\nEach time messages aged out of the buffer, the system recorded the event. This log shows how the summary evolved over time.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### What the LLM actually sees\n\nLet's peek at the assembled prompt. This is exactly what gets sent to the API on the next call. Notice how the summary sits in the system message and the buffer messages follow.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Comparison: Buffer vs. Summary Buffer\n\nHow does our hybrid approach compare to plain buffer memory in terms of token usage? Let's run the same conversation through both and measure.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Tradeoffs\n\n### When Summary Buffer Memory Works Well\n\n- **Medium to long conversations** (20-100+ turns) where you need both historical context and precise recent detail. Customer support bots and coaching agents are common examples.\n- **Token-budget-conscious applications**: the summary compresses older history, so cumulative token usage grows much slower than with pure buffer memory.\n- **When recent context matters most**: the buffer zone keeps the last few exchanges in full fidelity. The model can reference exact words, numbers, and names from the recent turns.\n\n### When It Breaks Down\n\n- **Summary quality degrades over time.** Each incremental summarization call risks losing detail. After dozens of evictions, the summary may miss facts that mattered. There's no built-in way to verify that the summary is accurate.\n- **Extra LLM calls add cost and latency.** Every eviction triggers a summarization call. For fast-paced conversations (sub-second response requirements), this overhead may be too high.\n- **Harder to debug than plain buffer.** When the agent forgets something, you need to trace whether the information was lost during summarization or never reached the buffer. With plain buffer memory, the full history is always there.\n- **Tuning is tricky.** The buffer threshold, the summarization prompt, and the model choice for summarization all interact. Getting the right balance takes experimentation.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Further Reading\n\n- [LangChain ConversationSummaryBufferMemory](https://python.langchain.com/docs/modules/memory/types/summary_buffer?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques): The framework implementation of this pattern with configurable token limits and LLM-based summarization.\n- [MemGPT / Letta: Tiered Memory Management (arXiv:2310.08560)](https://arxiv.org/abs/2310.08560): Packer et al. introduce a multi-tiered memory architecture where the LLM manages its own context window, moving data between main context and external storage.\n- [LlamaIndex ChatSummaryMemoryBuffer](https://docs.llamaindex.ai/en/stable/api_reference/memory/?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques): LlamaIndex's implementation that integrates summary-buffer memory with retrieval-augmented generation pipelines.\n- [OpenAI Cookbook: Counting Tokens with tiktoken](https://cookbook.openai.com/examples/how_to_count_tokens_with_tiktoken?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques): Practical strategies for counting and managing tokens in chat applications.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('---\n\n*← Previous: [03: Summary Memory](../03_summary_memory/) · Next: [05: Token Buffer Memory](../05_token_buffer_memory/) →*')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## 🧪 Try It Yourself\n\nThree small challenges to deepen your understanding. Each should take 10-30 minutes.\n\n### Challenge 1: Tune the eviction threshold\nModify the token threshold in `SummaryBufferMemory` to 500, 1000, and 2000 tokens. For each setting, run a 15-turn conversation and note how often `_evict_if_needed()` triggers. Record the final summary length each time.\n\n### Challenge 2: Compression ratio tracking\nAfter each eviction cycle, compute the ratio of tokens saved (evicted raw tokens minus summary tokens). Plot this compression ratio across turns. Identify the point where summarization gives diminishing returns.\n\n### Challenge 3: Entity-aware summarization\nBefore calling `update_summary()`, extract entities from the evicted messages using the approach from 07 Entity Memory. Pass the entity list to the summarizer prompt so it preserves named entities. Compare recall on entity-specific questions before and after this change.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--04-summary-buffer-memory--summary-buffer-memory)\n')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# SETUP (run separately): %pip install -q openai python-dotenv tiktoken\n\nimport os\nimport json\nimport copy\nfrom dotenv import load_dotenv\nimport tiktoken\nfrom openai import OpenAI\n\nload_dotenv()  # reads OPENAI_API_KEY from .env\n\nassert os.getenv("OPENAI_API_KEY"), "Set OPENAI_API_KEY in your .env file"\n\nclient = OpenAI()\n\n# We\'ll use this encoder throughout to count tokens.\n# "cl100k_base" is the tokenizer used by GPT-4o and GPT-4.\nencoder = tiktoken.get_encoding("cl100k_base")\n\ndef count_message_tokens(messages: list[dict], enc: tiktoken.Encoding = encoder) -> int:\n    """Count the total tokens in a list of chat messages.\n\n    Each message has overhead tokens for role formatting.\n    We add 4 tokens per message as an approximation of that overhead.\n    """\n    total = 0\n    for msg in messages:\n        total += 4  # role + formatting overhead\n        total += len(enc.encode(msg["content"]))\n    return total\n\nSUMMARY_SYSTEM_PROMPT = """You are a conversation summarizer. Your job is to maintain\na running summary of a conversation. You will receive:\n1. The current summary (may be empty if this is the start).\n2. New messages that need to be incorporated.\n\nProduce an updated summary that:\n- Preserves all key facts, names, preferences, and decisions.\n- Stays concise (aim for 3-6 sentences).\n- Uses third person ("The user said...", "The assistant suggested...").\n- Drops filler and small talk while keeping substance.\n"""\n\n\ndef update_summary(\n    current_summary: str,\n    evicted_messages: list[dict],\n    model: str = "gpt-4o-mini",\n) -> str:\n    """Fold evicted messages into the running summary via an LLM call."""\n    # Format the evicted messages as readable text\n    evicted_text = "\\n".join(\n        f"{msg[\'role\'].upper()}: {msg[\'content\']}" for msg in evicted_messages\n    )\n\n    user_prompt = (\n        f"Current summary:\\n{current_summary if current_summary else \'(empty)\'}\\n\\n"\n        f"New messages to incorporate:\\n{evicted_text}\\n\\n"\n        f"Write the updated summary:"\n    )\n\n    response = client.chat.completions.create(\n        model=model,\n        messages=[\n            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},\n            {"role": "user", "content": user_prompt},\n        ],\n        max_tokens=512,\n        temperature=0.3,  # low temperature for consistent summaries\n    )\n\n    return response.choices[0].message.content\n\nclass SummaryBufferMemory:\n    """Hybrid memory: running summary + recent message buffer."""\n\n    def __init__(\n        self,\n        model: str = "gpt-4o-mini",\n        system_prompt: str | None = None,\n        max_buffer_tokens: int = 300,\n        max_tokens: int = 1024,\n    ):\n        self.model = model\n        self.system_prompt = system_prompt\n        self.max_buffer_tokens = max_buffer_tokens\n        self.max_tokens = max_tokens\n\n        # The two memory regions\n        self.buffer: list[dict] = []      # recent messages (verbatim)\n        self.summary: str = ""             # compressed older history\n\n        # Bookkeeping\n        self.turn_count: int = 0\n        self.eviction_log: list[dict] = []  # tracks each eviction event\n\n\n    def _evict_if_needed(self) -> None:\n        """Move oldest messages from buffer to summary when over budget."""\n        evicted_batch = []\n\n        while (\n            len(self.buffer) > 2\n            and count_message_tokens(self.buffer) > self.max_buffer_tokens\n        ):\n            # Evict the oldest message (FIFO: first in, first out)\n            evicted_batch.append(self.buffer.pop(0))\n\n        if evicted_batch:\n            old_summary = self.summary\n            self.summary = update_summary(self.summary, evicted_batch, self.model)\n\n            self.eviction_log.append({\n                "turn": self.turn_count,\n                "evicted_count": len(evicted_batch),\n                "summary_before": old_summary,\n                "summary_after": self.summary,\n            })\n\n    def _build_messages(self) -> list[dict]:\n        """Assemble the full message list for the API call."""\n        messages = []\n\n        # Inject the summary as a system-level context block\n        if self.summary:\n            summary_block = f"Summary of earlier conversation:\\n{self.summary}"\n            if self.system_prompt:\n                messages.append({\n                    "role": "system",\n                    "content": f"{self.system_prompt}\\n\\n{summary_block}",\n                })\n            else:\n                messages.append({"role": "system", "content": summary_block})\n        elif self.system_prompt:\n            messages.append({"role": "system", "content": self.system_prompt})\n\n        # Append the recent buffer messages\n        messages.extend(self.buffer)\n        return messages\n\n\n    def chat(self, user_input: str) -> str:\n        """Send a message and get a response."""\n        self.buffer.append({"role": "user", "content": user_input})\n        self.turn_count += 1\n\n        # Check if we need to evict before calling the LLM\n        self._evict_if_needed()\n\n        # Build the prompt and call the API\n        messages = self._build_messages()\n\n        response = client.chat.completions.create(\n            model=self.model,\n            messages=messages,\n            max_tokens=self.max_tokens,\n        )\n\n        assistant_text = response.choices[0].message.content\n        self.buffer.append({"role": "assistant", "content": assistant_text})\n\n        return assistant_text\n\n\n    def get_buffer(self) -> list[dict]:\n        """Return a copy of the current buffer."""\n        return copy.deepcopy(self.buffer)\n\n    def get_summary(self) -> str:\n        """Return the current running summary."""\n        return self.summary\n\n    def get_buffer_token_count(self) -> int:\n        """Return the current token count of the buffer."""\n        return count_message_tokens(self.buffer)\n\n    def clear(self) -> None:\n        """Reset both memory regions."""\n        self.buffer.clear()\n        self.summary = ""\n        self.turn_count = 0\n        self.eviction_log.clear()\n\n    def __repr__(self) -> str:\n        return (\n            f"SummaryBufferMemory("\n            f"buffer={len(self.buffer)} msgs, "\n            f"summary={\'yes\' if self.summary else \'empty\'}, "\n            f"turns={self.turn_count})"\n        )\n\nmemory = SummaryBufferMemory(\n    system_prompt="You are a helpful, concise assistant. Keep replies under 2 sentences.",\n    max_buffer_tokens=300,\n)\n\nexchanges = [\n    "Hi! My name is Alice and I\'m a machine-learning engineer in Berlin.",\n    "I\'m building a chatbot for our customer support team. We get about 500 tickets a day.",\n    "The main issue is that our current bot forgets context after 3 messages.",\n    "We use Python and FastAPI on the backend. The bot runs on GPT-4o.",\n    "Our customers mostly ask about billing, shipping, and returns.",\n    "I also want the bot to remember user preferences across sessions.",\n    "We store conversation logs in PostgreSQL right now.",\n    "What memory technique would you recommend for our use case?",\n    "By the way, what\'s my name and where do I work?",\n]\n\nfor msg in exchanges:\n    print(f"\\n{\'=\'*60}")\n    print(f"Turn {memory.turn_count + 1}")\n    print(f"{\'=\'*60}")\n    print(f"User:  {msg}")\n    reply = memory.chat(msg)\n    print(f"Agent: {reply}")\n    print(f"\\n  Buffer: {len(memory.buffer)} messages ({memory.get_buffer_token_count()} tokens)")\n    print(f"  Summary: {\'[empty]\' if not memory.summary else memory.summary[:100] + \'...\'}")\n\nprint("RUNNING SUMMARY")\nprint("-" * 40)\nprint(memory.get_summary() or "(empty)")\n\nprint("\\nBUFFER (recent messages)")\nprint("-" * 40)\nfor i, msg in enumerate(memory.get_buffer()):\n    role_label = "USER" if msg["role"] == "user" else "ASST"\n    preview = msg["content"][:90] + ("..." if len(msg["content"]) > 90 else "")\n    print(f"  [{i}] {role_label}: {preview}")\n\nprint(f"\\nBuffer token count: {memory.get_buffer_token_count()}")\nprint(f"Buffer threshold:   {memory.max_buffer_tokens}")\n\nprint(f"Total eviction events: {len(memory.eviction_log)}\\n")\n\nfor i, event in enumerate(memory.eviction_log):\n    print(f"Eviction {i + 1} (after turn {event[\'turn\']})")\n    print(f"  Messages evicted: {event[\'evicted_count\']}")\n    print(f"  Summary before: {event[\'summary_before\'][:80] or \'(empty)\'}...")\n    print(f"  Summary after:  {event[\'summary_after\'][:80]}...")\n    print()\n\nassembled = memory._build_messages()\n\nprint(f"Total messages in assembled prompt: {len(assembled)}")\nprint(f"Total tokens in assembled prompt:   {count_message_tokens(assembled)}\\n")\n\nfor i, msg in enumerate(assembled):\n    role = msg["role"].upper()\n    content = msg["content"]\n    if len(content) > 150:\n        content = content[:150] + "..."\n    print(f"[{i}] {role}:")\n    print(f"    {content}")\n    print()\n\n# Simulate plain buffer memory: count tokens as if we sent ALL messages each turn.\n# We reuse the same exchanges list from above.\n\nall_messages = []  # accumulates like a plain buffer\nbuffer_tokens_per_turn = []\nsummary_buffer_tokens_per_turn = []\n\n# Reset summary buffer memory for a clean run\nsbm = SummaryBufferMemory(\n    system_prompt="You are a helpful, concise assistant. Keep replies under 2 sentences.",\n    max_buffer_tokens=300,\n)\n\nfor msg in exchanges:\n    # Plain buffer: accumulate all messages\n    all_messages.append({"role": "user", "content": msg})\n    buffer_tokens_per_turn.append(count_message_tokens(all_messages))\n    # Add a placeholder assistant reply to keep the count realistic\n    all_messages.append({"role": "assistant", "content": "Acknowledged."})\n\n    # Summary buffer: use the actual class\n    sbm.chat(msg)\n    assembled_msgs = sbm._build_messages()\n    summary_buffer_tokens_per_turn.append(count_message_tokens(assembled_msgs))\n\nprint(f"{\'Turn\':<6} {\'Buffer Memory\':<18} {\'Summary Buffer Memory\'}")\nprint("-" * 48)\nfor i in range(len(exchanges)):\n    print(f"{i+1:<6} {buffer_tokens_per_turn[i]:<18} {summary_buffer_tokens_per_turn[i]}")\n\nprint(f"\\nFinal turn token usage:")\nprint(f"  Buffer memory:         {buffer_tokens_per_turn[-1]} tokens")\nprint(f"  Summary buffer memory: {summary_buffer_tokens_per_turn[-1]} tokens")\nprint(f"  Savings:               {buffer_tokens_per_turn[-1] - summary_buffer_tokens_per_turn[-1]} tokens")', language="python", label="Recovered notebook code")
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
