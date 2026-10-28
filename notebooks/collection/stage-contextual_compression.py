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
    mo.md("# Contextual Compression in Document Retrieval\n\n## Overview\n\nThis code demonstrates the implementation of contextual compression in a document retrieval system using LangChain and OpenAI's language models. The technique aims to improve the relevance and conciseness of retrieved information by compressing and extracting the most pertinent parts of documents in the context of a given query.\n\n## Motivation\n\nTraditional document retrieval systems often return entire chunks or documents, which may contain irrelevant information. Contextual compression addresses this by intelligently extracting and compressing only the most relevant parts of retrieved documents, leading to more focused and efficient information retrieval.\n\n## Key Components\n\n1. Vector store creation from a PDF document\n2. Base retriever setup\n3. LLM-based contextual compressor\n4. Contextual compression retriever\n5. Question-answering chain integrating the compressed retriever\n\n## Method Details\n\n### Document Preprocessing and Vector Store Creation\n\n1. The PDF is processed and encoded into a vector store using a custom `encode_pdf` function.\n\n### Retriever and Compressor Setup\n\n1. A base retriever is created from the vector store.\n2. An LLM-based contextual compressor (LLMChainExtractor) is initialized using OpenAI's GPT-4 model.\n\n### Contextual Compression Retriever\n\n1. The base retriever and compressor are combined into a ContextualCompressionRetriever.\n2. This retriever first fetches documents using the base retriever, then applies the compressor to extract the most relevant information.\n\n### Question-Answering Chain\n\n1. A RetrievalQA chain is created, integrating the compression retriever.\n2. This chain uses the compressed and extracted information to generate answers to queries.\n\n## Benefits of this Approach\n\n1. Improved relevance: The system returns only the most pertinent information to the query.\n2. Increased efficiency: By compressing and extracting relevant parts, it reduces the amount of text the LLM needs to process.\n3. Enhanced context understanding: The LLM-based compressor can understand the context of the query and extract information accordingly.\n4. Flexibility: The system can be easily adapted to different types of documents and queries.\n\n## Conclusion\n\nContextual compression in document retrieval offers a powerful way to enhance the quality and efficiency of information retrieval systems. By intelligently extracting and compressing relevant information, it provides more focused and context-aware responses to queries. This approach has potential applications in various fields requiring efficient and accurate information retrieval from large document collections.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('<div style="text-align: center;">\n\n<img src="../images/contextual_compression.svg" alt="contextual compression" style="width:70%; height:auto;">\n</div>')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('# Package Installation and Imports\n\nThe cell below installs all necessary packages required to run this notebook.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Define document's path")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Create a vector store')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Create a retriever + contexual compressor + combine them ')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Example usage')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--contextual-compression)')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# Install required packages\n# SETUP (run separately): !pip install langchain python-dotenv\n\n# Clone the repository to access helper functions and evaluation modules\n# SETUP (run separately): !git clone https://github.com/NirDiamant/RAG_TECHNIQUES.git\nimport sys\nsys.path.append(\'RAG_TECHNIQUES\')\n# If you need to run with the latest data\n# !cp -r RAG_TECHNIQUES/data .\n\nimport os\nimport sys\nfrom dotenv import load_dotenv\nfrom langchain.retrievers.document_compressors import LLMChainExtractor\nfrom langchain.retrievers import ContextualCompressionRetriever\nfrom langchain.chains import RetrievalQA\n\n\n# Original path append replaced for Colab compatibility\nfrom helper_functions import *\nfrom evaluation.evalute_rag import *\n\n# Load environment variables from a .env file\nload_dotenv()\n\n# Set the OpenAI API key environment variable\nos.environ["OPENAI_API_KEY"] = os.getenv(\'OPENAI_API_KEY\')\n\n# Download required data files\nimport os\nos.makedirs(\'data\', exist_ok=True)\n\n# Download the PDF document used in this notebook\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n\npath = "data/Understanding_Climate_Change.pdf"\n\nvector_store = encode_pdf(path)\n\n# Create a retriever\nretriever = vector_store.as_retriever()\n\n\n#Create a contextual compressor\nllm = ChatOpenAI(temperature=0, model_name="gpt-4o-mini", max_tokens=4000)\ncompressor = LLMChainExtractor.from_llm(llm)\n\n#Combine the retriever with the compressor\ncompression_retriever = ContextualCompressionRetriever(\n    base_compressor=compressor,\n    base_retriever=retriever\n)\n\n# Create a QA chain with the compressed retriever\nqa_chain = RetrievalQA.from_chain_type(\n    llm=llm,\n    retriever=compression_retriever,\n    return_source_documents=True\n)\n\nquery = "What is the main topic of the document?"\nresult = qa_chain.invoke({"query": query})\nprint(result["result"])\nprint("Source documents:", result["source_documents"])', language="python", label="Recovered notebook code")
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
