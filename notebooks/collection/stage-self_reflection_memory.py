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
    # Self-Reflection Memory

    > **After each task attempt, the agent pauses to reflect on what happened, extracts durable insights, and stores them in a reflection memory. This way, the same mistakes never repeat and successful strategies carry forward across sessions.**

    Think of a chess player who reviews their games after each match. They don't only record the moves. They ask: "Why did I lose that piece? What pattern did I miss?" Over time, those post-game notes become more valuable than the game records themselves.

    Most memory techniques record *what* happened in a conversation: messages, entities, summaries. Self-Reflection Memory takes a different approach. It records *why* things went well or poorly, and *what to do differently next time*. This is the core idea behind **Reflexion** (Shinn et al., 2023), where agents use verbal self-reflection to convert sparse outcome signals into rich, reusable learning.

    The pattern works in four steps:
    1. The agent attempts a task and receives an outcome (success, partial, failure).
    2. A **reflection prompt** asks the agent to analyze root causes and extract lessons.
    3. The resulting **insight** goes into a dedicated reflection memory.
    4. Before future tasks, the agent retrieves relevant past reflections and injects them into the prompt.

    This creates a **reflect-then-store loop**. The loop lets an LLM-based agent (a language model used as a reasoning engine) improve across attempts *without any parameter updates*. Learning lives entirely in natural-language reflections.

    **By the end of this notebook you'll understand:**
    - How to implement a reflect-then-store loop with structured reflection prompts.
    - How to build a reflection memory store with persistence and retrieval.
    - How reflections improve agent performance across a multi-task benchmark (a standardized set of test tasks).
    - The tradeoffs of self-reflection memory vs. other memory techniques.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Key Concepts

    - **Reflection prompt:** A structured set of questions that guides the agent to evaluate its own performance. Example: *"What went well? What failed? What's the root cause? What should I do differently?"* This converts a pass/fail outcome into a rich learning signal.
    - **Insight extraction:** Distilling a full reflection into a concise, reusable principle. For example: *"Always check for edge cases in date parsing before attempting conversion."* Insights are the unit of storage.
    - **Reflection memory store:** A dedicated memory that holds past reflections. They're indexed by task type and outcome. Before each new task, the agent retrieves relevant reflections and injects them into its context.
    - **Reflect-then-store loop:** The core pattern: attempt, evaluate outcome, reflect, extract insight, store, retrieve on next attempt. Each cycle adds to the agent's accumulated wisdom.
    - **Outcome evaluation:** Comparing the agent's output against expected results to determine success, partial success, or failure. This signal triggers reflection.
    - **Reflexion framework:** From Shinn et al. (2023). Agents use verbal reinforcement learning (learning through written self-feedback). Natural-language reflections replace gradient updates as the learning mechanism.
    - **Meta-cognition:** The agent's ability to reason about its own reasoning. Self-reflection memory is an explicit implementation of metacognitive monitoring (watching your own thought process).
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Architecture

    <p align="center">
      <img src="../../images/diagrams/16_self_reflection_memory.svg" alt="diagram" width="720"/>
    </p>

    <details><summary>Mermaid source</summary>

    ```mermaid
    flowchart LR
        subgraph Attempt["Task Attempt"]
            A["Task prompt"] --> B["Retrieve relevant\npast reflections"]
            B --> C["Agent executes\ntask (with reflections\nin context)"]
            C --> D["Output"]
        end

        subgraph Evaluate["Outcome Evaluation"]
            D --> E["Compare output\nvs. expected"]
            E --> F{"Success?"}
        end

        subgraph Reflect["Reflection Loop"]
            F -->|"fail / partial"| G["Reflection prompt:\nWhat went wrong?\nRoot cause?\nLesson learned?"]
            F -->|"success"| H["Reflection prompt:\nWhat worked well?\nKey strategy?"]
            G --> I["Generate structured\nreflection"]
            H --> I
            I --> J["Extract concise\ninsight"]
        end

        subgraph Store["Reflection Memory"]
            J --> K[("Reflection Store\n─────────────\ntask_type\noutcome\ninsight\ntimestamp")]
            K --> B
        end

        style K fill:#4f46e5,color:#fff
        style C fill:#059669,color:#fff
        style I fill:#d97706,color:#fff
        style F fill:#dc2626,color:#fff
    ```

    </details>
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Setup

    Install the required packages. You only need to run this cell once.
    """)
    return


@app.cell
def _():
    # Install required packages (run once)
    # '%pip install -q anthropic python-dotenv matplotlib numpy' command supported automatically in marimo
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Load the Anthropic SDK and standard-library helpers.
    The API key comes from a `.env` file.
    """)
    return


