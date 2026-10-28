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
    mo.md("# Hierarchical Indices in Document Retrieval\n\n## Overview\n\nThis code implements a Hierarchical Indexing system for document retrieval, utilizing two levels of encoding: document-level summaries and detailed chunks. This approach aims to improve the efficiency and relevance of information retrieval by first identifying relevant document sections through summaries, then drilling down to specific details within those sections.\n\n## Motivation\n\nTraditional flat indexing methods can struggle with large documents or corpus, potentially missing context or returning irrelevant information. Hierarchical indexing addresses this by creating a two-tier search system, allowing for more efficient and context-aware retrieval.\n\n## Key Components\n\n1. PDF processing and text chunking\n2. Asynchronous document summarization using OpenAI's GPT-4\n3. Vector store creation for both summaries and detailed chunks using FAISS and OpenAI embeddings\n4. Custom hierarchical retrieval function\n\n## Method Details\n\n### Document Preprocessing and Encoding\n\n1. The PDF is loaded and split into documents (likely by page).\n2. Each document is summarized asynchronously using GPT-4.\n3. The original documents are also split into smaller, detailed chunks.\n4. Two separate vector stores are created:\n   - One for document-level summaries\n   - One for detailed chunks\n\n### Asynchronous Processing and Rate Limiting\n\n1. The code uses asynchronous programming (asyncio) to improve efficiency.\n2. Implements batching and exponential backoff to handle API rate limits.\n\n### Hierarchical Retrieval\n\nThe `retrieve_hierarchical` function implements the two-tier search:\n\n1. It first searches the summary vector store to identify relevant document sections.\n2. For each relevant summary, it then searches the detailed chunk vector store, filtering by the corresponding page number.\n3. This approach ensures that detailed information is retrieved only from the most relevant document sections.\n\n## Benefits of this Approach\n\n1. Improved Retrieval Efficiency: By first searching summaries, the system can quickly identify relevant document sections without processing all detailed chunks.\n2. Better Context Preservation: The hierarchical approach helps maintain the broader context of retrieved information.\n3. Scalability: This method is particularly beneficial for large documents or corpus, where flat searching might be inefficient or miss important context.\n4. Flexibility: The system allows for adjusting the number of summaries and chunks retrieved, enabling fine-tuning for different use cases.\n\n## Implementation Details\n\n1. Asynchronous Programming: Utilizes Python's asyncio for efficient I/O operations and API calls.\n2. Rate Limit Handling: Implements batching and exponential backoff to manage API rate limits effectively.\n3. Persistent Storage: Saves the generated vector stores locally to avoid unnecessary recomputation.\n\n## Conclusion\n\nHierarchical indexing represents a sophisticated approach to document retrieval, particularly suitable for large or complex document sets. By leveraging both high-level summaries and detailed chunks, it offers a balance between broad context understanding and specific information retrieval. This method has potential applications in various fields requiring efficient and context-aware information retrieval, such as legal document analysis, academic research, or large-scale content management systems.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('<div style="text-align: center;">\n\n<img src="../images/hierarchical_indices.svg" alt="hierarchical_indices" style="width:50%; height:auto;">\n</div>')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('<div style="text-align: center;">\n\n<img src="../images/hierarchical_indices_example.svg" alt="hierarchical_indices" style="width:100%; height:auto;">\n</div>')
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
    mo.md('### Function to encode to both summary and chunk levels, sharing the page metadata')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Encode the PDF book to both document-level summaries and detailed chunks if the vector stores do not exist\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Retrieve information according to summary level, and then retrieve information from the chunk level vector store and filter according to the summary level pages')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Demonstrate on a use case')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--hierarchical-indices)')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# Install required packages\n# SETUP (run separately): !pip install langchain langchain-openai python-dotenv\n\n# Clone the repository to access helper functions and evaluation modules\n# SETUP (run separately): !git clone https://github.com/NirDiamant/RAG_TECHNIQUES.git\nimport sys\nsys.path.append(\'RAG_TECHNIQUES\')\n# If you need to run with the latest data\n# !cp -r RAG_TECHNIQUES/data .\n\nimport asyncio\nimport os\nimport sys\nfrom dotenv import load_dotenv\nfrom langchain_openai import ChatOpenAI\nfrom langchain.chains.summarize.chain import load_summarize_chain\nfrom langchain.docstore.document import Document\n\n# Original path append replaced for Colab compatibility\nfrom helper_functions import *\nfrom evaluation.evalute_rag import *\nfrom helper_functions import encode_pdf, encode_from_string\n\n# Load environment variables from a .env file\nload_dotenv()\n\n# Set the OpenAI API key environment variable\nos.environ["OPENAI_API_KEY"] = os.getenv(\'OPENAI_API_KEY\')\n\n# Download required data files\nimport os\nos.makedirs(\'data\', exist_ok=True)\n\n# Download the PDF document used in this notebook\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n\npath = "data/Understanding_Climate_Change.pdf"\n\nasync def encode_pdf_hierarchical(path, chunk_size=1000, chunk_overlap=200, is_string=False):\n    """\n    Asynchronously encodes a PDF book into a hierarchical vector store using OpenAI embeddings.\n    Includes rate limit handling with exponential backoff.\n    \n    Args:\n        path: The path to the PDF file.\n        chunk_size: The desired size of each text chunk.\n        chunk_overlap: The amount of overlap between consecutive chunks.\n        \n    Returns:\n        A tuple containing two FAISS vector stores:\n        1. Document-level summaries\n        2. Detailed chunks\n    """\n    \n    # Load PDF documents\n    if not is_string:\n        loader = PyPDFLoader(path)\n        documents = await asyncio.to_thread(loader.load)\n    else:\n        text_splitter = RecursiveCharacterTextSplitter(\n            # Set a really small chunk size, just to show.\n            chunk_size=chunk_size,\n            chunk_overlap=chunk_overlap,\n            length_function=len,\n            is_separator_regex=False,\n        )\n        documents = text_splitter.create_documents([path])\n\n\n    # Create document-level summaries\n    summary_llm = ChatOpenAI(temperature=0, model_name="gpt-4o-mini", max_tokens=4000)\n    summary_chain = load_summarize_chain(summary_llm, chain_type="map_reduce")\n    \n    async def summarize_doc(doc):\n        """\n        Summarizes a single document with rate limit handling.\n        \n        Args:\n            doc: The document to be summarized.\n            \n        Returns:\n            A summarized Document object.\n        """\n        # Retry the summarization with exponential backoff\n        summary_output = await retry_with_exponential_backoff(summary_chain.ainvoke([doc]))\n        summary = summary_output[\'output_text\']\n        return Document(\n            page_content=summary,\n            metadata={"source": path, "page": doc.metadata["page"], "summary": True}\n        )\n\n    # Process documents in smaller batches to avoid rate limits\n    batch_size = 5  # Adjust this based on your rate limits\n    summaries = []\n    for i in range(0, len(documents), batch_size):\n        batch = documents[i:i+batch_size]\n        batch_summaries = await asyncio.gather(*[summarize_doc(doc) for doc in batch])\n        summaries.extend(batch_summaries)\n        await asyncio.sleep(1)  # Short pause between batches\n\n    # Split documents into detailed chunks\n    text_splitter = RecursiveCharacterTextSplitter(\n        chunk_size=chunk_size, chunk_overlap=chunk_overlap, length_function=len\n    )\n    detailed_chunks = await asyncio.to_thread(text_splitter.split_documents, documents)\n\n    # Update metadata for detailed chunks\n    for i, chunk in enumerate(detailed_chunks):\n        chunk.metadata.update({\n            "chunk_id": i,\n            "summary": False,\n            "page": int(chunk.metadata.get("page", 0))\n        })\n\n    # Create embeddings\n    embeddings = OpenAIEmbeddings()\n\n    # Create vector stores asynchronously with rate limit handling\n    async def create_vectorstore(docs):\n        """\n        Creates a vector store from a list of documents with rate limit handling.\n        \n        Args:\n            docs: The list of documents to be embedded.\n            \n        Returns:\n            A FAISS vector store containing the embedded documents.\n        """\n        return await retry_with_exponential_backoff(\n            asyncio.to_thread(FAISS.from_documents, docs, embeddings)\n        )\n\n    # Generate vector stores for summaries and detailed chunks concurrently\n    summary_vectorstore, detailed_vectorstore = await asyncio.gather(\n        create_vectorstore(summaries),\n        create_vectorstore(detailed_chunks)\n    )\n\n    return summary_vectorstore, detailed_vectorstore\n\nif os.path.exists("../vector_stores/summary_store") and os.path.exists("../vector_stores/detailed_store"):\n   embeddings = OpenAIEmbeddings()\n   summary_store = FAISS.load_local("../vector_stores/summary_store", embeddings, allow_dangerous_deserialization=True)\n   detailed_store = FAISS.load_local("../vector_stores/detailed_store", embeddings, allow_dangerous_deserialization=True)\n\nelse:\n    summary_store, detailed_store = await encode_pdf_hierarchical(path)\n    summary_store.save_local("../vector_stores/summary_store")\n    detailed_store.save_local("../vector_stores/detailed_store")\n\ndef retrieve_hierarchical(query, summary_vectorstore, detailed_vectorstore, k_summaries=3, k_chunks=5):\n    """\n    Performs a hierarchical retrieval using the query.\n\n    Args:\n        query: The search query.\n        summary_vectorstore: The vector store containing document summaries.\n        detailed_vectorstore: The vector store containing detailed chunks.\n        k_summaries: The number of top summaries to retrieve.\n        k_chunks: The number of detailed chunks to retrieve per summary.\n\n    Returns:\n        A list of relevant detailed chunks.\n    """\n    \n    # Retrieve top summaries\n    top_summaries = summary_vectorstore.similarity_search(query, k=k_summaries)\n    \n    relevant_chunks = []\n    for summary in top_summaries:\n        # For each summary, retrieve relevant detailed chunks\n        page_number = summary.metadata["page"]\n        page_filter = lambda metadata: metadata["page"] == page_number\n        page_chunks = detailed_vectorstore.similarity_search(\n            query, \n            k=k_chunks, \n            filter=page_filter\n        )\n        relevant_chunks.extend(page_chunks)\n    \n    return relevant_chunks\n\nquery = "What is the greenhouse effect?"\nresults = retrieve_hierarchical(query, summary_store, detailed_store)\n\n# Print results\nfor chunk in results:\n    print(f"Page: {chunk.metadata[\'page\']}")\n    print(f"Content: {chunk.page_content}...")  # Print first 100 characters\n    print("---")', language="python", label="Recovered notebook code")
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
