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
    mo.md('# Token Buffer Memory\n\n> **Trim conversation history to fit a strict token budget. Use a real tokenizer, because message count is a poor proxy for context window usage.**\n\nThink of packing a suitcase with a strict weight limit. You don\'t count the number of items. You weigh each one and remove the oldest items until everything fits. Token Buffer Memory works the same way. It measures conversation history by tokens (not message count) and removes the oldest messages until the total fits under a budget.\n\nSliding window memory (technique 02) drops messages based on a fixed count. But one message with a code block might cost thousands of tokens, while a short "yes" costs one. Token Buffer Memory replaces that blunt count with precise measurement. A **tokenizer** is a tool that splits text into **tokens** (the word-pieces a model processes internally). Integrate a library like `tiktoken`. Now the system knows exactly how many tokens the history consumes before it reaches the model.\n\nThis precision matters most in production. An oversized prompt either truncates silently or throws a hard error. An undersized prompt wastes expensive context window space. Token Buffer Memory eliminates both failure modes. It sets a hard ceiling (`max_token_limit`) and evicts the oldest messages when the total exceeds it.\n\nThe technique is deliberately not fancy: no summarization, no embeddings (vector representations of text), no retrieval. That simplicity is its strength. It\'s deterministic, fast, and straightforward to reason about. When you need more sophisticated retention, layer this with summary or retrieval-augmented memory. Token Buffer Memory remains the foundational guardrail that keeps the prompt within bounds.\n\n**By the end you\'ll understand:**\n- How tokenizers measure real context usage and why token counts beat message counting.\n- How to build a token-aware memory from scratch with `tiktoken` and the OpenAI SDK.\n- When token budgets shine and when you need something more.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Key Concepts\n\n- **Token**: The smallest unit a language model reads. Roughly one word or word-piece. The word "unhappiness" might split into two tokens: "un" and "happiness".\n- **Tokenizer (`tiktoken`)**: A library that splits text into tokens for a specific model. OpenAI\'s `tiktoken` handles GPT-4, GPT-4o, and related models.\n- **Encoding**: The specific token vocabulary a model uses. GPT-4 uses `cl100k_base`. GPT-4o uses `o200k_base`. The wrong encoding gives inaccurate counts.\n- **max_token_limit**: A hard ceiling on total tokens allowed in conversation history. The system evicts old messages until the total stays at or below this number.\n- **Per-message overhead**: Each chat message carries formatting tokens beyond the content itself. These include role markers, a content separator, and end-of-message delimiters. Typically 4 tokens per message.\n- **Message-level eviction**: Entire messages are removed (not partially trimmed). This preserves coherence but may slightly under-use the budget.\n- **Context window**: The maximum number of tokens a model can process in one call. GPT-4o supports 128K tokens. Your history budget must leave room for the system prompt and the model\'s response.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Architecture\n\n<p align="center">\n  <img src="../../images/diagrams/05_token_buffer_memory.svg" alt="diagram" width="720"/>\n</p>\n\n<details><summary>Mermaid source</summary>\n\n```mermaid\nflowchart LR\n    NewMsg["New Message"] --> Tokenizer["Tokenizer\\n(tiktoken)"]\n    Tokenizer --> Counter["Token Counter\\n(sum all messages)"]\n    Counter --> BudgetCheck{"Total > \\nmax_token_limit?"}\n    BudgetCheck -- No --> TrimmedHistory["Trimmed History"]\n    BudgetCheck -- Yes --> Evict["Evict Oldest\\nMessage"]\n    Evict --> Counter\n    TrimmedHistory --> LLM["LLM"]\n    LLM --> Response["Response"]\n    Response --> NewMsg\n```\n\n</details>\n\n**Data flow:** Each new message is tokenized. The counter sums all messages in the history. If the total exceeds `max_token_limit`, the oldest message is evicted and the count rechecks in a loop. Once under budget, the trimmed history goes to the LLM. The response is appended and the cycle repeats.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Setup\n\nInstall dependencies and configure API access.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Import `tiktoken` for token counting and the OpenAI SDK for LLM calls. The API key loads from a `.env` file.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Implementation\n\nWe'll build a `TokenBufferMemory` class that:\n1. Counts tokens per message using `tiktoken`.\n2. Keeps a running total of all stored messages.\n3. Evicts the oldest messages when the total exceeds `max_token_limit`.\n4. Sends the trimmed history to the OpenAI API on each call.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Token Counting\n\nAccurate token counting is the foundation of this technique. Each chat message costs more tokens than its content alone. The Chat Completions API wraps every message with special tokens. These include role markers, a content separator, and end-of-message delimiters. This overhead is typically 4 tokens per message.\n\nLet's see how `tiktoken` counts tokens for messages of different lengths.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### The TokenBufferMemory Class\n\nThis class wraps token counting into a complete memory system. On each `chat()` call, it:\n1. Appends the user message.\n2. Sums tokens across all stored messages.\n3. Evicts the oldest messages in a loop until the total fits under `max_token_limit`.\n4. Sends the trimmed history to the LLM.\n5. Appends the response.\n\nSet `max_token_limit` to the space available for history. Subtract the system prompt tokens and your response budget from the model's context window. For example, with a 128K window, a 200-token system prompt, and a 1,024-token response budget, set `max_token_limit` to about 126,000.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Now we add the eviction loop and the `chat` method. The `_trim` method runs a while-loop: it pops the oldest message, subtracts its token count, and repeats until the total fits under `max_token_limit`. The `chat` method appends the user message, trims if needed, calls the LLM, and appends the response.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Utility methods for inspecting and resetting the memory. `get_messages` returns a copy of the current history. `clear` wipes both messages and the eviction log.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Example Run\n\nA short conversation shows token buffer memory in action. With a generous budget (2,048 tokens), all messages fit and nothing gets evicted. The agent remembers everything.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Eviction in Action\n\nNow we'll use a tiny budget (300 tokens). This forces eviction after a few turns. Watch the token count stay bounded as older messages disappear.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Why Tokens Beat Message Count\n\nA sliding window that keeps the last 5 messages treats all messages as equal. In practice, messages vary in size by orders of magnitude. A one-word reply and a pasted code block both count as "one message" in a sliding window. But they differ enormously in tokens.\n\nThe cell below shows this directly.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Tradeoffs\n\n### When Token Buffer Memory Works Well\n- **Precise budget control**: You know exactly how many tokens go to the model. No silent truncation, no rejected prompts.\n- **Variable message sizes**: Code blocks, JSON payloads, and short replies all get measured accurately. Message-count trimming can't do this.\n- **Speed**: Eviction runs in milliseconds with no LLM calls (unlike summary memory). The trimming is deterministic.\n- **Multi-model routing**: If your system routes to models with different context windows, set a per-model `max_token_limit`. The same class handles both.\n\n### When It Breaks Down\n- **No recall of evicted content**: Once a message is removed, that information is gone. Summary memory or retrieval-augmented memory preserves some of it.\n- **One large message crowds out many small ones**: A single 1,000-token message forces eviction of many short messages to make room.\n- **Tokenizer must match the model**: Using GPT-4's encoding with GPT-4o (or vice versa) gives wrong counts. Keep the encoding in sync with the model.\n- **Whole-message eviction can waste budget**: If the budget is 500 tokens and the oldest message costs 400, evicting it frees more space than needed. Partial trimming would be more efficient, but it breaks message coherence.\n\n### What's Next?\n- **[06: Vector-Store Memory](../06_vector_store_memory/)** retrieves relevant past messages using semantic search instead of dropping by age.\n- **[03: Summary Memory](../03_summary_memory/)** compresses old messages into a summary so no information is fully lost.\n- Combine approaches: use token buffer as the hard ceiling, with summary or retrieval to preserve evicted content.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Further Reading\n\n- [LangChain ConversationTokenBufferMemory](https://python.langchain.com/docs/modules/memory/types/token_buffer?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques): LangChain's built-in implementation. It wraps tiktoken for automatic token-based trimming.\n- [tiktoken: OpenAI's Fast BPE Tokenizer](https://github.com/openai/tiktoken): The reference tokenizer for OpenAI models.\n- [OpenAI Cookbook: How to Count Tokens with tiktoken](https://cookbook.openai.com/examples/how_to_count_tokens_with_tiktoken?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques): Step-by-step guide to counting tokens accurately. Covers per-message overhead for the Chat Completions API.\n- [Anthropic Token Counting API](https://docs.anthropic.com/en/docs/build-with-claude/token-counting?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques): Anthropic's server-side token counting endpoint for Claude models.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('---\n\n*← Previous: [04: Summary Buffer Memory](../04_summary_buffer_memory/) · Next: [06: Vector-Store Memory](../06_vector_store_memory/) →*')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## 🧪 Try It Yourself\n\nThree small challenges to deepen your understanding. Each should take 10-30 minutes.\n\n### Challenge 1: Priority-based trimming\nModify `_trim()` so it scores each message (e.g., messages containing questions or names get higher priority) and evicts the lowest-priority message first instead of the oldest. Run a 15-turn conversation and compare recall against the default FIFO approach.\n\n### Challenge 2: Budget sweep\nRun the same conversation with `max_token_limit` set to 500, 1000, 2000, and 4000. For each budget, record the number of messages retained, the number evicted, and how many recall questions the agent answers correctly. Present results in a table.\n\n### Challenge 3: Token budget with summary overflow\nWhen `_trim()` evicts messages, pass them to a summarizer instead of discarding them. Prepend the summary as a system-prompt addition. Measure total tokens used per turn and compare against pure token buffer. This combines 05 Token Buffer with the approach from 03 Summary Memory.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--05-token-buffer-memory--token-buffer-memory)\n')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# SETUP (run separately): %pip install -q tiktoken openai python-dotenv\n\nimport os\n\nimport tiktoken\nfrom dotenv import load_dotenv\nfrom openai import OpenAI\n\nload_dotenv()  # reads OPENAI_API_KEY from .env\n\nclient = OpenAI()\nMODEL = "gpt-4o"\nENCODING = tiktoken.encoding_for_model(MODEL)\n\nassert os.getenv("OPENAI_API_KEY"), "Set OPENAI_API_KEY in your .env file"\n\ndef count_message_tokens(message: dict) -> int:\n    """Count tokens for one chat message, including per-message overhead.\n\n    Overhead (4 tokens per message):\n      <|im_start|> + role + content separator + <|im_end|>\n    """\n    overhead = 4\n    return overhead + len(ENCODING.encode(message["content"]))\n\n\n# Demo: count tokens for messages of different lengths\nsample_messages = [\n    {"role": "user", "content": "yes"},\n    {"role": "user", "content": "What is the capital of France?"},\n    {"role": "user", "content": (\n        "Write a Python function that computes the nth Fibonacci number "\n        "using dynamic programming with memoization."\n    )},\n]\n\nfor msg in sample_messages:\n    tokens = count_message_tokens(msg)\n    print(f"  {tokens:3d} tokens | \\"{msg[\'content\'][:70]}\\"")\n\nclass TokenBufferMemory:\n    """Token-aware conversation memory with a strict token budget."""\n\n    def __init__(\n        self,\n        model: str = "gpt-4o",\n        max_token_limit: int = 2048,\n        system_prompt: str | None = None,\n        max_response_tokens: int = 512,\n    ):\n        self.client = OpenAI()\n        self.model = model\n        self.max_token_limit = max_token_limit\n        self.system_prompt = system_prompt\n        self.max_response_tokens = max_response_tokens\n\n        # Select the correct encoding for the target model\n        self.encoding = tiktoken.encoding_for_model(model)\n\n        # Core data structure: the message buffer\n        self.messages: list[dict] = []\n\n        # Track evictions for inspection\n        self.eviction_log: list[dict] = []\n\n    # -- Token counting -----------------------------------------------\n    def count_tokens(self, message: dict) -> int:\n        """Count tokens for one message including per-message overhead."""\n        overhead = 4  # <|im_start|>, role, separator, <|im_end|>\n        return overhead + len(self.encoding.encode(message["content"]))\n\n    def total_tokens(self) -> int:\n        """Sum token counts across all stored messages."""\n        return sum(self.count_tokens(m) for m in self.messages)\n\n\n    # -- Eviction loop ------------------------------------------------\n    def _trim(self) -> None:\n        """Remove oldest messages until total tokens fit within budget."""\n        total = self.total_tokens()\n        while total > self.max_token_limit and len(self.messages) > 1:\n            removed = self.messages.pop(0)\n            removed_tokens = self.count_tokens(removed)\n            total -= removed_tokens\n            self.eviction_log.append({\n                "role": removed["role"],\n                "preview": removed["content"][:60],\n                "tokens_freed": removed_tokens,\n            })\n\n    # -- Chat ---------------------------------------------------------\n    def chat(self, user_input: str) -> str:\n        """Send a message, trim if over budget, return the response."""\n        self.messages.append({"role": "user", "content": user_input})\n        self._trim()\n\n        # Build the API payload\n        api_messages = []\n        if self.system_prompt:\n            api_messages.append({"role": "system", "content": self.system_prompt})\n        api_messages.extend(self.messages)\n\n        response = self.client.chat.completions.create(\n            model=self.model,\n            messages=api_messages,\n            max_tokens=self.max_response_tokens,\n        )\n\n        assistant_text = response.choices[0].message.content\n        self.messages.append({"role": "assistant", "content": assistant_text})\n\n        return assistant_text\n\n\n    # -- Utilities ----------------------------------------------------\n    def get_messages(self) -> list[dict]:\n        """Return a copy of the message history."""\n        return [m.copy() for m in self.messages]\n\n    def clear(self) -> None:\n        """Reset all messages and logs."""\n        self.messages.clear()\n        self.eviction_log.clear()\n\n    def __len__(self) -> int:\n        return len(self.messages)\n\n    def __repr__(self) -> str:\n        return (\n            f"TokenBufferMemory("\n            f"{len(self.messages)} msgs, "\n            f"{self.total_tokens()}/{self.max_token_limit} tokens)"\n        )\n\nmemory = TokenBufferMemory(\n    model="gpt-4o",\n    max_token_limit=2048,\n    system_prompt="You are a helpful, concise assistant. Keep replies under 2 sentences.",\n)\n\nexchanges = [\n    "Hi! My name is Alice and I\'m a machine-learning engineer.",\n    "I\'m building a project about agent memory systems.",\n    "What\'s my name and what am I working on?",  # recall test\n]\n\nfor msg in exchanges:\n    print(f"User:  {msg}")\n    reply = memory.chat(msg)\n    print(f"Agent: {reply}")\n    print(f"       [{memory.total_tokens()} / {memory.max_token_limit} tokens, "\n          f"{len(memory)} messages]\\n")\n\nsmall_memory = TokenBufferMemory(\n    model="gpt-4o",\n    max_token_limit=300,  # deliberately small to trigger eviction\n    system_prompt="Reply in one short sentence.",\n)\n\ndemo_messages = [\n    "My name is Bob and I live in Tokyo.",\n    "I have two cats named Mochi and Sushi.",\n    "My favorite language is Rust.",\n    "I work at a robotics startup with 20 engineers.",\n    "What do you remember about me?",  # some early facts will be gone\n]\n\nfor msg in demo_messages:\n    tokens_before = small_memory.total_tokens()\n    reply = small_memory.chat(msg)\n    tokens_after = small_memory.total_tokens()\n    print(f"User:  {msg}")\n    print(f"Agent: {reply}")\n    print(f"       [tokens: {tokens_before} -> {tokens_after}, "\n          f"messages: {len(small_memory)}]\\n")\n\n# Show what got evicted\nif small_memory.eviction_log:\n    print("--- Eviction log ---")\n    for entry in small_memory.eviction_log:\n        print(f"  Removed ({entry[\'role\']}): "\n              f"\\"{entry[\'preview\']}\\" "\n              f"({entry[\'tokens_freed\']} tokens freed)")\n\ncomparison_messages = [\n    {"role": "user", "content": "yes"},\n    {"role": "assistant", "content": "No problem!"},\n    {"role": "user", "content": (\n        "Here\'s my entire configuration file:\\n"\n        "import logging\\n"\n        "import os\\n"\n        "from pathlib import Path\\n\\n"\n        "BASE_DIR = Path(__file__).resolve().parent\\n"\n        "SECRET_KEY = os.environ[\'SECRET_KEY\']\\n"\n        "DEBUG = os.environ.get(\'DEBUG\', \'False\') == \'True\'\\n"\n        "ALLOWED_HOSTS = os.environ.get(\'ALLOWED_HOSTS\', \'\').split(\',\')\\n"\n        "DATABASES = {\\n"\n        "    \'default\': {\\n"\n        "        \'ENGINE\': \'django.db.backends.postgresql\',\\n"\n        "        \'NAME\': os.environ[\'DB_NAME\'],\\n"\n        "        \'USER\': os.environ[\'DB_USER\'],\\n"\n        "        \'PASSWORD\': os.environ[\'DB_PASSWORD\'],\\n"\n        "        \'HOST\': os.environ.get(\'DB_HOST\', \'localhost\'),\\n"\n        "        \'PORT\': os.environ.get(\'DB_PORT\', \'5432\'),\\n"\n        "    }\\n"\n        "}\\n"\n        "LOGGING = {\\n"\n        "    \'version\': 1,\\n"\n        "    \'handlers\': {\\n"\n        "        \'console\': {\'class\': \'logging.StreamHandler\'},\\n"\n        "    },\\n"\n        "    \'root\': {\'handlers\': [\'console\'], \'level\': \'WARNING\'},\\n"\n        "}\\n"\n    )},\n]\n\nprint("Message count vs. token count:\\n")\ntotal_tokens = 0\nfor i, msg in enumerate(comparison_messages):\n    tokens = count_message_tokens(msg)\n    total_tokens += tokens\n    preview = msg["content"][:50].replace("\\n", " ")\n    suffix = "..." if len(msg["content"]) > 50 else ""\n    print(f"  Message {i + 1} ({msg[\'role\']:>9}): {tokens:4d} tokens "\n          f"| \\"{preview}{suffix}\\"")\n\nprint(f"\\n  Total: {total_tokens} tokens across {len(comparison_messages)} messages")\nprint(f"\\n  A 3-message sliding window keeps all three.")\nprint(f"  A 50-token budget would drop message 3 "\n      f"({count_message_tokens(comparison_messages[2])} tokens).")\nprint(f"  Token-based trimming makes the right call here.")', language="python", label="Recovered notebook code")
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
