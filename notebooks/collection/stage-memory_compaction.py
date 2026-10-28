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
    mo.md('# Memory Compaction\n\n> **Reduce storage and token cost through progressive summarization: from raw transcript to key points to one-liner to tags.**\n\nImagine you record every meeting at work, word for word. After a year you have thousands of pages. Most of those pages are filler: "Let me pull that up," "Sure, sounds good," "Sorry, you were saying?" The real decisions and action items fill maybe 10% of the text.\n\nNow imagine you keep four versions of each meeting. The full transcript. A bullet-point summary. A one-liner. A set of tags. You\'d scan the tags for quick searches. You\'d read the one-liner for context. You\'d only open the full transcript when exact wording matters.\n\nMemory Compaction applies this idea to an agent\'s memory store. Raw memories (full conversation transcripts, detailed tool outputs, verbose reasoning traces) consume significant storage and token budget. Token budget is the cost of including text in a prompt. Compaction transforms verbose records into denser versions that keep essential information and discard filler.\n\nThis technique draws on Tiago Forte\'s Progressive Summarization method for personal knowledge management. Each memory exists at multiple fidelity levels. Level 0 (L0) is the raw transcript. Level 1 (L1) extracts key points. Level 2 (L2) distills those into a single sentence. Level 3 (L3) reduces everything to tags and entity references (structured labels like person names, dates, and project names).\n\nThe practical benefit is dramatic. A compacted memory store can hold 10x to 100x more semantic content in the same storage budget. Retrieval gets faster because compressed entries are smaller. The agent can choose the right level of detail for each situation.\n\n**By the end of this notebook you\'ll understand:**\n- How to compress memories through four progressive levels.\n- How to build a compaction engine that uses LLM calls for each level.\n- How to schedule compaction based on age and access patterns.\n- How to retrieve memories at any fidelity level on demand.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Key Concepts\n\n- **Progressive Summarization Levels**: A hierarchy of compression. L0 is the raw text. L1 has key points. L2 is a one-line summary. L3 is tags and entity references only. Each level trades fidelity (completeness) for compactness (smaller size).\n- **Lossy vs. Lossless Compression**: Lossless techniques (like extracting structured fields from unstructured text) keep all information. Lossy techniques (like summarization) intentionally discard detail. Compaction uses both strategically.\n- **Detail Levels on Retrieval**: The ability to retrieve a memory at any compaction level. Quick scans use L2 or L3. Deep dives request L0 or L1. This lets the agent budget context tokens precisely.\n- **Compaction Scheduling**: Policies for when compression happens. Options include age-based (compress after N hours), access-based (compress after M turns without access), and storage-pressure-based (compress when the store exceeds capacity).\n- **Reversibility**: Keeping the original L0 in cold storage (cheap, slower storage) so compaction is non-destructive. The agent can always "zoom in" to the raw memory if a summary proves insufficient.\n- **Storage-Fidelity Tradeoff**: The engineering decision about how much detail to retain at each level. You\'re balancing storage cost against information loss.\n- **Entity Extraction**: Pulling structured entities (people, dates, projects, decisions) from raw text as part of the compaction process. This creates a queryable index alongside the compressed memories.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Architecture\n\n<p align="center">\n  <img src="../../images/diagrams/15_memory_compaction.svg" alt="diagram" width="720"/>\n</p>\n\n<details><summary>Mermaid source</summary>\n\n```mermaid\nflowchart LR\n    RM["Raw Memory\\n(L0: Full fidelity)"] --> CE["Compaction\\nEngine"]\n\n    CE --> L1["L1: Key Points\\n(~30% of original)"]\n    L1 --> CE2["Compaction\\nEngine"]\n    CE2 --> L2["L2: One-liner\\n(~5% of original)"]\n    L2 --> CE3["Compaction\\nEngine"]\n    CE3 --> L3["L3: Tags Only\\n(~1% of original)"]\n\n    RM -->|"Archive original"| CS["Cold Storage"]\n\n    RQ["Retrieval Query"] --> LS["Level Selector"]\n    LS -->|"Quick scan"| L3\n    LS -->|"Summary"| L2\n    LS -->|"Moderate detail"| L1\n    LS -->|"Full detail"| CS\n\n    style RM fill:#2d4a7a,stroke:#49a,color:#fff\n    style L1 fill:#2d5a5a,stroke:#4aa,color:#fff\n    style L2 fill:#5a5a2d,stroke:#aa4,color:#fff\n    style L3 fill:#5a2d2d,stroke:#a44,color:#fff\n```\n\n</details>\n\n**Data flow**: A raw memory (L0) enters the system at full fidelity. The compaction engine progressively compresses it through three stages. L1 extracts key points (roughly 30% of the original tokens). L2 distills to a single-sentence summary (roughly 5%). L3 keeps only tags and entity references (roughly 1%).\n\nThe original L0 is archived in cold storage so you can always recover full detail. When a retrieval query arrives, the level selector picks the right detail level. It considers the query\'s needs and the available context budget.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Setup\n\nInstall dependencies and configure API access. You'll need an OpenAI API key stored in a `.env` file or as an environment variable.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Import the OpenAI SDK and standard library helpers. The API key loads from a `.env` file.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Implementation\n\nWe'll build four components:\n\n1. **CompactionLevel** and **CompactedMemory**: data structures that hold content at multiple fidelity levels.\n2. **CompactionEngine**: uses LLM calls to compress from one level to the next.\n3. **MemoryStore**: stores memories and supports level-aware retrieval.\n4. **CompactionScheduler**: decides which memories are due for further compression.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Data Structures\n\nThink of a filing system with four drawers. The top drawer holds full documents. The second holds bullet-point summaries clipped to each document. The third holds sticky-note synopses. The bottom drawer holds index cards with only keywords. Each drawer gives you a different speed-vs-detail tradeoff.\n\n`CompactionLevel` is an integer enum that labels the four drawers. `CompactedMemory` holds the content for whichever levels have been computed so far.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Compaction Engine\n\nThe engine does the actual compression. Each transition (L0 to L1, L1 to L2, L2 to L3) uses a different LLM prompt tailored to the target format.\n\n- **L0 to L1**: Extract 3 to 5 key points as bullet items.\n- **L1 to L2**: Distill those bullets into a single sentence.\n- **L2 to L3**: Extract only entity names and topic tags as a JSON object.\n\nEach step is a separate LLM call. This keeps prompts focused and outputs predictable.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("The `compact` method orchestrates progressive compression. It walks from the memory's current level up to the target level, calling the right method at each step. For example, compacting from L0 to L3 runs L0 to L1, then L1 to L2, then L2 to L3 in sequence.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Memory Store\n\nThe store holds all memories and their compaction levels. It also manages cold storage: when a memory gets compacted past L0, the original raw text moves to a separate archive. This keeps the active store small while preserving full-fidelity access on demand.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("The `retrieve` method is where multi-level access shines. You request a specific detail level. If it's already computed, you get it instantly. If the raw L0 was archived, it comes from cold storage. If the level hasn't been computed yet, the store triggers on-demand compaction.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Compaction Scheduler\n\nIn a production system you don't compact every memory by hand. The scheduler checks which memories are due for further compression. It uses two policies:\n\n- **Age-based**: compress memories older than a threshold (e.g., 24 hours).\n- **Idle-based**: compress memories that haven't been accessed recently.\n\nYou can add more policies (storage-pressure, access-frequency) using the same pattern.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Example Run\n\nLet's walk through a complete scenario. We'll add three realistic agent memories, compact them through all four levels, and see how storage shrinks at each step.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('First, create the engine and store. Then add three raw memories that an agent might collect during a workday.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('We add a third memory: a product roadmap discussion. After loading all three, we check their character counts at L0.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Step-by-Step Compaction\n\nLet's compact the first memory one level at a time. You'll see exactly what the LLM produces at each stage.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Now compress from L1 to L2 (single sentence), then from L2 to L3 (tags only).')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Batch Compaction\n\nCompact the remaining two memories to L3 in a single call each. The engine runs all intermediate steps automatically.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Level-Aware Retrieval\n\nThe key advantage of multi-level storage: you pick the right resolution for each query. A broad search scans L3 tags. A focused lookup reads L1 key points. A full audit retrieves L0 from cold storage.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Storage Savings\n\nLet's measure how much space compaction saves across all three memories.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Scheduled Compaction\n\nIn a real system, you don't compact by hand. The scheduler runs periodically and compresses memories that meet the policy criteria. Let's demonstrate with a short idle threshold.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Tradeoffs\n\n### When Memory Compaction Works Well\n\n- **Long-running agents** that accumulate thousands of raw memories over days or weeks. Compaction keeps the store searchable without blowing up storage costs.\n- **Token-constrained systems** where retrieved context must fit within tight budget limits. L2 and L3 summaries let you pack more memories into a single prompt.\n- **Multi-resolution retrieval**: quick tag-based filtering at L3, then expanding top results to L1 for richer context. This two-pass pattern is fast and cost-effective.\n\n### When It Breaks Down\n\n- **Latency-sensitive writes.** Each compaction step requires an LLM call. If you need instant writes, you'll need to batch compaction into background jobs. That adds operational complexity.\n- **Exact-recall tasks.** Summarization is lossy. If the agent later needs the precise wording from turn 47, the L2 summary won't have it. Cold storage retrieval helps, but adds latency.\n- **Compaction cost.** Each memory requires up to 3 LLM calls to reach L3. For high-throughput agents producing hundreds of memories per hour, the compaction cost may rival the storage savings.\n- **Small memory stores.** If your agent has fewer than 100 memories, the overhead of multi-level compaction outweighs the benefit. Buffer or window memory is a better fit.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Further Reading\n\n- Forte, ["Progressive Summarization: A Practical Technique for Designing Discoverable Notes,"](https://fortelabs.com/blog/progressive-summarization-a-practical-technique-for-designing-discoverable-notes/?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques) 2017. The original progressive summarization method for personal knowledge management. Directly inspires the multi-level compaction approach.\n- Xu et al., ["RECOMP: Improving Retrieval-Augmented LMs with Compression and Selective Augmentation,"](https://arxiv.org/abs/2310.04408) 2023. Compresses retrieved documents before injecting them into context. Shows that compressed content can match or exceed raw content performance.\n- Chevalier et al., ["Adapting Language Models to Compress Contexts,"](https://arxiv.org/abs/2305.14788) 2023. Trains models to produce compact context representations. A learned approach to memory compaction.\n- Jiang et al., ["LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression,"](https://arxiv.org/abs/2310.06839) 2023. Prompt compression techniques that reduce token count while preserving task performance.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('---\n\n*← Previous: [14 - Memory Consolidation](../14_memory_consolidation/) · Next: [16 - Self-Reflection Memory](../16_self_reflection_memory/) →*')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## 🧪 Try It Yourself\n\nThree small challenges to deepen your understanding. Each should take 10-30 minutes.\n\n### Challenge 1: Custom intermediate level\nAdd a new `L1_5_HIGHLIGHTS` level to `CompactionLevel` between L1 (key points) and L2 (one-liner). Write a `compact_to_l1_5()` method in `CompactionEngine` that extracts only the top 2 most important points. Test it on 5 memories and compare output length against L1 and L2.\n\n### Challenge 2: Compression ratio analysis\nCompact 10 memories through all four levels. For each memory, measure the token count at L0, L1, L2, and L3. Compute the compression ratio (L0 tokens / LN tokens) at each level. Plot a bar chart showing average compression ratios across the 10 memories.\n\n### Challenge 3: Level-aware retrieval\nModify `MemoryStore.retrieve()` to search L2 representations first (fast, cheap) and then fetch the L0 or L1 version of the top results (detailed, accurate). Measure retrieval quality and token cost against always searching L0. This connects to the hybrid retrieval ideas in 20 Memory Retrieval Patterns.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--15-memory-compaction--memory-compaction)')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# SETUP (run separately): %pip install -q openai python-dotenv\n\nimport os\nimport json\nimport time\nimport uuid\nimport re\nfrom enum import IntEnum\nfrom dataclasses import dataclass, field\nfrom dotenv import load_dotenv\nfrom openai import OpenAI\n\nload_dotenv()  # reads OPENAI_API_KEY from .env\n\nclient = OpenAI()  # picks up OPENAI_API_KEY automatically\nMODEL = "gpt-4o-mini"\n\nassert os.getenv("OPENAI_API_KEY"), "Set OPENAI_API_KEY in your .env file" \n\nclass CompactionLevel(IntEnum):\n    """Four progressive compression levels."""\n    L0_RAW = 0          # Full original text\n    L1_KEY_POINTS = 1   # Bullet-point extraction (~30% of L0)\n    L2_SUMMARY = 2      # Single-sentence distillation (~5% of L0)\n    L3_TAGS = 3         # Tags and entity labels only (~1% of L0)\n\n\n@dataclass\nclass CompactedMemory:\n    """A memory stored at one or more compaction levels."""\n    memory_id: str\n    levels: dict          # CompactionLevel -> str content\n    entities: list        # Extracted entity names\n    created_at: float     # Unix timestamp\n    last_accessed: float  # Unix timestamp\n    access_count: int = 0\n    current_level: int = 0  # Highest (most compressed) level computed\n\n    def char_count_at(self, level: int) -> int:\n        """Return character count at a given level, or 0 if not computed."""\n        content = self.levels.get(level, "")\n        return len(content)\n\nclass CompactionEngine:\n    """Compresses memories from one level to the next using LLM calls."""\n\n    def __init__(self, client: OpenAI, model: str = "gpt-4o-mini"):\n        self.client = client\n        self.model = model\n\n    def _call_llm(self, system_prompt: str, user_content: str) -> str:\n        """Send a single chat completion request."""\n        response = self.client.chat.completions.create(\n            model=self.model,\n            messages=[\n                {"role": "system", "content": system_prompt},\n                {"role": "user", "content": user_content},\n            ],\n            temperature=0.0,\n        )\n        return response.choices[0].message.content\n\n    def compact_to_l1(self, raw_text: str) -> str:\n        """L0 -> L1: Extract 3-5 key points as bullet items."""\n        prompt = (\n            "Extract the 3 to 5 most important points from this text. "\n            "Return only bullet points, one per line, starting with \'- \'. "\n            "Keep each point to one sentence."\n        )\n        return self._call_llm(prompt, raw_text)\n\n    def compact_to_l2(self, key_points: str) -> str:\n        """L1 -> L2: Distill key points into a single sentence."""\n        prompt = (\n            "Distill these key points into a single sentence of at most "\n            "25 words. Return only the sentence, no extra text."\n        )\n        return self._call_llm(prompt, key_points)\n\n    def compact_to_l3(self, summary: str) -> tuple:\n        """L2 -> L3: Extract tags and entities as structured data.\n\n        Returns (tag_string, entity_list).\n        """\n        prompt = (\n            "Extract entity tags from this text. Return a JSON object with "\n            "two keys: \\"tags\\" (topic keywords as a list of strings) and "\n            "\\"entities\\" (proper nouns like people, projects, tools as a "\n            "list of strings). Return only valid JSON, no markdown fences."\n        )\n        raw = self._call_llm(prompt, summary)\n        # Strip markdown code fences if the model wraps the JSON\n        cleaned = re.sub(r"^```(?:json)?\\n?|```$", "", raw.strip())\n        parsed = json.loads(cleaned)\n        tag_str = ", ".join(parsed.get("tags", []))\n        entities = parsed.get("entities", [])\n        return tag_str, entities\n\n    def compact(self, memory: CompactedMemory, target_level: int) -> CompactedMemory:\n        """Progressively compact a memory up to the target level.\n\n        Runs each intermediate step if needed. For example, compacting\n        from L0 to L3 runs L0->L1, L1->L2, and L2->L3 in sequence.\n        """\n        current = memory.current_level\n        while current < target_level:\n            next_level = current + 1\n            source_text = memory.levels[current]\n\n            if next_level == CompactionLevel.L1_KEY_POINTS:\n                memory.levels[next_level] = self.compact_to_l1(source_text)\n            elif next_level == CompactionLevel.L2_SUMMARY:\n                memory.levels[next_level] = self.compact_to_l2(source_text)\n            elif next_level == CompactionLevel.L3_TAGS:\n                tag_str, entities = self.compact_to_l3(source_text)\n                memory.levels[next_level] = tag_str\n                memory.entities = entities\n\n            memory.current_level = next_level\n            current = next_level\n\n        return memory\n\nclass MemoryStore:\n    """Stores memories at multiple compaction levels with cold storage."""\n\n    def __init__(self, engine: CompactionEngine):\n        self.engine = engine\n        self.memories: dict[str, CompactedMemory] = {}\n        self.cold_storage: dict[str, str] = {}  # memory_id -> L0 text\n\n    def add(self, raw_text: str, memory_id: str | None = None) -> CompactedMemory:\n        """Add a new raw memory at L0."""\n        if memory_id is None:\n            memory_id = uuid.uuid4().hex[:8]\n        now = time.time()\n        memory = CompactedMemory(\n            memory_id=memory_id,\n            levels={CompactionLevel.L0_RAW: raw_text},\n            entities=[],\n            created_at=now,\n            last_accessed=now,\n        )\n        self.memories[memory_id] = memory\n        return memory\n\n    def compact(self, memory_id: str, target_level: int) -> CompactedMemory:\n        """Compact a memory to the target level. Archive L0 to cold storage."""\n        memory = self.memories[memory_id]\n        self.engine.compact(memory, target_level)\n\n        # Move L0 to cold storage after any compaction\n        if target_level >= CompactionLevel.L1_KEY_POINTS:\n            if memory_id not in self.cold_storage:\n                self.cold_storage[memory_id] = memory.levels[CompactionLevel.L0_RAW]\n\n        return memory\n\n    def retrieve(self, memory_id: str, level: int | None = None) -> str:\n        """Retrieve a memory at the requested detail level.\n\n        If the level hasn\'t been computed yet, compaction runs on demand.\n        If L0 is requested and has been archived, it comes from cold storage.\n        """\n        memory = self.memories[memory_id]\n        memory.last_accessed = time.time()\n        memory.access_count += 1\n\n        if level is None:\n            level = memory.current_level\n\n        # Check if the level is already available\n        if level in memory.levels:\n            return memory.levels[level]\n\n        # L0 might be in cold storage\n        if level == CompactionLevel.L0_RAW and memory_id in self.cold_storage:\n            return self.cold_storage[memory_id]\n\n        # Need a level that hasn\'t been computed yet: compact on demand\n        if level > memory.current_level:\n            self.compact(memory_id, level)\n            return memory.levels[level]\n\n        return memory.levels[memory.current_level]\n\n    def storage_report(self) -> dict:\n        """Measure character counts at each compaction level."""\n        totals = {level: 0 for level in CompactionLevel}\n        for memory in self.memories.values():\n            for level_key, content in memory.levels.items():\n                totals[level_key] += len(content)\n        cold_chars = sum(len(v) for v in self.cold_storage.values())\n        return {\n            "active_levels": {\n                CompactionLevel(k).name: v for k, v in totals.items()\n            },\n            "cold_storage_chars": cold_chars,\n            "total_memories": len(self.memories),\n        }\n\nclass CompactionScheduler:\n    """Selects memories for compaction based on age and access patterns."""\n\n    def __init__(\n        self,\n        store: MemoryStore,\n        age_threshold_seconds: float = 86400,   # 24 hours\n        idle_threshold_seconds: float = 3600,    # 1 hour without access\n    ):\n        self.store = store\n        self.age_threshold = age_threshold_seconds\n        self.idle_threshold = idle_threshold_seconds\n\n    def get_candidates(self) -> list:\n        """Find memories eligible for further compaction.\n\n        Returns a list of (memory_id, target_level) tuples.\n        """\n        now = time.time()\n        candidates = []\n        for mid, memory in self.store.memories.items():\n            # Already at maximum compression\n            if memory.current_level >= CompactionLevel.L3_TAGS:\n                continue\n\n            age = now - memory.created_at\n            idle_time = now - memory.last_accessed\n            next_level = memory.current_level + 1\n\n            if age > self.age_threshold:\n                candidates.append((mid, next_level))\n            elif idle_time > self.idle_threshold:\n                candidates.append((mid, next_level))\n\n        return candidates\n\n    def run(self) -> list:\n        """Compact all eligible memories. Return list of compacted IDs."""\n        candidates = self.get_candidates()\n        compacted_ids = []\n        for mid, target_level in candidates:\n            self.store.compact(mid, target_level)\n            compacted_ids.append(mid)\n            print(f"  Compacted {mid} to {CompactionLevel(target_level).name}")\n        return compacted_ids\n\nengine = CompactionEngine(client=client, model=MODEL)\nstore = MemoryStore(engine=engine)\n\n# Memory 1: A CI/CD planning conversation\nmemory_1 = store.add(\n    memory_id="cicd-plan",\n    raw_text=(\n        "User: We need to set up CI/CD for the new microservices project. "\n        "We\'re using Kubernetes on AWS EKS. The team uses GitHub for version control. "\n        "Assistant: I\'ll help you set up CI/CD for your Kubernetes microservices on "\n        "AWS EKS. I recommend GitHub Actions for the pipeline. Each service gets its "\n        "own workflow file. The pipeline should build a Docker image, push it to ECR, "\n        "then deploy via Helm charts. User: Sounds good. What about staging vs "\n        "production? Assistant: Use separate EKS namespaces for staging and production. "\n        "The staging deploy triggers on every push to main. Production requires a "\n        "manual approval step in the GitHub Actions workflow. User: What about "\n        "rollbacks? Assistant: Helm tracks release history. Run \'helm rollback\' to "\n        "revert to any previous version. Set up health checks so Kubernetes "\n        "auto-restarts unhealthy pods. User: Great, let\'s go with that plan."\n    ),\n)\n\n# Memory 2: A debugging session\nmemory_2 = store.add(\n    memory_id="debug-500",\n    raw_text=(\n        "User: The checkout service is throwing 500 errors since yesterday\'s deploy. "\n        "About 15% of requests fail. Assistant: Let me help debug that. What changed "\n        "in yesterday\'s deploy? User: We updated the payment gateway SDK from v2.3 to "\n        "v3.0 and added a new discount calculation module. Assistant: The payment SDK "\n        "jump from v2 to v3 is likely the cause. v3 changed the response format from "\n        "XML to JSON. Your deserialization code probably expects XML. Check the "\n        "PaymentResponseParser class. User: You\'re right. The parser was calling "\n        "xml.etree.parse on JSON responses. I\'ve switched it to json.loads and the "\n        "errors stopped. Assistant: Good catch. I\'d also recommend adding a response "\n        "format check so future SDK updates don\'t break silently. Log the content-type "\n        "header before parsing."\n    ),\n)\n\n# Memory 3: A product roadmap discussion\nmemory_3 = store.add(\n    memory_id="q2-roadmap",\n    raw_text=(\n        "User: We need to plan the Q2 product roadmap. Main themes are mobile app "\n        "improvements and API v2 launch. The team has 12 engineers. Assistant: Let\'s "\n        "break Q2 into two tracks. Track A: Mobile improvements with 5 engineers. "\n        "Track B: API v2 with 7 engineers. User: For mobile, the priorities are "\n        "offline mode, push notifications, and biometric login. Assistant: I\'d suggest "\n        "this order: biometric login first (2 weeks, unblocks other features), then "\n        "push notifications (3 weeks, high user demand), then offline mode (5 weeks, "\n        "most complex). User: For API v2, we need rate limiting, webhook support, and "\n        "OAuth2 scopes. Assistant: Start with OAuth2 scopes since other features "\n        "depend on the auth model. Then rate limiting (protects the new endpoints). "\n        "Webhooks last because they need the stable endpoint structure. User: Timeline "\n        "works. Let\'s write this up and share with the team."\n    ),\n)\n\nprint(f"Added {len(store.memories)} memories to the store.")\nfor mid, mem in store.memories.items():\n    chars = mem.char_count_at(CompactionLevel.L0_RAW)\n    print(f"  {mid}: {chars} characters at L0")\n\n# Compact cicd-plan from L0 to L1 (key points)\nstore.compact("cicd-plan", CompactionLevel.L1_KEY_POINTS)\nmem = store.memories["cicd-plan"]\n\nprint("=== L0: Raw transcript ===")\nprint(mem.levels[CompactionLevel.L0_RAW][:200] + "...")\nprint(f"\\n({mem.char_count_at(CompactionLevel.L0_RAW)} chars)")\n\nprint("\\n=== L1: Key points ===")\nprint(mem.levels[CompactionLevel.L1_KEY_POINTS])\nprint(f"\\n({mem.char_count_at(CompactionLevel.L1_KEY_POINTS)} chars)")\n\nratio = mem.char_count_at(CompactionLevel.L1_KEY_POINTS) / mem.char_count_at(CompactionLevel.L0_RAW)\nprint(f"\\nCompression ratio: {ratio:.0%} of original")\n\n# L1 -> L2 -> L3\nstore.compact("cicd-plan", CompactionLevel.L3_TAGS)\nmem = store.memories["cicd-plan"]\n\nprint("=== L2: One-sentence summary ===")\nprint(mem.levels[CompactionLevel.L2_SUMMARY])\nprint(f"({mem.char_count_at(CompactionLevel.L2_SUMMARY)} chars)")\n\nprint("\\n=== L3: Tags only ===")\nprint(mem.levels[CompactionLevel.L3_TAGS])\nprint(f"({mem.char_count_at(CompactionLevel.L3_TAGS)} chars)")\n\nprint(f"\\nExtracted entities: {mem.entities}")\n\n# Show the full compression ladder\nprint("\\n=== Compression ladder ===")\nfor level in CompactionLevel:\n    if level in mem.levels:\n        chars = len(mem.levels[level])\n        pct = chars / mem.char_count_at(CompactionLevel.L0_RAW) * 100\n        print(f"  {level.name}: {chars} chars ({pct:.1f}% of L0)")\n\nfor mid in ["debug-500", "q2-roadmap"]:\n    store.compact(mid, CompactionLevel.L3_TAGS)\n    mem = store.memories[mid]\n    l0_chars = mem.char_count_at(CompactionLevel.L0_RAW)\n    l3_chars = mem.char_count_at(CompactionLevel.L3_TAGS)\n    print(f"{mid}:")\n    print(f"  L0: {l0_chars} chars")\n    print(f"  L3: {l3_chars} chars ({l3_chars / l0_chars:.1%} of L0)")\n    print(f"  Entities: {mem.entities}")\n    print()\n\nprint("--- Retrieving \'debug-500\' at different levels ---\\n")\n\nfor level in CompactionLevel:\n    content = store.retrieve("debug-500", level=level)\n    preview = content[:120].replace("\\n", " ")\n    if len(content) > 120:\n        preview += "..."\n    print(f"{level.name}:")\n    print(f"  {preview}")\n    print(f"  ({len(content)} chars)\\n")\n\nreport = store.storage_report()\n\nprint(f"Total memories: {report[\'total_memories\']}")\nprint(f"\\nActive store by level:")\nfor level_name, chars in report["active_levels"].items():\n    print(f"  {level_name}: {chars:,} chars")\nprint(f"\\nCold storage (archived L0): {report[\'cold_storage_chars\']:,} chars")\n\n# Calculate overall compression\ntotal_l0 = sum(\n    mem.char_count_at(CompactionLevel.L0_RAW)\n    for mem in store.memories.values()\n)\ntotal_l3 = sum(\n    mem.char_count_at(CompactionLevel.L3_TAGS)\n    for mem in store.memories.values()\n)\nprint(f"\\nTotal L0 content: {total_l0:,} chars")\nprint(f"Total L3 content: {total_l3:,} chars")\nprint(f"Compression ratio (L3/L0): {total_l3 / total_l0:.1%}")\nprint(f"\\nIf you retrieve at L3, you use ~{total_l3 / total_l0:.0%} of the tokens.")\nprint(f"The original text stays safe in cold storage for when you need it.")\n\n# Create a fresh store for the scheduling demo\nsched_engine = CompactionEngine(client=client, model=MODEL)\nsched_store = MemoryStore(engine=sched_engine)\n\n# Add two memories\nsched_store.add(\n    memory_id="old-mem",\n    raw_text="User asked about Python virtual environments. We discussed venv, "\n    "conda, and poetry. Recommended poetry for dependency management in "\n    "production projects. Covered lock files and reproducible builds.",\n)\n\nsched_store.add(\n    memory_id="new-mem",\n    raw_text="User wants to learn about async programming in Python. Discussed "\n    "asyncio event loops, coroutines, and the await keyword. Recommended "\n    "starting with simple HTTP requests using aiohttp.",\n)\n\n# Backdate the first memory so it looks old\nsched_store.memories["old-mem"].created_at -= 90000   # ~25 hours ago\nsched_store.memories["old-mem"].last_accessed -= 90000\n\n# Create scheduler with 24-hour age threshold\nscheduler = CompactionScheduler(\n    store=sched_store,\n    age_threshold_seconds=86400,   # 24 hours\n    idle_threshold_seconds=3600,   # 1 hour\n)\n\nprint("Before scheduling:")\nfor mid, mem in sched_store.memories.items():\n    print(f"  {mid}: level={CompactionLevel(mem.current_level).name}")\n\nprint("\\nRunning scheduler...")\ncompacted = scheduler.run()\n\nprint(f"\\nCompacted {len(compacted)} memories.")\nprint("\\nAfter scheduling:")\nfor mid, mem in sched_store.memories.items():\n    print(f"  {mid}: level={CompactionLevel(mem.current_level).name}")', language="python", label="Recovered notebook code")
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