@app.cell
def _():
    import os
    import json
    import time
    from datetime import datetime
    from dotenv import load_dotenv

    load_dotenv()  # reads API keys from .env

    import anthropic

    assert os.getenv("ANTHROPIC_API_KEY"), "Set ANTHROPIC_API_KEY in your .env file"

    print("\u2713 API key loaded")
    print(f"\u2713 anthropic version: {anthropic.__version__}")
    return anthropic, datetime, json, os


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Core Implementation

    Our Self-Reflection Memory system has three components:

    1. **`ReflectionStore`:** Stores structured reflections (task type, outcome, insight, full reflection text) with persistence and keyword-based retrieval.
    2. **`ReflectionGenerator`:** Uses Claude to analyze task outcomes and generate structured reflections with extracted insights.
    3. **`ReflectiveAgent`:** The main agent that attempts tasks, evaluates outcomes, triggers reflection on failures, and retrieves past reflections to improve future attempts.
    """)
    return


@app.cell
def _(datetime):
    class ReflectionStore:
        """Stores structured reflections with retrieval by task type and keyword matching."""

        def __init__(self):
            self.reflections: list[dict] = []

        def add(self, reflection: dict) -> None:
            """Add a structured reflection to the store.

            Expected keys: task_type, outcome, insight, reflection_text, task_description
            """
            reflection["timestamp"] = datetime.now().isoformat()
            reflection["id"] = len(self.reflections)
            self.reflections.append(reflection)

        def retrieve(self, task_type: str | None = None, limit: int = 5) -> list[dict]:
            """Retrieve reflections, optionally filtered by task type."""
            matches = self.reflections
            if task_type:
                matches = [r for r in matches if r.get("task_type") == task_type]
            # Most recent first
            return sorted(matches, key=lambda r: r["timestamp"], reverse=True)[:limit]

        def retrieve_by_keywords(self, text: str, limit: int = 5) -> list[dict]:
            """Retrieve reflections whose insight or task_description overlaps with the text."""
            text_words = set(text.lower().split())
            scored = []
            for r in self.reflections:
                ref_text = f"{r.get('insight', '')} {r.get('task_description', '')}".lower()
                ref_words = set(ref_text.split())
                overlap = len(text_words & ref_words)
                if overlap > 0:
                    scored.append((overlap, r))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [r for _, r in scored[:limit]]

        def get_failure_insights(self, task_type: str | None = None) -> list[str]:
            """Get all insights from failed attempts, optionally filtered by task type."""
            reflections = self.retrieve(task_type=task_type, limit=100)
            return [
                r["insight"] for r in reflections
                if r.get("outcome") == "failure" and r.get("insight")
            ]

        def format_for_prompt(self, reflections: list[dict]) -> str:
            """Format reflections for injection into agent context."""
            if not reflections:
                return "No relevant past reflections."
            lines = []
            for r in reflections:
                outcome = r.get("outcome", "unknown")
                icon = "\u2713" if outcome == "success" else "\u2717"
                lines.append(
                    f"  {icon} [{outcome.upper()}] {r.get('task_description', 'N/A')}\n"
                    f"    Insight: {r.get('insight', 'N/A')}"
                )
            return "\n".join(lines)

    return (ReflectionStore,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `ReflectionStore` also needs persistence and utility methods.
    Below we add `save` and `load` for writing reflections to JSON files,
    plus `__len__` and `__repr__` for convenience.
    """)
    return


@app.cell
def _(ReflectionStore, json):
    def save(self, path: str) -> None:
        """Persist reflections to JSON."""
        with open(path, "w") as f:
            json.dump(self.reflections, f, indent=2)

    ReflectionStore.save = save

    def __len__(self) -> int:
        return len(self.reflections)

    ReflectionStore.__len__ = __len__

    def __repr__(self) -> str:
        n_fail = sum(1 for r in self.reflections if r.get("outcome") == "failure")
        n_ok = sum(1 for r in self.reflections if r.get("outcome") == "success")
        return f"ReflectionStore({len(self)} reflections: {n_ok} success, {n_fail} failure)"


    print("\u2713 ReflectionStore class defined")
    ReflectionStore.__repr__ = __repr__

    print("\u2713 ReflectionStore class defined")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Next we define the tool schema for reflection generation.
    A tool schema is a structured description of what fields the model should return.
    This one asks Claude for four outputs: what happened, the root cause, a concise insight, and a strategy for next time.
    """)
    return


@app.cell
def _():
    REFLECTION_TOOL = {
        "name": "store_reflection",
        "description": (
            "Store a structured reflection about a task attempt. "
            "Analyze what happened, identify root causes, and extract a concise insight."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "what_happened": {
                    "type": "string",
                    "description": "Brief summary of what the agent did and the outcome.",
                },
                "root_cause": {
                    "type": "string",
                    "description": "Why did the attempt succeed or fail? Identify the key factor.",
                },
                "insight": {
                    "type": "string",
                    "description": (
                        "A concise, reusable lesson learned (1-2 sentences). "
                        "Should be actionable and applicable to similar future tasks."
                    ),
                },
                "strategy_for_next_time": {
                    "type": "string",
                    "description": "Concrete strategy to apply when facing a similar task.",
                },
            },
            "required": ["what_happened", "root_cause", "insight", "strategy_for_next_time"],
        },
    }
    return (REFLECTION_TOOL,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `ReflectionGenerator` sends task outcomes to Claude along with the tool schema above.
    Claude returns a structured reflection.
    If the tool call fails, the generator returns a safe fallback with placeholder values.
    """)
    return


