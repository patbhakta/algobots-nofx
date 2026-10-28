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
    mo.md("# Fusion Retrieval in Document Search\n\n## Overview\n\nThis code implements a Fusion Retrieval system that combines vector-based similarity search with keyword-based BM25 retrieval. The approach aims to leverage the strengths of both methods to improve the overall quality and relevance of document retrieval.\n\n## Motivation\n\nTraditional retrieval methods often rely on either semantic understanding (vector-based) or keyword matching (BM25). Each approach has its strengths and weaknesses. Fusion retrieval aims to combine these methods to create a more robust and accurate retrieval system that can handle a wider range of queries effectively.\n\n## Key Components\n\n1. PDF processing and text chunking\n2. Vector store creation using FAISS and OpenAI embeddings\n3. BM25 index creation for keyword-based retrieval\n4. Custom fusion retrieval function that combines both methods\n\n## Method Details\n\n### Document Preprocessing\n\n1. The PDF is loaded and split into chunks using RecursiveCharacterTextSplitter.\n2. Chunks are cleaned by replacing 't' with spaces (likely addressing a specific formatting issue).\n\n### Vector Store Creation\n\n1. OpenAI embeddings are used to create vector representations of the text chunks.\n2. A FAISS vector store is created from these embeddings for efficient similarity search.\n\n### BM25 Index Creation\n\n1. A BM25 index is created from the same text chunks used for the vector store.\n2. This allows for keyword-based retrieval alongside the vector-based method.\n\n### Fusion Retrieval Function\n\nThe `fusion_retrieval` function is the core of this implementation:\n\n1. It takes a query and performs both vector-based and BM25-based retrieval.\n2. Scores from both methods are normalized to a common scale.\n3. A weighted combination of these scores is computed (controlled by the `alpha` parameter).\n4. Documents are ranked based on the combined scores, and the top-k results are returned.\n\n## Benefits of this Approach\n\n1. Improved Retrieval Quality: By combining semantic and keyword-based search, the system can capture both conceptual similarity and exact keyword matches.\n2. Flexibility: The `alpha` parameter allows for adjusting the balance between vector and keyword search based on specific use cases or query types.\n3. Robustness: The combined approach can handle a wider range of queries effectively, mitigating weaknesses of individual methods.\n4. Customizability: The system can be easily adapted to use different vector stores or keyword-based retrieval methods.\n\n## Conclusion\n\nFusion retrieval represents a powerful approach to document search that combines the strengths of semantic understanding and keyword matching. By leveraging both vector-based and BM25 retrieval methods, it offers a more comprehensive and flexible solution for information retrieval tasks. This approach has potential applications in various fields where both conceptual similarity and keyword relevance are important, such as academic research, legal document search, or general-purpose search engines.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('<div style="text-align: center;">\n\n<img src="../images/fusion_retrieval.svg" alt="Fusion Retrieval" style="width:100%; height:auto;">\n</div>')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('# Package Installation and Imports\n\nThe cell below installs all necessary packages required to run this notebook.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define document path')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Encode the pdf to vector store and return split document from the step before to create BM25 instance')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Create vectorstore and get the chunked documents')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Create a bm25 index for retrieving documents by keywords')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define a function that retrieves both semantically and by keyword, normalizes the scores and gets the top k documents')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Use Case example')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--fusion-retrieval)')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# Install required packages\n# SETUP (run separately): !pip install langchain numpy python-dotenv rank-bm25\n\n# Clone the repository to access helper functions and evaluation modules\n# SETUP (run separately): !git clone https://github.com/NirDiamant/RAG_TECHNIQUES.git\nimport sys\nsys.path.append(\'RAG_TECHNIQUES\')\n# If you need to run with the latest data\n# !cp -r RAG_TECHNIQUES/data .\n\nimport os\nimport sys\nfrom dotenv import load_dotenv\nfrom langchain.docstore.document import Document\n\nfrom typing import List\nfrom rank_bm25 import BM25Okapi\nimport numpy as np\n\n\n# Original path append replaced for Colab compatibility\nfrom helper_functions import *\nfrom evaluation.evalute_rag import *\n\n# Load environment variables from a .env file\nload_dotenv()\n\n# Set the OpenAI API key environment variable\nos.environ["OPENAI_API_KEY"] = os.getenv(\'OPENAI_API_KEY\')\n\n# Download required data files\nimport os\nos.makedirs(\'data\', exist_ok=True)\n\n# Download the PDF document used in this notebook\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n\npath = "data/Understanding_Climate_Change.pdf"\n\ndef encode_pdf_and_get_split_documents(path, chunk_size=1000, chunk_overlap=200):\n    """\n    Encodes a PDF book into a vector store using OpenAI embeddings.\n\n    Args:\n        path: The path to the PDF file.\n        chunk_size: The desired size of each text chunk.\n        chunk_overlap: The amount of overlap between consecutive chunks.\n\n    Returns:\n        A FAISS vector store containing the encoded book content.\n    """\n\n    # Load PDF documents\n    loader = PyPDFLoader(path)\n    documents = loader.load()\n\n    # Split documents into chunks\n    text_splitter = RecursiveCharacterTextSplitter(\n        chunk_size=chunk_size, chunk_overlap=chunk_overlap, length_function=len\n    )\n    texts = text_splitter.split_documents(documents)\n    cleaned_texts = replace_t_with_space(texts)\n\n    # Create embeddings and vector store\n    embeddings = OpenAIEmbeddings()\n    vectorstore = FAISS.from_documents(cleaned_texts, embeddings)\n\n    return vectorstore, cleaned_texts\n\nvectorstore, cleaned_texts = encode_pdf_and_get_split_documents(path)\n\ndef create_bm25_index(documents: List[Document]) -> BM25Okapi:\n    """\n    Create a BM25 index from the given documents.\n\n    BM25 (Best Matching 25) is a ranking function used in information retrieval.\n    It\'s based on the probabilistic retrieval framework and is an improvement over TF-IDF.\n\n    Args:\n    documents (List[Document]): List of documents to index.\n\n    Returns:\n    BM25Okapi: An index that can be used for BM25 scoring.\n    """\n    # Tokenize each document by splitting on whitespace\n    # This is a simple approach and could be improved with more sophisticated tokenization\n    tokenized_docs = [doc.page_content.split() for doc in documents]\n    return BM25Okapi(tokenized_docs)\n\nbm25 = create_bm25_index(cleaned_texts) # Create BM25 index from the cleaned texts (chunks)\n\ndef fusion_retrieval(vectorstore, bm25, query: str, k: int = 5, alpha: float = 0.5) -> List[Document]:\n    """\n    Perform fusion retrieval combining keyword-based (BM25) and vector-based search.\n\n    Args:\n    vectorstore (VectorStore): The vectorstore containing the documents.\n    bm25 (BM25Okapi): Pre-computed BM25 index.\n    query (str): The query string.\n    k (int): The number of documents to retrieve.\n    alpha (float): The weight for vector search scores (1-alpha will be the weight for BM25 scores).\n\n    Returns:\n    List[Document]: The top k documents based on the combined scores.\n    """\n    \n    epsilon = 1e-8\n\n    # Step 1: Get all documents from the vectorstore\n    all_docs = vectorstore.similarity_search("", k=vectorstore.index.ntotal)\n\n    # Step 2: Perform BM25 search\n    bm25_scores = bm25.get_scores(query.split())\n\n    # Step 3: Perform vector search\n    vector_results = vectorstore.similarity_search_with_score(query, k=len(all_docs))\n    \n    # Step 4: Normalize scores\n    vector_scores = np.array([score for _, score in vector_results])\n    vector_scores = 1 - (vector_scores - np.min(vector_scores)) / (np.max(vector_scores) - np.min(vector_scores) + epsilon)\n\n    bm25_scores = (bm25_scores - np.min(bm25_scores)) / (np.max(bm25_scores) -  np.min(bm25_scores) + epsilon)\n\n    # Step 5: Combine scores\n    combined_scores = alpha * vector_scores + (1 - alpha) * bm25_scores  \n\n    # Step 6: Rank documents\n    sorted_indices = np.argsort(combined_scores)[::-1]\n    \n    # Step 7: Return top k documents\n    return [all_docs[i] for i in sorted_indices[:k]]\n\n# Query\nquery = "What are the impacts of climate change on the environment?"\n\n# Perform fusion retrieval\ntop_docs = fusion_retrieval(vectorstore, bm25, query, k=5, alpha=0.5)\ndocs_content = [doc.page_content for doc in top_docs]\nshow_context(docs_content)', language="python", label="Recovered notebook code")
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
