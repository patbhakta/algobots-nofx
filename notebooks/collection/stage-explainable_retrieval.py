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
    mo.md("# Explainable Retrieval in Document Search\n\n## Overview\n\nThis code implements an Explainable Retriever, a system that not only retrieves relevant documents based on a query but also provides explanations for why each retrieved document is relevant. It combines vector-based similarity search with natural language explanations, enhancing the transparency and interpretability of the retrieval process.\n\n## Motivation\n\nTraditional document retrieval systems often work as black boxes, providing results without explaining why they were chosen. This lack of transparency can be problematic in scenarios where understanding the reasoning behind the results is crucial. The Explainable Retriever addresses this by offering insights into the relevance of each retrieved document.\n\n## Key Components\n\n1. Vector store creation from input texts\n2. Base retriever using FAISS for efficient similarity search\n3. Language model (LLM) for generating explanations\n4. Custom ExplainableRetriever class that combines retrieval and explanation generation\n\n## Method Details\n\n### Document Preprocessing and Vector Store Creation\n\n1. Input texts are converted into embeddings using OpenAI's embedding model.\n2. A FAISS vector store is created from these embeddings for efficient similarity search.\n\n### Retriever Setup\n\n1. A base retriever is created from the vector store, configured to return the top 5 most similar documents.\n\n### Explanation Generation\n\n1. An LLM (GPT-4) is used to generate explanations.\n2. A custom prompt template is defined to guide the LLM in explaining the relevance of retrieved documents.\n\n### ExplainableRetriever Class\n\n1. Combines the base retriever and explanation generation into a single interface.\n2. The `retrieve_and_explain` method:\n   - Retrieves relevant documents using the base retriever.\n   - For each retrieved document, generates an explanation of its relevance to the query.\n   - Returns a list of dictionaries containing both the document content and its explanation.\n\n## Benefits of this Approach\n\n1. Transparency: Users can understand why specific documents were retrieved.\n2. Trust: Explanations build user confidence in the system's results.\n3. Learning: Users can gain insights into the relationships between queries and documents.\n4. Debugging: Easier to identify and correct issues in the retrieval process.\n5. Customization: The explanation prompt can be tailored for different use cases or domains.\n\n## Conclusion\n\nThe Explainable Retriever represents a significant step towards more interpretable and trustworthy information retrieval systems. By providing natural language explanations alongside retrieved documents, it bridges the gap between powerful vector-based search techniques and human understanding. This approach has potential applications in various fields where the reasoning behind information retrieval is as important as the retrieved information itself, such as legal research, medical information systems, and educational tools.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('# Package Installation and Imports\n\nThe cell below installs all necessary packages required to run this notebook.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define the explainable retriever class ')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Create a mock example and explainable retriever instance')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Show the results')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--explainable-retrieval)')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# Install required packages\n# SETUP (run separately): !pip install python-dotenv\n\n# Clone the repository to access helper functions and evaluation modules\n# SETUP (run separately): !git clone https://github.com/NirDiamant/RAG_TECHNIQUES.git\nimport sys\nsys.path.append(\'RAG_TECHNIQUES\')\n# If you need to run with the latest data\n# !cp -r RAG_TECHNIQUES/data .\n\nimport os\nimport sys\nfrom dotenv import load_dotenv\n\n\n# Original path append replaced for Colab compatibility\nfrom helper_functions import *\nfrom evaluation.evalute_rag import *\n\n# Load environment variables from a .env file\nload_dotenv()\n\n# Set the OpenAI API key environment variable\nos.environ["OPENAI_API_KEY"] = os.getenv(\'OPENAI_API_KEY\')\n\nclass ExplainableRetriever:\n    def __init__(self, texts):\n        self.embeddings = OpenAIEmbeddings()\n\n        self.vectorstore = FAISS.from_texts(texts, self.embeddings)\n        self.llm = ChatOpenAI(temperature=0, model_name="gpt-4o-mini", max_tokens=4000)\n\n        \n        # Create a base retriever\n        self.retriever = self.vectorstore.as_retriever(search_kwargs={"k": 5})\n        \n        # Create an explanation chain\n        explain_prompt = PromptTemplate(\n            input_variables=["query", "context"],\n            template="""\n            Analyze the relationship between the following query and the retrieved context.\n            Explain why this context is relevant to the query and how it might help answer the query.\n            \n            Query: {query}\n            \n            Context: {context}\n            \n            Explanation:\n            """\n        )\n        self.explain_chain = explain_prompt | self.llm\n\n    def retrieve_and_explain(self, query):\n        # Retrieve relevant documents\n        docs = self.retriever.get_relevant_documents(query)\n        \n        explained_results = []\n        \n        for doc in docs:\n            # Generate explanation\n            input_data = {"query": query, "context": doc.page_content}\n            explanation = self.explain_chain.invoke(input_data).content\n            \n            explained_results.append({\n                "content": doc.page_content,\n                "explanation": explanation\n            })\n        \n        return explained_results\n\n\n\n# Usage\ntexts = [\n    "The sky is blue because of the way sunlight interacts with the atmosphere.",\n    "Photosynthesis is the process by which plants use sunlight to produce energy.",\n    "Global warming is caused by the increase of greenhouse gases in Earth\'s atmosphere."\n]\n\nexplainable_retriever = ExplainableRetriever(texts)\n\nquery = "Why is the sky blue?"\nresults = explainable_retriever.retrieve_and_explain(query)\n\nfor i, result in enumerate(results, 1):\n    print(f"Result {i}:")\n    print(f"Content: {result[\'content\']}")\n    print(f"Explanation: {result[\'explanation\']}")\n    print()', language="python", label="Recovered notebook code")
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