@app.cell
def _(anthropic):
    class ReflectionGenerator:
        """Uses Claude to generate structured reflections from task outcomes."""

        def __init__(self, model: str = "claude-sonnet-4-20250514"):
            self.client = anthropic.Anthropic()
            self.model = model

    return (ReflectionGenerator,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `reflect` method sends a task outcome to Claude and asks for a structured analysis.
    It uses Claude's tool-use feature to get back a clean JSON object with four fields:
    what happened, root cause, insight, and strategy for next time.
    """)
    return


@app.cell
def _(REFLECTION_TOOL, ReflectionGenerator):
    def reflect(
        self,
        task_description: str,
        agent_output: str,
        expected_output: str,
        outcome: str,
    ) -> dict:
        """Generate a structured reflection on a task attempt.

        Args:
            task_description: What the task was.
            agent_output: What the agent produced.
            expected_output: What was expected.
            outcome: 'success', 'failure', or 'partial'.

        Returns:
            Dict with keys: what_happened, root_cause, insight, strategy_for_next_time
        """
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=(
                "You are a reflection system that analyzes task outcomes. "
                "Given a task, the agent's output, and the expected output, "
                "generate a thoughtful reflection. Focus on extractable lessons "
                "that would help in future similar tasks. Be specific and actionable."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Task: {task_description}\n\n"
                        f"Agent output: {agent_output}\n\n"
                        f"Expected output: {expected_output}\n\n"
                        f"Outcome: {outcome}\n\n"
                        "Analyze this attempt and extract a lesson learned."
                    ),
                }
            ],
            tools=[REFLECTION_TOOL],
            tool_choice={"type": "tool", "name": "store_reflection"},
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "store_reflection":
                return block.input
        return {
            "what_happened": "Reflection generation failed.",
            "root_cause": "Unknown",
            "insight": "No insight extracted.",
            "strategy_for_next_time": "Retry with more context.",
        }

    ReflectionGenerator.reflect = reflect

    print("\u2713 ReflectionGenerator class defined (uses Claude tool-use)")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    We need a way to check whether the agent produced the right answer.
    This evaluator uses keyword matching.
    It looks for expected keywords in the agent's output.
    If 80% or more keywords appear, the outcome is "success". Between 30-80% is "partial". Below that is "failure".
    """)
    return


@app.function
# ── Task Evaluator ──

def evaluate_output(agent_output: str, expected: str, check_keywords: list[str]) -> str:
    """Simple keyword-based evaluation: checks if required keywords appear in output.

    Returns 'success' if ALL keywords found, 'partial' if some, 'failure' if none.
    """
    output_lower = agent_output.lower()
    found = [kw for kw in check_keywords if kw.lower() in output_lower]
    ratio = len(found) / len(check_keywords) if check_keywords else 0
    if ratio >= 0.8:
        return "success"
    elif ratio >= 0.3:
        return "partial"
    return "failure"


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Here is our benchmark: six tasks that test different skills.
    Each task has a prompt, an expected answer, and keywords to check.
    The tasks are designed to be tricky.
    A naive attempt often fails on specific pitfalls, but a reflection-informed attempt can learn from past mistakes.
    """)
    return


@app.cell
def _():
    # ── Multi-Task Benchmark ──
    # Each task has: description, prompt, expected answer summary, and check keywords.
    # Tasks are designed so that naive attempts often fail on specific pitfalls,
    # but reflection-informed attempts can learn from past mistakes.

    BENCHMARK_TASKS = [
        {
            "task_type": "date_parsing",
            "description": "Parse ambiguous date formats",
            "prompt": (
                "Parse the following date string and return it in ISO 8601 format (YYYY-MM-DD). "
                "The date is: '03/04/2025'. Assume the format is DD/MM/YYYY (European convention). "
                "Return ONLY the ISO date, nothing else."
            ),
            "expected": "2025-04-03",
            "check_keywords": ["2025-04-03"],
        },
        {
            "task_type": "list_processing",
            "description": "Extract and deduplicate items from text",
            "prompt": (
                "Extract all unique fruit names from this text and return them as a comma-separated "
                "list in alphabetical order:\n"
                "'I bought apples, then more apples, some bananas, three oranges, "
                "a kiwi, more bananas, and finally a mango.'\n"
                "Return ONLY the comma-separated list, nothing else."
            ),
            "expected": "apples, bananas, kiwi, mango, oranges",
            "check_keywords": ["apples", "bananas", "kiwi", "mango", "oranges"],
        },
        {
            "task_type": "code_generation",
            "description": "Write a function with specific edge case handling",
            "prompt": (
                "Write a Python function called `safe_divide(a, b)` that returns a/b. "
                "It must handle: division by zero (return 0), non-numeric inputs (return None), "
                "and both int and float inputs. Include a docstring. "
                "Return ONLY the function code, no explanation."
            ),
            "expected": "def safe_divide with zero check and type check",
            "check_keywords": ["def safe_divide", "zero", "none", "docstring"],
        },
    ]

    print(f"Benchmark batch 1: {len(BENCHMARK_TASKS)} tasks")
    return (BENCHMARK_TASKS,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Here are the remaining three benchmark tasks.
    They test text transformation, data extraction, and reasoning.
    We combine both batches into a single `BENCHMARK_TASKS` list.
    """)
    return


