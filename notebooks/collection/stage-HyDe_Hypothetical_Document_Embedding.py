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
    mo.md("# Hypothetical Document Embedding (HyDE) in Document Retrieval\n\n## Overview\n\nThis code implements a Hypothetical Document Embedding (HyDE) system for document retrieval. HyDE is an innovative approach that transforms query questions into hypothetical documents containing the answer, aiming to bridge the gap between query and document distributions in vector space.\n\n## Motivation\n\nTraditional retrieval methods often struggle with the semantic gap between short queries and longer, more detailed documents. HyDE addresses this by expanding the query into a full hypothetical document, potentially improving retrieval relevance by making the query representation more similar to the document representations in the vector space.\n\n## Key Components\n\n1. PDF processing and text chunking\n2. Vector store creation using FAISS and OpenAI embeddings\n3. Language model for generating hypothetical documents\n4. Custom HyDERetriever class implementing the HyDE technique\n\n## Method Details\n\n### Document Preprocessing and Vector Store Creation\n\n1. The PDF is processed and split into chunks.\n2. A FAISS vector store is created using OpenAI embeddings for efficient similarity search.\n\n### Hypothetical Document Generation\n\n1. A language model (GPT-4) is used to generate a hypothetical document that answers the given query.\n2. The generation is guided by a prompt template that ensures the hypothetical document is detailed and matches the chunk size used in the vector store.\n\n### Retrieval Process\n\nThe `HyDERetriever` class implements the following steps:\n\n1. Generate a hypothetical document from the query using the language model.\n2. Use the hypothetical document as the search query in the vector store.\n3. Retrieve the most similar documents to this hypothetical document.\n\n## Key Features\n\n1. Query Expansion: Transforms short queries into detailed hypothetical documents.\n2. Flexible Configuration: Allows adjustment of chunk size, overlap, and number of retrieved documents.\n3. Integration with OpenAI Models: Uses GPT-4 for hypothetical document generation and OpenAI embeddings for vector representation.\n\n## Benefits of this Approach\n\n1. Improved Relevance: By expanding queries into full documents, HyDE can potentially capture more nuanced and relevant matches.\n2. Handling Complex Queries: Particularly useful for complex or multi-faceted queries that might be difficult to match directly.\n3. Adaptability: The hypothetical document generation can adapt to different types of queries and document domains.\n4. Potential for Better Context Understanding: The expanded query might better capture the context and intent behind the original question.\n\n## Implementation Details\n\n1. Uses OpenAI's ChatGPT model for hypothetical document generation.\n2. Employs FAISS for efficient similarity search in the vector space.\n3. Allows for easy visualization of both the hypothetical document and retrieved results.\n\n## Conclusion\n\nHypothetical Document Embedding (HyDE) represents an innovative approach to document retrieval, addressing the semantic gap between queries and documents. By leveraging advanced language models to expand queries into hypothetical documents, HyDE has the potential to significantly improve retrieval relevance, especially for complex or nuanced queries. This technique could be particularly valuable in domains where understanding query intent and context is crucial, such as legal research, academic literature review, or advanced information retrieval systems.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('<div style="text-align: center;">\n\n<img src="../images/HyDe.svg" alt="HyDe" style="width:40%; height:auto;">\n</div>')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('<div style="text-align: center;">\n\n<img src="../images/hyde-advantages.svg" alt="HyDe" style="width:100%; height:auto;">\n</div>')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('# Package Installation and Imports\n\nThe cell below installs all necessary packages required to run this notebook.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define document(s) path')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define the HyDe retriever class - creating vector store, generating hypothetical document, and retrieving')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Create a HyDe retriever instance')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Demonstrate on a use case')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Plot the hypothetical document and the retrieved documnets ')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--hyde-hypothetical-document-embedding)')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# Install required packages\n# SETUP (run separately): !pip install python-dotenv\n\n# Clone the repository to access helper functions and evaluation modules\n# SETUP (run separately): !git clone https://github.com/NirDiamant/RAG_TECHNIQUES.git\nimport sys\nsys.path.append(\'RAG_TECHNIQUES\')\n# If you need to run with the latest data\n# !cp -r RAG_TECHNIQUES/data .\n\nimport os\nimport sys\nfrom dotenv import load_dotenv\n\n\n# Original path append replaced for Colab compatibility\nfrom helper_functions import *\nfrom evaluation.evalute_rag import *\n\n# Load environment variables from a .env file\nload_dotenv()\n\n# Set the OpenAI API key environment variable\nos.environ["OPENAI_API_KEY"] = os.getenv(\'OPENAI_API_KEY\')\n\n# Download required data files\nimport os\nos.makedirs(\'data\', exist_ok=True)\n\n# Download the PDF document used in this notebook\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n\npath = "data/Understanding_Climate_Change.pdf"\n\nclass HyDERetriever:\n    def __init__(self, files_path, chunk_size=500, chunk_overlap=100):\n        self.llm = ChatOpenAI(temperature=0, model_name="gpt-4o-mini", max_tokens=4000)\n\n        self.embeddings = OpenAIEmbeddings()\n        self.chunk_size = chunk_size\n        self.chunk_overlap = chunk_overlap\n        self.vectorstore = encode_pdf(files_path, chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)\n    \n        \n        self.hyde_prompt = PromptTemplate(\n            input_variables=["query", "chunk_size"],\n            template="""Given the question \'{query}\', generate a hypothetical document that directly answers this question. The document should be detailed and in-depth.\n            the document size has be exactly {chunk_size} characters.""",\n        )\n        self.hyde_chain = self.hyde_prompt | self.llm\n\n    def generate_hypothetical_document(self, query):\n        input_variables = {"query": query, "chunk_size": self.chunk_size}\n        return self.hyde_chain.invoke(input_variables).content\n\n    def retrieve(self, query, k=3):\n        hypothetical_doc = self.generate_hypothetical_document(query)\n        similar_docs = self.vectorstore.similarity_search(hypothetical_doc, k=k)\n        return similar_docs, hypothetical_doc\n\nretriever = HyDERetriever(path)\n\ntest_query = "What is the main cause of climate change?"\nresults, hypothetical_doc = retriever.retrieve(test_query)\n\ndocs_content = [doc.page_content for doc in results]\n\nprint("hypothetical_doc:\\n")\nprint(text_wrap(hypothetical_doc)+"\\n")\nshow_context(docs_content)', language="python", label="Recovered notebook code")
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
