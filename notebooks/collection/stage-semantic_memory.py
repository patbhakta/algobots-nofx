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
    mo.md('# Semantic Memory\n\n> **Extract and store generalized facts from conversations, building a persistent knowledge base that transcends any single interaction.**\n\nYou know that Paris is the capital of France. But you probably can\'t remember the exact moment you learned it. That\'s semantic memory at work: knowledge distilled from experience into stable, context-free facts. The "when" and "how" fade away. The fact itself remains.\n\nAI agents face the same challenge. A user mentions their favorite language is Python in session one, their team size in session two, and their deployment target in session three. Without semantic memory, each session starts from zero. With it, the agent builds a growing profile of distilled facts. Over time it stops asking the same questions. It anticipates needs based on what it already knows.\n\nThis notebook shows you how to build a semantic memory system from scratch using the **OpenAI SDK**. You\'ll extract facts from conversations with an LLM call, store them with vector embeddings (numerical representations of meaning), detect duplicates and contradictions, and retrieve relevant facts for future prompts.\n\n**By the end you\'ll understand:**\n- How to extract clean, declarative facts from messy conversation text.\n- How embedding similarity catches duplicates that string matching misses.\n- How to detect and resolve contradictions when users change their minds.\n- When semantic memory helps and when it quietly fails.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Key Concepts\n\n- **Semantic memory**: A store of general facts and knowledge, separate from specific episodes. In cognitive science, Endel Tulving coined this term in 1972 to distinguish "knowing that" from "remembering when."\n- **Fact extraction**: Pulling declarative statements from conversation text using an LLM prompt. "Oh yeah, I switched to a Mac last month" becomes the fact: "User uses macOS."\n- **Embedding**: A list of numbers (a vector) that captures the meaning of a piece of text. Texts with similar meaning have embeddings that point in similar directions. We use embeddings to compare facts by meaning, not by exact wording.\n- **Cosine similarity**: A measure of how similar two vectors are. It ranges from -1 (opposite) to 1 (identical direction). We use it to compare embeddings.\n- **Deduplication**: Detecting when a new fact means the same thing as one already stored. "I use a Mac" and "My laptop runs macOS" are the same fact. Cosine similarity catches this even though the words differ.\n- **Contradiction detection**: Identifying when a new fact conflicts with an existing one. "I use Windows" contradicts a stored "User uses macOS." The system must decide which to keep (usually the newer one).\n- **Confidence score**: A number from 0.0 to 1.0 that represents how certain we are about a fact. Explicit statements get high confidence. Inferred facts get lower confidence. Repeated mentions boost confidence.\n- **Context injection**: Inserting retrieved facts into the system prompt so the LLM can use them when generating a response.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Architecture\n\n<p align="center">\n  <img src="../../images/diagrams/10_semantic_memory.svg" alt="diagram" width="720"/>\n</p>\n\n<details><summary>Mermaid source</summary>\n\n```mermaid\nflowchart LR\n    Conv["Conversation"] --> Extractor["Fact Extractor\\n(LLM call)"]\n    Extractor --> DedupCheck["Dedup / Conflict\\nChecker"]\n    DedupCheck -- "new fact" --> KB["Knowledge Base\\n(facts + confidence\\n+ timestamps)"]\n    DedupCheck -- "duplicate" --> Merge["Merge / Update\\nConfidence"]\n    Merge --> KB\n    DedupCheck -- "contradiction" --> Resolve["Resolve Conflict\\n(prefer recent)"]\n    Resolve --> KB\n    NewQuery["New Query"] --> Search["Semantic Search\\n(embedding similarity)"]\n    KB --> Search\n    Search --> Injection["Context Injection"]\n    Injection --> LLM["LLM"]\n    LLM --> Response["Response"]\n```\n\n</details>\n\nThe diagram shows the two main flows. **Write path (left to right):** after each conversation, a fact extractor (an LLM call) pulls out declarative facts. Each fact runs through a dedup/conflict checker that compares it against the existing knowledge base. New facts are added. Duplicates merge and boost confidence. Contradictions are resolved by keeping the newer statement.\n\n**Read path (bottom):** when the agent needs to respond, it embeds the current query, searches the knowledge base for relevant facts, and injects them into the prompt. The LLM sees accumulated knowledge from all past sessions.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Setup\n\nInstall dependencies and configure API access. We use the OpenAI SDK for both chat completions and embeddings.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Import all libraries and load the API key from a `.env` file.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Implementation\n\nWe'll build a `SemanticMemory` class in four parts:\n\n1. **Fact data structure** and a helper for cosine similarity.\n2. **Embedding and extraction**: turning conversations into facts with vector representations.\n3. **Deduplication and contradiction detection**: comparing new facts against existing ones.\n4. **Retrieval and chat**: fetching relevant facts and injecting them into prompts.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Part 1: Fact data structure\n\nThink of a filing cabinet where each card holds one fact. Every card has the fact itself, a confidence score, timestamps, and an embedding for search. We also need a quick way to measure how similar two cards are. That's cosine similarity.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Part 2: SemanticMemory core, embedding, and fact extraction\n\nThe `SemanticMemory` class stores a list of `Fact` objects. It uses the OpenAI embeddings API to convert text into vectors and a chat completion call to extract facts from conversation messages.\n\nThe extraction prompt is the heart of the system. It tells the LLM to pull out clean declarative statements and ignore chitchat, questions, and hypotheticals.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('The `extract_facts` method sends conversation messages to the LLM with a carefully crafted prompt. The prompt tells the model to pull out only clear declarative statements and skip greetings, questions, and hypotheticals. Each extracted fact is a short, standalone sentence.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Part 3: Deduplication and contradiction detection\n\nImagine two people file the same customer complaint using different words. A good clerk spots they\'re about the same issue. That\'s deduplication. Now imagine a customer says "I love the product" in January and "I hate the product" in March. The clerk needs to flag the contradiction and keep the recent one.\n\nWe handle both in `_find_match`. For each new fact, we compute its embedding and compare against every stored fact. High similarity (above 0.85) means it\'s a duplicate. Moderate similarity (above 0.50) means the facts are on the same topic, so we ask the LLM if they contradict each other.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Part 4: Processing, retrieval, and chat\n\nNow we wire everything together. `process_conversation` extracts facts from messages and routes each one through add, merge, or conflict resolution. `retrieve` finds the most relevant facts for a query. `chat` ties it all together: it retrieves relevant knowledge, injects it into the system prompt, and calls the LLM.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('The `retrieve` method finds stored facts relevant to a query using cosine similarity. The `chat` method ties everything together: it retrieves relevant facts, injects them into the system prompt, and calls the LLM. `get_active_facts` returns all non-archived facts for inspection.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Example Run\n\nLet's walk through a realistic scenario. A user chats with an agent across three sessions. Session one: introductions. Session two: work details. Session three: a preference change. We'll see the knowledge base grow, deduplicate, and resolve a contradiction.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Session 1: Getting to know the user\n\nThe user shares basic information. The fact extractor pulls out declarative statements.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Session 2: More details (with duplicates)\n\nThe user mentions some of the same information again. The system should merge these duplicates and boost their confidence instead of creating new entries.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Session 3: A contradiction\n\nThe user has moved cities. This contradicts a stored fact. The system should archive the old fact ("lives in Berlin") and store the new one ("lives in Amsterdam").')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Retrieval: finding relevant facts\n\nWhen the user asks a question, the system retrieves facts relevant to that query. Let's test with a few different queries.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Chat with memory\n\nNow let's see the full loop. The agent uses retrieved facts to answer questions it was never directly asked in this session.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Persistence\n\nA semantic memory that disappears on restart isn't useful. We serialize the knowledge base to JSON so it survives between sessions.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Clean up the temporary file.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Tradeoffs\n\n### When Semantic Memory Works Well\n\n- **Long-lived agents.** If your agent talks to the same user across many sessions, semantic memory accumulates a rich profile. The agent feels personalized without the user repeating themselves.\n- **Cross-session knowledge.** Facts extracted in January are available in July. Buffer memory and sliding window memory lose this information when the session ends.\n- **Efficient context use.** Instead of re-sending hundreds of past messages, you inject 5-10 relevant facts. This saves tokens and keeps the prompt focused.\n\n### When It Breaks Down\n\n- **Extraction errors.** The LLM may extract opinions as facts, miss implicit information, or hallucinate facts that weren\'t stated. Every fact in the knowledge base needs to have actually been said.\n- **Subtle contradictions.** "I work remotely" and "I go to the office on Tuesdays" aren\'t strict contradictions, but the system may struggle with this nuance.\n- **Scaling.** Comparing every new fact against every stored fact is O(n). For thousands of facts, you\'ll need approximate nearest neighbor search (ANN) instead of brute-force cosine similarity.\n- **Stale facts.** Without a mechanism for temporal decay (reducing confidence over time), outdated facts linger. The user may have switched jobs six months ago, but the old job title persists.\n\n### Cost Considerations\n\nEach conversation turn costs one LLM call for extraction, one embedding call per extracted fact, and possibly one LLM call per contradiction check. For a turn that produces 3 facts, that\'s roughly 2-5 API calls. This is more expensive than buffer memory per turn, but cheaper per session when sessions are long.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Further Reading\n\n- [Tulving, "Episodic and Semantic Memory," *Organization of Memory*, 1972](https://psycnet.apa.org/record/1973-08477-005) - The original chapter where Endel Tulving defined semantic memory as a distinct system from episodic memory.\n- [Park et al., "Generative Agents: Interactive Simulacra of Human Behavior," UIST 2023 (arXiv:2304.03442)](https://arxiv.org/abs/2304.03442) - Demonstrates both episodic and semantic memory in simulated agents that form beliefs from experiences.\n- [OpenAI Embeddings Guide](https://platform.openai.com/docs/guides/embeddings) - Official documentation for the embeddings API used in this notebook.\n- [Mem0: Long-Term Memory for AI Agents](https://github.com/mem0ai/mem0?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques) - An open-source library that implements fact extraction, deduplication, and contradiction detection.\n- [Zep: Long-Term Memory for AI Assistants](https://github.com/getzep/zep?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques) - A memory server that extracts facts from conversations and provides semantic search over accumulated knowledge.\n\n---\n\n*Previous: [09 - Episodic Memory](../09_episodic_memory/) | Next: [11 - Procedural Memory](../11_procedural_memory/) ->*')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## 🧪 Try It Yourself\n\nThree small challenges to deepen your understanding. Each should take 10-30 minutes.\n\n### Challenge 1: Threshold sensitivity\nAdjust the duplicate detection threshold (default 0.85) to 0.75, 0.80, 0.90, and 0.95. For each setting, process the same 20-turn conversation and count how many facts are classified as new, duplicate, or contradiction. Plot a confusion matrix for each threshold.\n\n### Challenge 2: Fact accuracy audit\nAfter processing 20 turns, export all active facts with `get_active_facts()`. Manually label each fact as correct, outdated, or wrong. Compute the accuracy rate. Identify whether errors come from extraction, deduplication, or contradiction resolution.\n\n### Challenge 3: Categorized fact store\nGroup facts into named categories (e.g., 'personal', 'professional', 'preferences') by adding a `category` field to the `Fact` dataclass. Route facts to categories using the classification approach from 17 Memory Routing. Compare retrieval quality when searching within a category vs. searching all facts.\n")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--10-semantic-memory--semantic-memory)\n')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# SETUP (run separately): %pip install -q openai python-dotenv numpy\n\nimport os\nimport json\nimport uuid\nfrom dataclasses import dataclass, field, asdict\nfrom datetime import datetime, timezone\n\nimport numpy as np\nfrom openai import OpenAI\nfrom dotenv import load_dotenv\n\nload_dotenv()\n\nclient = OpenAI()  # reads OPENAI_API_KEY from environment\nassert os.getenv("OPENAI_API_KEY"), "Set OPENAI_API_KEY in your .env file"\n\nCHAT_MODEL = "gpt-4o-mini"\nEMBEDDING_MODEL = "text-embedding-3-small"\n\n@dataclass\nclass Fact:\n    """A single piece of knowledge extracted from conversation."""\n    content: str                          # e.g., "User prefers dark mode"\n    confidence: float = 0.8               # 0.0 to 1.0\n    fact_id: str = field(default_factory=lambda: str(uuid.uuid4()))\n    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())\n    last_confirmed: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())\n    mention_count: int = 1\n    embedding: list[float] = field(default_factory=list)\n    archived: bool = False                # True if superseded by a newer fact\n\n\ndef cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:\n    """Compute cosine similarity between two vectors."""\n    a = np.array(vec_a)\n    b = np.array(vec_b)\n    dot = np.dot(a, b)\n    norm = np.linalg.norm(a) * np.linalg.norm(b)\n    if norm == 0:\n        return 0.0\n    return float(dot / norm)\n\nclass SemanticMemory:\n    """Persistent knowledge base that extracts and stores facts from conversations."""\n\n    EXTRACTION_PROMPT = """You are a fact extractor. Read the conversation below and extract \\\ndeclarative facts about the user, their preferences, their work, or their world.\n\nRules:\n- Output one fact per line.\n- Each fact must be a short, standalone statement (under 20 words).\n- Write in third person: "User ..." or "User\'s ...".\n- Only extract facts that were clearly stated or strongly implied.\n- Skip greetings, questions, opinions phrased as questions, and hypotheticals.\n- If there are no extractable facts, output exactly: NONE\n\nConversation:\n{conversation}\n\nExtracted facts (one per line):"""\n\n    CONTRADICTION_PROMPT = """Do these two facts contradict each other? \\\nAnswer only YES or NO.\n\nFact A: {fact_a}\nFact B: {fact_b}\n\nAnswer:"""\n\n    def __init__(\n        self,\n        similarity_threshold: float = 0.85,\n        contradiction_threshold: float = 0.50,\n    ):\n        self.facts: list[Fact] = []\n        self.similarity_threshold = similarity_threshold\n        self.contradiction_threshold = contradiction_threshold\n\n    # -- Embedding -------------------------------------------------------\n    def _embed(self, text: str) -> list[float]:\n        """Get an embedding vector for a piece of text."""\n        response = client.embeddings.create(\n            model=EMBEDDING_MODEL,\n            input=text,\n        )\n        return response.data[0].embedding\n\n    def _embed_batch(self, texts: list[str]) -> list[list[float]]:\n        """Embed multiple texts in one API call."""\n        response = client.embeddings.create(\n            model=EMBEDDING_MODEL,\n            input=texts,\n        )\n        return [item.embedding for item in response.data]\n\n\n    # -- Fact extraction --------------------------------------------------\n    def extract_facts(self, messages: list[dict]) -> list[str]:\n        """Use an LLM call to extract declarative facts from messages."""\n        conversation_text = "\\n".join(\n            f"{m[\'role\'].upper()}: {m[\'content\']}" for m in messages\n        )\n        response = client.chat.completions.create(\n            model=CHAT_MODEL,\n            messages=[{\n                "role": "user",\n                "content": self.EXTRACTION_PROMPT.format(conversation=conversation_text),\n            }],\n            temperature=0.0,\n        )\n        raw = response.choices[0].message.content.strip()\n        if raw == "NONE":\n            return []\n        # Each line is one fact\n        facts = [line.strip().lstrip("- ") for line in raw.splitlines() if line.strip()]\n        return facts\n\ndef _find_match(self, new_text: str, new_embedding: list[float]):\n    """Check if a new fact duplicates or contradicts an existing one.\n\n    Returns:\n        ("duplicate", existing_fact) if the fact already exists.\n        ("contradiction", existing_fact) if it conflicts with a stored fact.\n        ("new", None) if it\'s a genuinely new fact.\n    """\n    best_sim = 0.0\n    best_fact = None\n\n    for fact in self.facts:\n        if fact.archived:\n            continue\n        sim = cosine_similarity(new_embedding, fact.embedding)\n        if sim > best_sim:\n            best_sim = sim\n            best_fact = fact\n\n    if best_sim >= self.similarity_threshold:\n        return ("duplicate", best_fact)\n\n    if best_sim >= self.contradiction_threshold and best_fact is not None:\n        # Same topic but different content. Ask the LLM if they contradict.\n        if self._check_contradiction(best_fact.content, new_text):\n            return ("contradiction", best_fact)\n\n    return ("new", None)\n\n\ndef _check_contradiction(self, fact_a: str, fact_b: str) -> bool:\n    """Ask the LLM whether two facts contradict each other."""\n    response = client.chat.completions.create(\n        model=CHAT_MODEL,\n        messages=[{\n            "role": "user",\n            "content": self.CONTRADICTION_PROMPT.format(fact_a=fact_a, fact_b=fact_b),\n        }],\n        temperature=0.0,\n        max_tokens=5,\n    )\n    answer = response.choices[0].message.content.strip().upper()\n    return answer.startswith("YES")\n\n\n# Attach methods to the class\nSemanticMemory._find_match = _find_match\nSemanticMemory._check_contradiction = _check_contradiction\n\ndef process_conversation(self, messages: list[dict]) -> dict:\n    """Extract facts from messages and update the knowledge base.\n\n    Returns a summary of what happened: counts of new, merged, and resolved facts.\n    """\n    extracted = self.extract_facts(messages)\n    if not extracted:\n        return {"extracted": 0, "new": 0, "merged": 0, "contradictions": 0}\n\n    embeddings = self._embed_batch(extracted)\n    stats = {"extracted": len(extracted), "new": 0, "merged": 0, "contradictions": 0}\n\n    for fact_text, embedding in zip(extracted, embeddings):\n        match_type, existing = self._find_match(fact_text, embedding)\n\n        if match_type == "new":\n            self.facts.append(Fact(content=fact_text, embedding=embedding))\n            stats["new"] += 1\n\n        elif match_type == "duplicate":\n            # Boost confidence and update timestamp\n            existing.mention_count += 1\n            existing.confidence = min(1.0, existing.confidence + 0.05)\n            existing.last_confirmed = datetime.now(timezone.utc).isoformat()\n            stats["merged"] += 1\n\n        elif match_type == "contradiction":\n            # Archive the old fact, add the new one\n            existing.archived = True\n            self.facts.append(Fact(\n                content=fact_text,\n                embedding=embedding,\n                confidence=0.9,  # recent statements get high confidence\n            ))\n            stats["contradictions"] += 1\n\n    return stats\n\n\n\ndef retrieve(self, query: str, top_k: int = 5) -> list[tuple[Fact, float]]:\n    """Find the most relevant facts for a query using cosine similarity."""\n    query_embedding = self._embed(query)\n    scored = []\n    for fact in self.facts:\n        if fact.archived:\n            continue\n        sim = cosine_similarity(query_embedding, fact.embedding)\n        scored.append((fact, sim))\n    scored.sort(key=lambda x: x[1], reverse=True)\n    return scored[:top_k]\n\n\ndef chat(self, user_input: str, conversation_history: list[dict] | None = None) -> str:\n    """Respond to the user with relevant facts injected into the prompt."""\n    relevant = self.retrieve(user_input, top_k=5)\n\n    # Build system prompt with known facts\n    system_parts = ["You are a helpful assistant."]\n    if relevant:\n        facts_text = "\\n".join(\n            f"- {fact.content} (confidence: {fact.confidence:.2f})"\n            for fact, _sim in relevant\n        )\n        system_parts.append(\n            f"\\nHere is what you know about the user:\\n{facts_text}\\n"\n            "Use these facts naturally. Don\'t list them unless asked."\n        )\n\n    messages = [{"role": "system", "content": "\\n".join(system_parts)}]\n    if conversation_history:\n        messages.extend(conversation_history)\n    messages.append({"role": "user", "content": user_input})\n\n    response = client.chat.completions.create(\n        model=CHAT_MODEL,\n        messages=messages,\n    )\n    return response.choices[0].message.content\n\n\ndef get_active_facts(self) -> list[Fact]:\n    """Return all non-archived facts."""\n    return [f for f in self.facts if not f.archived]\n\n\n# Attach methods to the class\nSemanticMemory.process_conversation = process_conversation\nSemanticMemory.retrieve = retrieve\nSemanticMemory.chat = chat\nSemanticMemory.get_active_facts = get_active_facts\n\nmemory = SemanticMemory()\n\nsession_1 = [\n    {"role": "user", "content": "Hi! I\'m Maya. I\'m a data scientist living in Berlin."},\n    {"role": "assistant", "content": "Nice to meet you, Maya! Berlin is a great city for tech. What are you working on?"},\n    {"role": "user", "content": "I\'m building a recommendation engine for an e-commerce company. We use Python and PyTorch mostly."},\n    {"role": "assistant", "content": "Sounds like a solid stack. How large is your dataset?"},\n    {"role": "user", "content": "About 50 million user interactions. We store everything in PostgreSQL and train on AWS."},\n]\n\nstats = memory.process_conversation(session_1)\nprint("Session 1 results:", stats)\nprint(f"\\nKnowledge base now has {len(memory.get_active_facts())} facts:")\nfor fact in memory.get_active_facts():\n    print(f"  [{fact.confidence:.2f}] {fact.content}")\n\nsession_2 = [\n    {"role": "user", "content": "I\'m back! So we talked about my recommendation project before."},\n    {"role": "assistant", "content": "Welcome back, Maya! Yes, the e-commerce recommendation engine. How\'s it going?"},\n    {"role": "user", "content": "Good! My team has 5 engineers. We deploy our models on AWS SageMaker."},\n    {"role": "assistant", "content": "SageMaker is a nice fit for that. Any challenges?"},\n    {"role": "user", "content": "Latency is our biggest issue. We need sub-100ms inference for real-time recommendations."},\n]\n\nstats = memory.process_conversation(session_2)\nprint("Session 2 results:", stats)\nprint(f"\\nKnowledge base now has {len(memory.get_active_facts())} active facts:")\nfor fact in memory.get_active_facts():\n    confirmed = "(boosted)" if fact.mention_count > 1 else ""\n    print(f"  [{fact.confidence:.2f}] {fact.content} {confirmed}")\n\nsession_3 = [\n    {"role": "user", "content": "Hey, big news! I moved to Amsterdam last month for a new role."},\n    {"role": "assistant", "content": "Congratulations on the move! What\'s the new role?"},\n    {"role": "user", "content": "I\'m now a senior ML engineer at a fintech startup. Still using Python though!"},\n]\n\nstats = memory.process_conversation(session_3)\nprint("Session 3 results:", stats)\nprint(f"\\nActive facts ({len(memory.get_active_facts())}):")\nfor fact in memory.get_active_facts():\n    print(f"  [{fact.confidence:.2f}] {fact.content}")\n\narchived = [f for f in memory.facts if f.archived]\nif archived:\n    print(f"\\nArchived facts ({len(archived)}):")\n    for fact in archived:\n        print(f"  [archived] {fact.content}")\n\ntest_queries = [\n    "What tech stack does Maya use?",\n    "Where does the user live?",\n    "Tell me about the user\'s team.",\n]\n\nfor query in test_queries:\n    print(f"Query: {query}")\n    results = memory.retrieve(query, top_k=3)\n    for fact, score in results:\n        print(f"  [{score:.3f}] {fact.content}")\n    print()\n\nquestions = [\n    "Can you recommend a good deep learning conference near me?",\n    "What programming language should I use for my next project?",\n    "What do you know about me?",\n]\n\nfor q in questions:\n    print(f"User: {q}")\n    reply = memory.chat(q)\n    print(f"Agent: {reply}\\n")\n\ndef save_memory(mem: SemanticMemory, path: str) -> None:\n    """Save the knowledge base to a JSON file."""\n    data = [asdict(f) for f in mem.facts]\n    with open(path, "w") as f:\n        json.dump(data, f, indent=2)\n    active = len(mem.get_active_facts())\n    print(f"Saved {active} active facts to {path}")\n\n\ndef load_memory(path: str, **kwargs) -> SemanticMemory:\n    """Load a knowledge base from a JSON file."""\n    with open(path) as f:\n        data = json.load(f)\n    mem = SemanticMemory(**kwargs)\n    for item in data:\n        mem.facts.append(Fact(**item))\n    active = len(mem.get_active_facts())\n    print(f"Loaded {active} active facts from {path}")\n    return mem\n\n\n# Round-trip test\nsave_memory(memory, "semantic_memory.json")\nloaded = load_memory("semantic_memory.json")\n\n# Verify the loaded memory works\nreply = loaded.chat("Where do I live now?")\nprint(f"\\nAgent (from loaded memory): {reply}")\n\nif os.path.exists("semantic_memory.json"):\n    os.remove("semantic_memory.json")', language="python", label="Recovered notebook code")
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