@app.cell
def _(BENCHMARK_TASKS):
    BENCHMARK_TASKS_2 = [
        {
            "task_type": "reasoning",
            "description": "Multi-step logical reasoning",
            "prompt": (
                "A farmer has 3 fields. Field A produces 120 bushels/acre across 5 acres. "
                "Field B produces 95 bushels/acre across 8 acres. "
                "Field C produces 110 bushels/acre across 6 acres. "
                "Which field produces the MOST total bushels? "
                "Show your calculation for each field, then state the answer. "
                "Format: 'Field X: Y bushels' for each, then 'Answer: Field Z'."
            ),
            "expected": "Field B: 760 bushels. Answer: Field B",
            "check_keywords": ["760", "field b"],
        },
        {
            "task_type": "text_transformation",
            "description": "Apply a specific text transformation rule",
            "prompt": (
                "Convert the following sentence to title case, but keep articles "
                "(a, an, the), conjunctions (and, but, or), and prepositions "
                "(in, on, at, to, for, of, with) in lowercase UNLESS they start the sentence. "
                "Sentence: 'the quick brown fox jumps over the lazy dog in the park'\n"
                "Return ONLY the transformed sentence."
            ),
            "expected": "The Quick Brown Fox Jumps over the Lazy Dog in the Park",
            "check_keywords": ["Quick Brown Fox", "over the", "in the"],
        },
        {
            "task_type": "data_extraction",
            "description": "Extract structured data from unstructured text",
            "prompt": (
                "Extract all email addresses from this text and return them one per line, sorted alphabetically:\n"
                "'Contact us at support@acme.com or sales@acme.com. "
                "For technical issues, email dev@acme.com. "
                "Our CEO can be reached at alice@acme.com. "
                "Spam this address: noreply@acme.com'\n"
                "Return ONLY the email addresses, one per line, sorted alphabetically."
            ),
            "expected": "alice@acme.com\ndev@acme.com\nnoreply@acme.com\nsales@acme.com\nsupport@acme.com",
            "check_keywords": ["alice@acme.com", "dev@acme.com", "noreply@acme.com", "sales@acme.com", "support@acme.com"],
        },
    ]

    BENCHMARK_TASKS.extend(BENCHMARK_TASKS_2)

    print(f"\u2713 Benchmark defined: {len(BENCHMARK_TASKS)} tasks")
    for t in BENCHMARK_TASKS:
        print(f"  \u2022 [{t['task_type']}] {t['description']}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `ReflectiveAgent` ties everything together into the reflect-then-store loop.

    Before each task, it retrieves relevant past reflections and injects them into the prompt.
    After each task, it evaluates the outcome.
    If the result isn't a clean success, it generates a new reflection and stores it.
    Over multiple runs, the agent accumulates insights that help it avoid repeating the same mistakes.
    """)
    return


@app.cell
def _(ReflectionGenerator, ReflectionStore, anthropic):
    class ReflectiveAgent:
        """Agent that attempts tasks, reflects on outcomes, and improves via stored insights.

        The reflect-then-store loop:
        1. Retrieve relevant past reflections for the current task.
        2. Inject reflections into the prompt as context.
        3. Attempt the task.
        4. Evaluate the outcome.
        5. If not a clean success, generate a reflection and store it.
        6. Return the result and metadata.
        """

        def __init__(
            self,
            model: str = "claude-sonnet-4-20250514",
            reflection_model: str = "claude-sonnet-4-20250514",
            max_tokens: int = 1024,
            reflection_store: ReflectionStore | None = None,
        ):
            self.client = anthropic.Anthropic()
            self.model = model
            self.max_tokens = max_tokens
            self.store = reflection_store or ReflectionStore()
            self.generator = ReflectionGenerator(model=reflection_model)
            self.attempt_log: list[dict] = []

    return (ReflectiveAgent,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `attempt_task` method is the heart of the reflect-then-store loop.
    It retrieves past reflections, injects them into the prompt, executes the task,
    evaluates the outcome, and generates a new reflection if the result wasn't a clean success.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Before attempting a task, the agent gathers past reflections.
    This helper retrieves reflections by task type and keyword overlap,
    then formats them into a context string for injection into the prompt.
    """)
    return


