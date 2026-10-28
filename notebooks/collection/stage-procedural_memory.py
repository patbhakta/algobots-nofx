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
    mo.md('# Procedural Memory\n\n> Capture learned procedures, workflows, and "how-to" knowledge so your agent improves with experience.\n\nThink about making coffee for the first time in a new kitchen. You open every cabinet, check every drawer, and fumble with the machine. By the tenth morning, your hands move on autopilot. You\'ve internalized the procedure.\n\nMost memory techniques store *what happened* (episodic) or *what is true* (semantic). Procedural memory stores *how to do things*. It captures the step-by-step strategies and workflows (sequences of actions that accomplish a goal) that an agent discovers through experience.\n\nHere\'s the problem. When an agent solves a complex task through reasoning and tool calls, that successful action sequence is valuable knowledge. Without procedural memory, the agent re-derives the solution from scratch every time. With procedural memory, it retrieves the learned procedure and adapts it to the new situation.\n\nSystems like Voyager (Wang et al., 2023) show this in practice. That Minecraft agent writes reusable code-based skills and stores them in a skill library (an organized collection of procedures). When a similar task appears, it retrieves the stored skill instead of starting over.\n\n**In this notebook, you\'ll build a procedural memory system from scratch.** It will:\n1. Extract reusable procedures from successful execution traces (logs of agent actions).\n2. Store them in a skill library indexed by task type.\n3. Retrieve matching procedures when new tasks arrive.\n4. Adapt the retrieved procedure to the new context.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Key Concepts\n\n- **Execution trace**: A log of everything the agent did during a task. It includes actions taken, tools called, inputs provided, and outputs received.\n- **Procedure extraction**: Identifying a reusable action sequence from a specific execution trace. An LLM (large language model, an AI that processes text) reviews the trace and distills it into a clean template.\n- **Workflow template**: A parameterized procedure where specific values (file names, server addresses, app names) are replaced with placeholders like `{app_name}`. This makes the workflow apply to new inputs without rewriting it.\n- **Skill library**: An organized collection of procedures indexed by task type. The library grows as the agent solves new kinds of tasks.\n- **Procedure adaptation**: Filling in a template\'s placeholders with concrete values for a new task. The adapted procedure is ready to execute.\n- **Procedure generalization**: Abstracting a specific procedure into a broader form. "Deploy weather-api to deploy.cloudhost.io" becomes "Deploy {app_name} to {server_host}".')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Architecture\n\n<p align="center">\n  <img src="../../images/diagrams/11_procedural_memory.svg" alt="Procedural Memory Architecture" width="720"/>\n</p>\n\n<details><summary>Mermaid source</summary>\n\n```mermaid\nflowchart LR\n    Task["Task Execution\\n(step-by-step)"] --> SuccessCheck{"Task\\nSucceeded?"}\n    SuccessCheck -- No --> Discard["Discard / Log\\nfor debugging"]\n    SuccessCheck -- Yes --> Extractor["Procedure Extractor\\n(LLM call)"]\n    Extractor --> Template["Workflow Template\\n(parameterized steps)"]\n    Template --> Library["Skill Library\\n(indexed by task type)"]\n    NewTask["New Task"] --> Retrieval["Retrieval\\n(task-type matching)"]\n    Library --> Retrieval\n    Retrieval --> Adaptation["Adaptation\\n(fill parameters)"]\n    Adaptation --> Execution["Execute Adapted\\nProcedure"]\n```\n\n</details>\n\n**Data flow:** When the agent completes a task, the execution trace goes to a procedure extractor (an LLM call). The extractor distills the action sequence into a parameterized workflow template. That template is stored in the skill library, indexed by task type and metadata.\n\nWhen a new task arrives, the retrieval engine matches it against the library. If it finds a relevant procedure, it adapts the template by filling placeholders with concrete values. If no match exists, the agent solves the task from scratch. Then the cycle repeats.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Setup\n\nWe need the OpenAI Python SDK for LLM calls and `python-dotenv` for loading API keys from a `.env` file.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Load the API key and create the OpenAI client. Set `OPENAI_API_KEY` in your `.env` file before running.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Implementation\n\nWe'll build three components:\n\n1. **Procedure data model.** A dataclass that holds the procedure's name, steps, parameters, and metadata.\n2. **LLM prompt templates.** Three prompts that power extraction, retrieval, and adaptation.\n3. **ProceduralMemory class.** The core engine that ties everything together.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Procedure Data Model\n\nThink of a recipe card in a box. Each card records the dish name, the category (appetizer, main, dessert), the ingredients you'll need, and the numbered steps. Our `Procedure` dataclass is that recipe card.\n\nThe `steps` field holds parameterized action descriptions. The `parameters` field lists the placeholder names used in those steps. The `preconditions` field records what must be true before the procedure can run.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### LLM Prompt Templates\n\nThe system makes three distinct LLM calls, each with its own prompt.\n\n1. **Extraction prompt**: Reads an execution trace and produces a parameterized procedure.\n2. **Retrieval prompt**: Compares a new task against the skill library and picks the best match.\n3. **Adaptation prompt**: Fills in a procedure's placeholders with values from the new task context.\n\nAll three prompts request JSON output. This makes parsing reliable.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### ProceduralMemory Class\n\nThis class ties extraction, storage, retrieval, and adaptation together. The skill library is a Python list. In a production system, you'd use a database with vector search (finding similar items by comparing their numeric representations) for faster retrieval. For learning purposes, a list with LLM-based matching works well.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("Next we add the retrieval and adaptation methods. Retrieval compares the new task description against all stored procedures using the LLM. Adaptation fills in a procedure's placeholders with concrete values from the new task context.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('The `learn_from_execution` method ties the loop together: if a task succeeded, it extracts and stores a procedure in one call. The helper methods handle duplicate detection and library listing.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Example Run\n\nLet's see procedural memory in action. We'll walk through three scenarios:\n\n1. An agent deploys a web API. We extract and store the deployment procedure.\n2. A similar deployment task arrives. We retrieve the stored procedure and adapt it.\n3. A data pipeline task runs. We extract a second procedure, growing the library.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Scenario 1: Learn a Deployment Procedure\n\nBelow is an execution trace from an agent that deployed a Flask API to a cloud server. Each line records one action the agent took.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('We pass the trace to `learn_from_execution`. The LLM extracts a parameterized procedure and the system stores it in the skill library.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Scenario 2: Retrieve and Adapt for a New Task\n\nA new task arrives: deploy a different API to a different server. Instead of solving from scratch, the agent checks its skill library first.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('The retrieval engine found our deployment procedure. Now we adapt it. The adaptation step fills in each placeholder with a concrete value from the new task.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Scenario 3: Grow the Library\n\nNow the agent runs a data pipeline task. This is a different task type, so the system creates a new procedure alongside the deployment one.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("The skill library now holds two procedures from different domains. Let's inspect both.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Selective Retrieval\n\nWith multiple procedures in the library, the retrieval engine must pick the right one. Let's test it with tasks from each domain.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("## Tradeoffs\n\n### When Procedural Memory Works Well\n\n- **Repetitive multi-step tasks.** Agents that deploy services, run data pipelines, or integrate APIs perform similar workflows repeatedly. Storing the procedure avoids re-deriving the steps each time.\n- **Skill transfer across sessions.** A procedure extracted in one session is available in the next. The agent's capability grows over time without retraining or fine-tuning.\n- **Faster execution.** Retrieving a stored procedure and adapting it takes fewer LLM calls than solving from scratch with multi-step reasoning.\n\n### When It Breaks Down\n\n- **Novel tasks.** If every task is unique, the skill library never gets reused. The extraction cost adds overhead with no payoff.\n- **Fragile procedures.** A procedure extracted from one successful run may not generalize well. If the environment changes (different OS, different API version), the stored steps can fail without warning. You need feedback loops and versioning to handle this.\n- **Retrieval errors.** LLM-based retrieval can match the wrong procedure, especially as the library grows large. Production systems need confidence thresholds and fallback behavior (solve from scratch if confidence is low).\n- **Stale procedures.** Procedures become outdated as tools and APIs change. Without a way to invalidate or update old procedures, the library accumulates unreliable knowledge.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Further Reading\n\n- [Wang et al., "Voyager: An Open-Ended Embodied Agent with Large Language Models," 2023](https://arxiv.org/abs/2305.16291) - A Minecraft agent that builds a reusable skill library of code-based procedures. The closest existing system to what we built here.\n- [Sumers et al., "Cognitive Architectures for Language Agents," 2023](https://arxiv.org/abs/2309.02427) - A survey of cognitive architectures for LLM agents. Covers procedural memory as a core component alongside episodic and semantic memory.\n- [Anderson, "Acquisition of Cognitive Skill," *Psychological Review*, 1982](https://doi.org/10.1037/0033-295X.89.4.369) - The foundational psychology paper on how humans transition from declarative knowledge ("knowing that") to procedural knowledge ("knowing how").\n- [Park et al., "Generative Agents: Interactive Simulacra of Human Behavior," 2023](https://arxiv.org/abs/2304.03442) - Simulated agents that develop behavioral patterns through memory and reflection. A form of emergent procedural knowledge.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('---\n\n*\\u2190 Previous: [10 - Semantic Memory](../10_semantic_memory/) \\u00b7 Next: [12 - Working Memory / Context Window](../12_working_memory_context_window/) \\u2192*')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## 🧪 Try It Yourself\n\nThree small challenges to deepen your understanding. Each should take 10-30 minutes.\n\n### Challenge 1: Procedure versioning\nAdd a `version` field and a `history` list to the `Procedure` dataclass. Each time `store_procedure()` updates an existing procedure, increment the version and archive the previous one. Print the version history after several learning cycles.\n\n### Challenge 2: Adaptation success rate\nCreate 5 task variants that require adapting the same base procedure. Run `adapt_procedure()` for each, then execute the adapted procedure and score success. Report the adaptation success rate and identify which types of adaptations fail most often.\n\n### Challenge 3: Memory-management procedures\nUse `ProceduralMemory` to store procedures about when to summarize, when to forget, and when to consolidate memories. Feed these procedures back into an agent that manages its own memory. This combines procedural memory with the routing logic from 17 Memory Routing.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--11-procedural-memory--procedural-memory)')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# SETUP (run separately): %pip install -q openai python-dotenv\n\nimport os\nimport json\nfrom dataclasses import dataclass, field\nfrom datetime import datetime\n\nfrom dotenv import load_dotenv\nfrom openai import OpenAI\n\nload_dotenv()\n\nclient = OpenAI()  # reads OPENAI_API_KEY from environment\nMODEL = "gpt-4o-mini"\n\nassert os.getenv("OPENAI_API_KEY"), "Set OPENAI_API_KEY in your .env file"\n\n@dataclass\nclass Procedure:\n    """A reusable, parameterized procedure extracted from a successful task."""\n\n    name: str\n    task_type: str\n    description: str\n    steps: list[str]           # parameterized action descriptions\n    parameters: list[str]      # placeholder names (e.g., ["app_name", "server_host"])\n    preconditions: list[str]   # what must be true before execution\n    success_count: int = 0\n    created_at: str = field(default_factory=lambda: datetime.now().isoformat())\n\n    def display(self) -> None:\n        """Print a readable summary of this procedure."""\n        print(f"Procedure: {self.name}")\n        print(f"  Type: {self.task_type}")\n        print(f"  Description: {self.description}")\n        print(f"  Parameters: {self.parameters}")\n        print(f"  Preconditions: {self.preconditions}")\n        print(f"  Steps:")\n        for i, step in enumerate(self.steps, 1):\n            print(f"    {i}. {step}")\n        print(f"  Success count: {self.success_count}")\n\nEXTRACTION_PROMPT = """\\\nYou are a procedure extractor. You receive an execution trace from a \\\nsuccessful task. Your job: distill it into a reusable, parameterized procedure.\n\nRules:\n- Replace specific values (file names, URLs, server addresses, app names) \\\nwith descriptive placeholders like {app_name}, {server_host}, {file_path}.\n- Keep the steps in execution order.\n- Remove noise (debug output, retries, irrelevant side-effects).\n- Identify preconditions (what must be true before this procedure can run).\n\nReturn a JSON object with these fields:\n- name: short name for the procedure (e.g., "Deploy containerized app")\n- task_type: category (e.g., "deployment", "data_pipeline", "api_integration")\n- description: one-sentence summary of what this procedure accomplishes\n- steps: list of parameterized step descriptions (strings)\n- parameters: list of placeholder names used in the steps\n- preconditions: list of conditions that must hold before execution\n"""\n\nRETRIEVAL_PROMPT = """\\\nYou are a procedure retrieval engine. You receive a task description and a \\\nskill library (a list of stored procedures with index numbers).\n\nPick the best matching procedure for the task.\n\nReturn a JSON object with:\n- best_match_index: integer index of the best match, or null if none is relevant\n- confidence: float between 0.0 and 1.0\n- reasoning: one sentence explaining your choice\n"""\n\nADAPTATION_PROMPT = """\\\nYou are a procedure adaptation engine. You receive a parameterized procedure \\\nand a new task context. Fill in the placeholders with concrete values from \\\nthe context.\n\nReturn a JSON object with:\n- adapted_steps: list of concrete step descriptions (placeholders filled in)\n- parameter_values: object mapping each parameter name to its concrete value\n"""\n\nclass ProceduralMemory:\n    """A skill library that learns procedures from successful task executions."""\n\n    def __init__(self, client: OpenAI, model: str = "gpt-4o-mini"):\n        self.client = client\n        self.model = model\n        self.skill_library: list[Procedure] = []\n\n    # ── Extraction ───────────────────────────────────────────────\n    def extract_procedure(self, execution_trace: str) -> Procedure:\n        """Use the LLM to extract a reusable procedure from an execution trace."""\n        response = self.client.chat.completions.create(\n            model=self.model,\n            messages=[\n                {"role": "system", "content": EXTRACTION_PROMPT},\n                {"role": "user", "content": f"Execution trace:\\n{execution_trace}"},\n            ],\n            response_format={"type": "json_object"},\n        )\n        data = json.loads(response.choices[0].message.content)\n        return Procedure(\n            name=data["name"],\n            task_type=data["task_type"],\n            description=data["description"],\n            steps=data["steps"],\n            parameters=data["parameters"],\n            preconditions=data.get("preconditions", []),\n        )\n\n    # ── Storage ──────────────────────────────────────────────────\n    def store_procedure(self, procedure: Procedure) -> str:\n        """Add a procedure to the skill library. Merge if a similar one exists."""\n        existing = self._find_similar(procedure)\n        if existing:\n            existing.success_count += 1\n            return f"Merged with existing: \'{existing.name}\' (count: {existing.success_count})"\n        self.skill_library.append(procedure)\n        return f"Stored new procedure: \'{procedure.name}\'"\n\n    # ── Retrieval ────────────────────────────────────────────────\n    def retrieve_procedure(self, task_description: str) -> tuple[Procedure | None, dict]:\n        """Find the best matching procedure for a new task."""\n        if not self.skill_library:\n            return None, {"reasoning": "Skill library is empty."}\n\n        library_summary = "\\n".join(\n            f"[{i}] {p.name} (type: {p.task_type}): {p.description}"\n            for i, p in enumerate(self.skill_library)\n        )\n\n        response = self.client.chat.completions.create(\n            model=self.model,\n            messages=[\n                {"role": "system", "content": RETRIEVAL_PROMPT},\n                {"role": "user", "content": (\n                    f"Task: {task_description}\\n\\n"\n                    f"Skill library:\\n{library_summary}"\n                )},\n            ],\n            response_format={"type": "json_object"},\n        )\n        result = json.loads(response.choices[0].message.content)\n        idx = result.get("best_match_index")\n        if idx is not None and 0 <= idx < len(self.skill_library):\n            return self.skill_library[idx], result\n        return None, result\n\n    # ── Adaptation ───────────────────────────────────────────────\n    def adapt_procedure(self, procedure: Procedure, task_context: str) -> dict:\n        """Adapt a procedure\'s steps to a new context by filling placeholders."""\n        steps_text = "\\n".join(\n            f"  {i+1}. {s}" for i, s in enumerate(procedure.steps)\n        )\n\n        response = self.client.chat.completions.create(\n            model=self.model,\n            messages=[\n                {"role": "system", "content": ADAPTATION_PROMPT},\n                {"role": "user", "content": (\n                    f"Procedure: {procedure.name}\\n"\n                    f"Steps:\\n{steps_text}\\n\\n"\n                    f"Parameters: {procedure.parameters}\\n\\n"\n                    f"New task context: {task_context}"\n                )},\n            ],\n            response_format={"type": "json_object"},\n        )\n        return json.loads(response.choices[0].message.content)\n\n    # ── Full learning loop ───────────────────────────────────────\n    def learn_from_execution(\n        self, execution_trace: str, success: bool\n    ) -> Procedure | None:\n        """Extract and store a procedure if the task succeeded."""\n        if not success:\n            print("Task failed. Skipping procedure extraction.")\n            return None\n        procedure = self.extract_procedure(execution_trace)\n        status = self.store_procedure(procedure)\n        print(status)\n        return procedure\n\n    # ── Internal helpers ─────────────────────────────────────────\n    def _find_similar(self, procedure: Procedure) -> Procedure | None:\n        """Check if a similar procedure already exists (by type and name)."""\n        for p in self.skill_library:\n            if (\n                p.task_type == procedure.task_type\n                and p.name.lower() == procedure.name.lower()\n            ):\n                return p\n        return None\n\n    def list_procedures(self) -> None:\n        """Print all procedures in the skill library."""\n        if not self.skill_library:\n            print("Skill library is empty.")\n            return\n        for i, p in enumerate(self.skill_library):\n            print(f"\\n{\'=\'*60}")\n            print(f"[{i}] ", end="")\n            p.display()\n\ndeployment_trace = """\\\n1. Created project directory "weather-api"\n2. Initialized Python 3.11 virtual environment in weather-api/venv\n3. Installed dependencies: flask, requests, gunicorn (pip install)\n4. Wrote application code in weather-api/app.py with /forecast and /health endpoints\n5. Wrote unit tests in weather-api/test_app.py\n6. Ran pytest on test_app.py - all 8 tests passed\n7. Created Dockerfile with python:3.11-slim base image\n8. Built Docker image tagged "weather-api:v1"\n9. Pushed image to container registry at registry.cloudhost.io/weather-api:v1\n10. Connected via SSH to server at deploy.cloudhost.io\n11. Pulled the Docker image on the server\n12. Started container with port mapping 80:5000 using docker-compose\n13. Verified health check at https://deploy.cloudhost.io/health returned 200 OK\n"""\n\nprint(deployment_trace)\n\nmemory = ProceduralMemory(client=client, model=MODEL)\n\nprocedure = memory.learn_from_execution(deployment_trace, success=True)\nprint()\nprocedure.display()\n\nnew_task = "Deploy the inventory-service (a FastAPI app) to production server prod.mycompany.com"\n\nmatched_procedure, retrieval_info = memory.retrieve_procedure(new_task)\n\nprint("Retrieval result:")\nprint(f"  Matched: {matched_procedure.name if matched_procedure else \'None\'}")\nprint(f"  Confidence: {retrieval_info.get(\'confidence\', \'N/A\')}")\nprint(f"  Reasoning: {retrieval_info.get(\'reasoning\', \'N/A\')}")\n\ntask_context = (\n    "App name: inventory-service. "\n    "Framework: FastAPI. "\n    "Server: prod.mycompany.com. "\n    "Registry: docker.mycompany.com. "\n    "Port mapping: 80:8000. "\n    "Python version: 3.12."\n)\n\nadaptation = memory.adapt_procedure(matched_procedure, task_context)\n\nprint("Adapted steps for the new task:\\n")\nfor i, step in enumerate(adaptation["adapted_steps"], 1):\n    print(f"  {i}. {step}")\n\nprint(f"\\nParameter values:")\nprint(json.dumps(adaptation.get("parameter_values", {}), indent=2))\n\npipeline_trace = """\\\n1. Connected to PostgreSQL database at db.analytics.io:5432\n2. Queried the \'sales\' table for records where date >= \'2024-01-01\' and date < \'2024-02-01\'\n3. Loaded 15,420 rows into a pandas DataFrame\n4. Cleaned data: dropped 23 rows with null revenue, converted currency columns to USD\n5. Grouped by region and product_category, computed sum of revenue and count of orders\n6. Generated a summary CSV report with 48 rows (one per region-category pair)\n7. Uploaded report to S3 at s3://company-reports/monthly/2024-01-sales-summary.csv\n8. Sent notification email to analytics-team@company.com with the S3 link\n"""\n\npipeline_procedure = memory.learn_from_execution(pipeline_trace, success=True)\n\nmemory.list_procedures()\n\n# A deployment task should match the deployment procedure\ntask_a = "Deploy the user-auth microservice to staging server staging.myapp.io"\nmatch_a, info_a = memory.retrieve_procedure(task_a)\nprint(f"Task: {task_a}")\nprint(f"  Matched: {match_a.name if match_a else \'None\'}")\nprint(f"  Reasoning: {info_a.get(\'reasoning\', \'N/A\')}")\n\nprint()\n\n# A data task should match the pipeline procedure\ntask_b = "Generate the February 2024 sales report from the analytics database"\nmatch_b, info_b = memory.retrieve_procedure(task_b)\nprint(f"Task: {task_b}")\nprint(f"  Matched: {match_b.name if match_b else \'None\'}")\nprint(f"  Reasoning: {info_b.get(\'reasoning\', \'N/A\')}")', language="python", label="Recovered notebook code")
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
