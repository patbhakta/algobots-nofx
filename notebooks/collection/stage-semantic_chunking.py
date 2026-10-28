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
    mo.md('# Semantic Chunking for Document Processing\n\n## Overview\n\nThis code implements a semantic chunking approach for processing and retrieving information from PDF documents, [first proposed by Greg Kamradt](https://youtu.be/8OJC21T2SL4?t=1933) and subsequently [implemented in LangChain](https://python.langchain.com/docs/how_to/semantic-chunker/). Unlike traditional methods that split text based on fixed character or word counts, semantic chunking aims to create more meaningful and context-aware text segments.\n\n## Motivation\n\nTraditional text splitting methods often break documents at arbitrary points, potentially disrupting the flow of information and context. Semantic chunking addresses this issue by attempting to split text at more natural breakpoints, preserving semantic coherence within each chunk.\n\n## Key Components\n\n1. PDF processing and text extraction\n2. Semantic chunking using LangChain\'s SemanticChunker\n3. Vector store creation using FAISS and OpenAI embeddings\n4. Retriever setup for querying the processed documents\n\n## Method Details\n\n### Document Preprocessing\n\n1. The PDF is read and converted to a string using a custom `read_pdf_to_string` function.\n\n### Semantic Chunking\n\n1. Utilizes LangChain\'s `SemanticChunker` with OpenAI embeddings.\n2. Three breakpoint types are available:\n   - \'percentile\': Splits at differences greater than the X percentile.\n   - \'standard_deviation\': Splits at differences greater than X standard deviations.\n   - \'interquartile\': Uses the interquartile distance to determine split points.\n3. In this implementation, the \'percentile\' method is used with a threshold of 90.\n\n### Vector Store Creation\n\n1. OpenAI embeddings are used to create vector representations of the semantic chunks.\n2. A FAISS vector store is created from these embeddings for efficient similarity search.\n\n### Retriever Setup\n\n1. A retriever is configured to fetch the top 2 most relevant chunks for a given query.\n\n## Key Features\n\n1. Context-Aware Splitting: Attempts to maintain semantic coherence within chunks.\n2. Flexible Configuration: Allows for different breakpoint types and thresholds.\n3. Integration with Advanced NLP Tools: Uses OpenAI embeddings for both chunking and retrieval.\n\n## Benefits of this Approach\n\n1. Improved Coherence: Chunks are more likely to contain complete thoughts or ideas.\n2. Better Retrieval Relevance: By preserving context, retrieval accuracy may be enhanced.\n3. Adaptability: The chunking method can be adjusted based on the nature of the documents and retrieval needs.\n4. Potential for Better Understanding: LLMs or downstream tasks may perform better with more coherent text segments.\n\n## Implementation Details\n\n1. Uses OpenAI\'s embeddings for both the semantic chunking process and the final vector representations.\n2. Employs FAISS for creating an efficient searchable index of the chunks.\n3. The retriever is set up to return the top 2 most relevant chunks, which can be adjusted as needed.\n\n## Example Usage\n\nThe code includes a test query: "What is the main cause of climate change?". This demonstrates how the semantic chunking and retrieval system can be used to find relevant information from the processed document.\n\n## Conclusion\n\nSemantic chunking represents an advanced approach to document processing for retrieval systems. By attempting to maintain semantic coherence within text segments, it has the potential to improve the quality of retrieved information and enhance the performance of downstream NLP tasks. This technique is particularly valuable for processing long, complex documents where maintaining context is crucial, such as scientific papers, legal documents, or comprehensive reports.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('<div style="text-align: center;">\n\n<img src="../images/semantic_chunking_comparison.svg" alt="Self RAG" style="width:100%; height:auto;">\n</div>')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('# Package Installation and Imports\n\nThe cell below installs all necessary packages required to run this notebook.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define file path')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Read PDF to string')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Breakpoint types: \n* 'percentile': all differences between sentences are calculated, and then any difference greater than the X percentile is split.\n* 'standard_deviation': any difference greater than X standard deviations is split.\n* 'interquartile': the interquartile distance is used to split chunks.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Split original text to semantic chunks')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Create vector store and retriever')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Test the retriever')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--semantic-chunking)')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# Install required packages\n# SETUP (run separately): !pip install langchain-experimental langchain-openai python-dotenv\n\n# Clone the repository to access helper functions and evaluation modules\n# SETUP (run separately): !git clone https://github.com/NirDiamant/RAG_TECHNIQUES.git\nimport sys\nsys.path.append(\'RAG_TECHNIQUES\')\n# If you need to run with the latest data\n# !cp -r RAG_TECHNIQUES/data .\n\nimport os\nimport sys\nfrom dotenv import load_dotenv\n\n# Original path append replaced for Colab compatibility\nfrom helper_functions import *\nfrom evaluation.evalute_rag import *\n\nfrom langchain_experimental.text_splitter import SemanticChunker\nfrom langchain_openai.embeddings import OpenAIEmbeddings\n\n# Load environment variables from a .env file\nload_dotenv()\n\n# Set the OpenAI API key environment variable\nos.environ["OPENAI_API_KEY"] = os.getenv(\'OPENAI_API_KEY\')\n\n\n# Download required data files\nimport os\nos.makedirs(\'data\', exist_ok=True)\n\n# Download the PDF document used in this notebook\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n\npath = "data/Understanding_Climate_Change.pdf"\n\ncontent = read_pdf_to_string(path)\n\ntext_splitter = SemanticChunker(OpenAIEmbeddings(), breakpoint_threshold_type=\'percentile\', breakpoint_threshold_amount=90) # chose which embeddings and breakpoint type and threshold to use\n\ndocs = text_splitter.create_documents([content])\n\nembeddings = OpenAIEmbeddings()\nvectorstore = FAISS.from_documents(docs, embeddings)\nchunks_query_retriever = vectorstore.as_retriever(search_kwargs={"k": 2})\n\ntest_query = "What is the main cause of climate change?"\ncontext = retrieve_context_per_question(test_query, chunks_query_retriever)\nshow_context(context)', language="python", label="Recovered notebook code")
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