@app.cell
def _(ReflectiveAgent):
    def _build_reflection_context(self, task, use_reflections):
        """Retrieve relevant reflections and build the context string."""
        reflections_used = []
        reflection_context = ""
        if use_reflections:
            by_type = self.store.retrieve(task_type=task["task_type"], limit=3)
            by_keywords = self.store.retrieve_by_keywords(task["prompt"], limit=2)
            seen_ids = set()
            merged = []
            for r in by_type + by_keywords:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    merged.append(r)
            reflections_used = merged[:5]
            if reflections_used:
                formatted = self.store.format_for_prompt(reflections_used)
                reflection_context = (
                    "\n\nYou have these insights from past attempts at similar tasks. "
                    "Apply these lessons to avoid repeating mistakes:\n\n"
                    f"{formatted}\n"
                )
        return reflections_used, reflection_context

    ReflectiveAgent._build_reflection_context = _build_reflection_context
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `attempt_task` method runs the full reflect-then-store loop.
    It builds the prompt with reflection context, executes the task, evaluates the result,
    and stores a new reflection if the outcome wasn't a clean success.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    This helper handles task execution, evaluation, and reflection generation.
    It sends the prompt to Claude, checks the output against expected keywords,
    and generates a structured reflection if the outcome isn't a clean success.
    """)
    return


@app.cell
def _(ReflectiveAgent, json):
    def _execute_and_reflect(self, task, reflections_used, reflection_context):
        """Execute the task, evaluate the outcome, and reflect if needed."""
        system = (
            "You are a precise task executor. Follow instructions exactly. "
            "Pay close attention to output format requirements."
            f"{reflection_context}"
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": task["prompt"]}],
        )
        output = response.content[0].text

        outcome = evaluate_output(output, task["expected"], task["check_keywords"])

        reflection = None
        if outcome != "success":
            reflection = self.generator.reflect(
                task_description=task["description"],
                agent_output=output,
                expected_output=task["expected"],
                outcome=outcome,
            )
            self.store.add({
                "task_type": task["task_type"],
                "task_description": task["description"],
                "outcome": outcome,
                "insight": reflection.get("insight", ""),
                "reflection_text": json.dumps(reflection),
            })

        return output, outcome, reflection

    ReflectiveAgent._execute_and_reflect = _execute_and_reflect
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The `attempt_task` method ties the pieces together.
    It retrieves past reflections, executes the task with context, and logs the result.
    """)
    return


@app.cell
def _(ReflectiveAgent):
    def attempt_task(self, task, use_reflections=True):
        """Attempt a task, optionally using past reflections for guidance.

        Args:
            task: Dict with keys: task_type, description, prompt, expected, check_keywords
            use_reflections: Whether to retrieve and inject past reflections.

        Returns:
            Dict with: output, outcome, reflection (if generated), reflections_used
        """
        reflections_used, reflection_context = self._build_reflection_context(
            task, use_reflections,
        )

        output, outcome, reflection = self._execute_and_reflect(
            task, reflections_used, reflection_context,
        )

        result = {
            "task_type": task["task_type"],
            "description": task["description"],
            "output": output,
            "expected": task["expected"],
            "outcome": outcome,
            "reflection": reflection,
            "reflections_used": len(reflections_used),
        }
        self.attempt_log.append(result)
        return result

    ReflectiveAgent.attempt_task = attempt_task
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The remaining methods handle benchmarking and persistence.
    `run_benchmark` runs a full suite of tasks and prints a summary.
    `save_memory` and `from_saved` handle writing and loading reflections across sessions.
    """)
    return


@app.cell
def _(ReflectionStore, ReflectiveAgent):
    def run_benchmark(self, tasks: list[dict], use_reflections: bool=True, label: str='Run') -> dict:
        """Run a full benchmark suite and return aggregate results."""
        results = []
        for i, task in enumerate(tasks):
            result = self.attempt_task(task, use_reflections=use_reflections)
            status = '✓' if result['outcome'] == 'success' else '~' if result['outcome'] == 'partial' else '✗'
            ref_info = f" (used {result['reflections_used']} reflections)" if use_reflections else ''
            print(f"  {status} [{result['task_type']}] {result['description']}{ref_info}")
            results.append(result)
        n_success = sum((1 for r in results if r['outcome'] == 'success'))
        n_partial = sum((1 for r in results if r['outcome'] == 'partial'))
        n_failure = sum((1 for r in results if r['outcome'] == 'failure'))
        summary = {'label': label, 'total': len(results), 'success': n_success, 'partial': n_partial, 'failure': n_failure, 'score': n_success / len(results) if results else 0, 'results': results}
        print(f'\n  Score: {n_success}/{len(results)} ({n_success / len(results) * 100:.0f}%) success | {n_partial} partial | {n_failure} failure')
        return summary
    ReflectiveAgent.run_benchmark = run_benchmark

    def save_memory(self, path: str) -> None:
        """Persist reflection store to disk."""
        self.store.save(path)
    ReflectiveAgent.save_memory = save_memory

    @classmethod
    def from_saved(cls, path: str, **kwargs) -> 'ReflectiveAgent':
        """Create agent pre-loaded with saved reflections."""
        store = ReflectionStore.load(path)
        return cls(reflection_store=store, **kwargs)
    ReflectiveAgent.from_saved = from_saved

    def __repr___1(self) -> str:
        return f'ReflectiveAgent(reflections={len(self.store)}, attempts={len(self.attempt_log)})'
    ReflectiveAgent.__repr__ = __repr___1
    print('✓ ReflectiveAgent class defined')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Usage Example: The Reflect-Then-Store Loop

    Let's walk through the reflect-then-store loop with a single task. You'll see exactly how reflection works. The agent will:
    1. Attempt a task.
    2. Evaluate the outcome.
    3. If it fails, generate a reflection with root cause analysis and an actionable insight.
    4. Store the insight for future use.
    """)
    return


@app.cell
def _(ReflectiveAgent):
    # Create a fresh agent
    agent = ReflectiveAgent()

    # A task that's easy to get subtly wrong
    demo_task = {
        "task_type": "date_parsing",
        "description": "Parse ambiguous date formats",
        "prompt": (
            "Parse the following date string and return it in ISO 8601 format (YYYY-MM-DD). "
            "The date is: '03/04/2025'. Assume the format is DD/MM/YYYY (European convention). "
            "Return ONLY the ISO date, nothing else."
        ),
        "expected": "2025-04-03",
        "check_keywords": ["2025-04-03"],
    }

    # First attempt -- no reflections available yet
    print("=== Attempt 1 (no prior reflections) ===\n")
    result1 = agent.attempt_task(demo_task, use_reflections=True)
    print(f"  Output:   {result1['output'].strip()}")
    print(f"  Expected: {result1['expected']}")
    print(f"  Outcome:  {result1['outcome']}")

    if result1["reflection"]:
        print(f"\n  \U0001f4ad Reflection generated:")
        print(f"     What happened:  {result1['reflection']['what_happened']}")
        print(f"     Root cause:     {result1['reflection']['root_cause']}")
        print(f"     Insight:        {result1['reflection']['insight']}")
        print(f"     Next time:      {result1['reflection']['strategy_for_next_time']}")

    print(f"\n  Reflections in store: {len(agent.store)}")

    # Second attempt -- now has reflection from first attempt
    print("\n=== Attempt 2 (with reflection from attempt 1) ===\n")
    result2 = agent.attempt_task(demo_task, use_reflections=True)
    print(f"  Output:   {result2['output'].strip()}")
    print(f"  Expected: {result2['expected']}")
    print(f"  Outcome:  {result2['outcome']}")
    print(f"  Reflections used: {result2['reflections_used']}")

    print(f"\n\u2713 Reflect-then-store loop demonstrated")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Multi-Task Benchmark: Does Reflection Help?

    Now let's run a controlled experiment. We run the same 6-task benchmark **three times**:

    1. **Run 1 (Baseline):** No reflections available. The agent attempts all tasks cold.
    2. **Run 2 (With Reflections):** The agent has reflections from Run 1's failures. Past insights are injected into the prompt.
    3. **Run 3 (Accumulated):** The agent has reflections from both previous runs, further refining its approach.

    If self-reflection memory works, we should see scores **increase across runs** as the agent learns from its mistakes.
    """)
    return


@app.cell
def _(BENCHMARK_TASKS, ReflectiveAgent):
    # Fresh agent for the experiment
    agent_1 = ReflectiveAgent()
    print('=' * 60)
    # ── Run 1: Baseline (no reflections yet) ──
    print('RUN 1 - Baseline (no reflections available)')
    print('=' * 60)
    run1 = agent_1.run_benchmark(BENCHMARK_TASKS, use_reflections=True, label='Run 1 (Baseline)')
    print(f'\nReflections after Run 1: {len(agent_1.store)}')
    print()
    print('=' * 60)
    print('RUN 2 - With reflections from Run 1')
    print('=' * 60)
    # ── Run 2: With reflections from Run 1 ──
    run2 = agent_1.run_benchmark(BENCHMARK_TASKS, use_reflections=True, label='Run 2 (Reflective)')
    print(f'\nReflections after Run 2: {len(agent_1.store)}')
    print()
    print('=' * 60)
    print('RUN 3 - With accumulated reflections from Runs 1 & 2')
    print('=' * 60)
    run3 = agent_1.run_benchmark(BENCHMARK_TASKS, use_reflections=True, label='Run 3 (Accumulated)')
    # ── Run 3: With accumulated reflections ──
    print(f'\nReflections after Run 3: {len(agent_1.store)}')
    return agent_1, run1, run2, run3


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    For a fair comparison, we run the same benchmark with reflections disabled.
    This control group shows whether the stored reflections actually helped the agent perform better.
    """)
    return


@app.cell
def _(BENCHMARK_TASKS, ReflectiveAgent):
    # ── Control: Same benchmark WITHOUT reflection ──
    print("=" * 60)
    print("CONTROL - Same agent, reflections DISABLED")
    print("=" * 60)

    # Create a new agent with the same stored reflections but disable retrieval
    control_agent = ReflectiveAgent()
    control = control_agent.run_benchmark(
        BENCHMARK_TASKS, use_reflections=False, label="Control (No Reflection)"
    )
    return (control,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Let's visualize the results.
    The left panel shows overall scores across the four runs.
    The right panel is a per-task heatmap: green means success, yellow means partial, red means failure.
    Look for tasks that flip from red to green across runs.
    """)
    return


@app.cell
def _(BENCHMARK_TASKS, control, run1, run2, run3):
    import matplotlib.pyplot as plt
    import numpy as np
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    runs = [run1, run2, run3, control]
    labels = [r['label'] for r in runs]
    # ── Panel 1: Score progression across runs ──
    scores = [r['success'] for r in runs]
    colors = ['#94a3b8', '#4f46e5', '#059669', '#ef4444']
    bars = axes[0].bar(labels, scores, color=colors, width=0.55, alpha=0.9)
    axes[0].set_ylabel('Tasks Passed', fontsize=12)
    axes[0].set_ylim(0, len(BENCHMARK_TASKS) + 1)
    axes[0].set_title('Score Progression Across Benchmark Runs', fontsize=13, fontweight='bold')
    axes[0].axhline(y=len(BENCHMARK_TASKS), color='gray', linestyle='--', alpha=0.3)
    for bar, score in zip(bars, scores):
        axes[0].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.2, f'{score}/{len(BENCHMARK_TASKS)}', ha='center', fontweight='bold', fontsize=12)
    axes[0].tick_params(axis='x', labelsize=9)
    task_labels = [t['task_type'] for t in BENCHMARK_TASKS]
    run_labels = ['Run 1', 'Run 2', 'Run 3']
    heatmap_data = []
    for run in [run1, run2, run3]:
        row = []
        for _result in run['results']:
            val = 1.0 if _result['outcome'] == 'success' else 0.5 if _result['outcome'] == 'partial' else 0.0
    # ── Panel 2: Per-task improvement heatmap ──
            row.append(val)
        heatmap_data.append(row)
    heatmap_data = np.array(heatmap_data)
    im = axes[1].imshow(heatmap_data, cmap='RdYlGn', aspect='auto', vmin=0, vmax=1)
    axes[1].set_xticks(range(len(task_labels)))
    axes[1].set_xticklabels(task_labels, rotation=45, ha='right', fontsize=9)
    axes[1].set_yticks(range(len(run_labels)))
    axes[1].set_yticklabels(run_labels, fontsize=10)
    axes[1].set_title('Per-Task Outcomes Across Runs', fontsize=13, fontweight='bold')
    for i in range(len(run_labels)):
        for j in range(len(task_labels)):
            val = heatmap_data[i, j]
            text = '✓' if val == 1.0 else '~' if val == 0.5 else '✗'
            axes[1].text(j, i, text, ha='center', va='center', fontsize=14, color='white' if val < 0.5 else 'black', fontweight='bold')
    plt.tight_layout()
    plt.savefig('reflection_benchmark.png', dpi=150, bbox_inches='tight')
    plt.show()
    print(f"\nRun 1 (Baseline):     {run1['success']}/{run1['total']}")
    print(f"Run 2 (Reflective):   {run2['success']}/{run2['total']}")
    # Add text annotations
    print(f"Run 3 (Accumulated):  {run3['success']}/{run3['total']}")
    print(f"Control (No Reflect): {control['success']}/{control['total']}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Inspecting the Reflection Store

    Let's examine what the agent learned. Below you'll see the actual reflections it generated and stored after failed attempts.
    """)
    return


@app.cell
def _(agent_1, json):
    print(f'=== Reflection Store: {len(agent_1.store)} reflections ===\n')
    for r in agent_1.store.reflections:
        outcome = r.get('outcome', 'unknown')
        icon = '✓' if outcome == 'success' else '✗'
        print(f"{icon} [{outcome.upper()}] {r['task_description']}")
        print(f"  Task type: {r['task_type']}")
        print(f"  Insight:   {r['insight']}")
        reflection_data = json.loads(r['reflection_text'])
        print(f"  Strategy:  {reflection_data.get('strategy_for_next_time', 'N/A')}")
        print()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Cross-Session Persistence

    Reflections persist to JSON (a standard text-based data format). A new agent instance can load accumulated wisdom from past sessions and benefit from it immediately. There's no need to re-learn from the same mistakes.
    """)
    return


@app.cell
def _(BENCHMARK_TASKS, ReflectiveAgent, agent_1):
    REFLECTIONS_FILE = 'reflections.json'
    agent_1.save_memory(REFLECTIONS_FILE)
    print(f'✓ Saved {len(agent_1.store)} reflections to {REFLECTIONS_FILE}')
    print('\n--- NEW SESSION ---\n')
    agent2 = ReflectiveAgent.from_saved(REFLECTIONS_FILE)
    print(f'Loaded: {agent2.store}')
    print(f"\nFailure insights for 'date_parsing':")
    for insight in agent2.store.get_failure_insights('date_parsing'):
        print(f'  • {insight}')
    print(f"\nFailure insights for 'code_generation':")
    for insight in agent2.store.get_failure_insights('code_generation'):
        print(f'  • {insight}')
    print('\n=== New Session Task Attempt ===\n')
    _result = agent2.attempt_task(BENCHMARK_TASKS[0], use_reflections=True)
    print(f"  Task:     {_result['description']}")
    print(f"  Output:   {_result['output'].strip()}")
    print(f"  Outcome:  {_result['outcome']}")
    print(f"  Reflections used: {_result['reflections_used']}")
    print(f'\n✓ Cross-session persistence works -- insights preserved!')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Discussion & Tradeoffs

    ### Strengths
    - **Learning without fine-tuning:** The agent improves across attempts using only natural-language reflections. No gradient updates, no model changes. This works with any LLM API.
    - **Explicit and inspectable:** Every reflection is human-readable. You can audit exactly what the agent learned. This is unlike opaque parameter updates or embedding-based memory.
    - **Composable:** Self-reflection memory can layer on top of any other memory technique. Combine it with entity memory, knowledge graphs, or vector stores for a multi-layer architecture.
    - **Cost-efficient improvement:** One reflection API call per failure can prevent the same failure across all future sessions. The return-on-investment for reflection calls is very high.

    ### Weaknesses
    - **Reflection quality depends on the model.** If the LLM generates shallow or incorrect reflections, the stored insights may be misleading. Garbage in, garbage out.
    - **Extra API cost per failure:** Each failed task triggers an additional LLM call for reflection generation. In high-failure-rate scenarios, this adds up.
    - **Keyword retrieval is brittle:** Our keyword-matching retrieval can miss relevant reflections or surface irrelevant ones. Production systems should use embedding-based similarity (comparing meaning through vector math).
    - **No contradiction resolution:** If the agent generates conflicting insights across runs, both are stored. A production system needs conflict detection and resolution.
    - **Evaluation bottleneck:** The system relies on being able to evaluate outcomes. Tasks without clear success criteria can't trigger meaningful reflection.

    ### Self-Reflection Memory vs. Other Approaches

    | Aspect | Self-Reflection Memory | Summary Memory | Entity Memory |
    |--------|----------------------|----------------|---------------|
    | Stores | *Why* things happened | *What* happened | Facts *about* entities |
    | Learning | Improves across attempts | Compresses history | Tracks state |
    | Trigger | Task outcome (success/fail) | Every N turns | Entity mention |
    | Retrieval | By task type + keywords | Always injected | By entity name |
    | Meta-cognitive | Yes (reasons about reasoning) | No | No |
    | Cost | Extra call on failure only | Extra call every N turns | Extra call every turn |

    ### When to Use Self-Reflection Memory

    | Scenario | Recommendation |
    |----------|---------------|
    | Agents performing repeatable tasks with clear success criteria | **Excellent** (the core use case) |
    | Long-running agents that should demonstrably improve | **Excellent** |
    | Debugging agent failures across sessions | **Great** (reflections explain *why* things failed) |
    | A Q&A chatbot | **Overkill** (summary or sliding window is sufficient) |
    | Tasks with no evaluatable outcome | **Poor fit** (reflection needs outcome signals) |
    | Cost-sensitive with low failure rates | **Good** (reflection only fires on failure) |
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Further Reading

    - [Shinn et al., "Reflexion: Language Agents with Verbal Reinforcement Learning" (2023)](https://arxiv.org/abs/2303.11366). The foundational paper for self-reflection in LLM agents.
    - [Madaan et al., "Self-Refine: Iterative Refinement with Self-Feedback" (2023)](https://arxiv.org/abs/2303.17651). A related approach that uses self-feedback for iterative improvement.
    - [Yao et al., "ReAct: Synergizing Reasoning and Acting" (2023)](https://arxiv.org/abs/2210.03629). Reasoning traces that complement reflection.
    - [Anthropic Tool Use (Function Calling)](https://docs.anthropic.com/en/docs/build-with-claude/tool-use?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques). The API used for structured reflection extraction.
    - [Flavell, "Metacognition and Cognitive Monitoring" (1979)](https://doi.org/10.1037/0003-066X.34.10.906). Foundational cognitive science work on metacognition.
    - [Anthropic: Building Conversational AI](https://docs.anthropic.com/en/docs/build-with-claude/conversational-ai?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques). Multi-turn conversation patterns.

    ---

    *← Previous: [15: Memory Compaction](../15_memory_compaction/) · Next: [17: Memory Routing](../17_memory_routing/) →*
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Remove the temporary files created during this demo.
    """)
    return


@app.cell
def _(os):
    # Clean up temp files
    for f in ['reflections.json', 'reflection_benchmark.png']:
        if os.path.exists(f):
            os.remove(f)
            print(f'Removed {f}')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 🧪 Try It Yourself

    Three small challenges to deepen your understanding. Each should take 10-30 minutes.

    ### Challenge 1: Reflection categories
    Extend `ReflectionStore` to tag each reflection with a category: 'strategy', 'mistake', or 'preference'. Modify `retrieve()` to accept an optional category filter. Test by running `run_benchmark()` and querying only mistake-related reflections on the next attempt.

    ### Challenge 2: Learning curve measurement
    Run `run_benchmark()` for 5 consecutive rounds on the same task set. After each round, record the success rate. Plot the learning curve (round number vs. success rate). Calculate how many rounds it takes for the agent to plateau.

    ### Challenge 3: Reflection sharing between agents
    Create two `ReflectiveAgent` instances working on different task types. After both complete their benchmarks, export reflections from one agent and import them into the other. Measure whether cross-agent reflections improve performance. This connects to the shared memory patterns in 22 Multi-Agent Shared Memory.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--16-self-reflection-memory--self-reflection-memory)
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
