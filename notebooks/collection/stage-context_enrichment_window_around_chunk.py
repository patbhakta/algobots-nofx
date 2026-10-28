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
    mo.md('# Context Enrichment Window for Document Retrieval\n\n## Overview\n\nThis code implements a context enrichment window technique for document retrieval in a vector database. It enhances the standard retrieval process by adding surrounding context to each retrieved chunk, improving the coherence and completeness of the returned information.\n\n## Motivation\n\nTraditional vector search often returns isolated chunks of text, which may lack necessary context for full understanding. This approach aims to provide a more comprehensive view of the retrieved information by including neighboring text chunks.\n\n## Key Components\n\n1. PDF processing and text chunking\n2. Vector store creation using FAISS and OpenAI embeddings\n3. Custom retrieval function with context window\n4. Comparison between standard and context-enriched retrieval\n\n## Method Details\n\n### Document Preprocessing\n\n1. The PDF is read and converted to a string.\n2. The text is split into chunks with overlap, each chunk tagged with its index.\n\n### Vector Store Creation\n\n1. OpenAI embeddings are used to create vector representations of the chunks.\n2. A FAISS vector store is created from these embeddings.\n\n### Context-Enriched Retrieval\n\n1. The `retrieve_with_context_overlap` function performs the following steps:\n   - Retrieves relevant chunks based on the query\n   - For each relevant chunk, fetches neighboring chunks\n   - Concatenates the chunks, accounting for overlap\n   - Returns the expanded context for each relevant chunk\n\n### Retrieval Comparison\n\nThe notebook includes a section to compare standard retrieval with the context-enriched approach.\n\n## Benefits of this Approach\n\n1. Provides more coherent and contextually rich results\n2. Maintains the advantages of vector search while mitigating its tendency to return isolated text fragments\n3. Allows for flexible adjustment of the context window size\n\n## Conclusion\n\nThis context enrichment window technique offers a promising way to improve the quality of retrieved information in vector-based document search systems. By providing surrounding context, it helps maintain the coherence and completeness of the retrieved information, potentially leading to better understanding and more accurate responses in downstream tasks such as question answering.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('<div style="text-align: center;">\n\n<img src="../images/vector-search-comparison_context_enrichment.svg" alt="context enrichment window" style="width:70%; height:auto;">\n</div>')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('<div style="text-align: center;">\n\n<img src="../images/context_enrichment_window.svg" alt="context enrichment window" style="width:70%; height:auto;">\n</div>')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('# Package Installation and Imports\n\nThe cell below installs all necessary packages required to run this notebook.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define path to PDF')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Read PDF to string')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Function to split text into chunks with metadata of the chunk chronological index')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Split our document accordingly')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Create vector store and retriever')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Function to draw the k<sup>th</sup> chunk (in the original order) from the vector store \n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Check the function')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Function that retrieves from the vector stroe based on semantic similarity and then pads each retrieved chunk with its num_neighbors before and after, taking into account the chunk overlap to construct a meaningful wide window arround it')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Comparing regular retrival and retrival with context window')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### An example that showcases the superiority of additional context window')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--context-enrichment-window-around-chunk)')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# Install required packages\n# SETUP (run separately): !pip install langchain python-dotenv\n\n# Clone the repository to access helper functions and evaluation modules\n# SETUP (run separately): !git clone https://github.com/NirDiamant/RAG_TECHNIQUES.git\nimport sys\nsys.path.append(\'RAG_TECHNIQUES\')\n# If you need to run with the latest data\n# !cp -r RAG_TECHNIQUES/data .\n\nimport os\nimport sys\nfrom dotenv import load_dotenv\nfrom langchain.docstore.document import Document\n\n\n# Original path append replaced for Colab compatibility\nfrom helper_functions import *\nfrom evaluation.evalute_rag import *\n\n# Load environment variables from a .env file\nload_dotenv()\n\n# Set the OpenAI API key environment variable\nos.environ["OPENAI_API_KEY"] = os.getenv(\'OPENAI_API_KEY\')\n\n# Download required data files\nimport os\nos.makedirs(\'data\', exist_ok=True)\n\n# Download the PDF document used in this notebook\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n\npath = "data/Understanding_Climate_Change.pdf"\n\ncontent = read_pdf_to_string(path)\n\ndef split_text_to_chunks_with_indices(text: str, chunk_size: int, chunk_overlap: int) -> List[Document]:\n    chunks = []\n    start = 0\n    while start < len(text):\n        end = start + chunk_size\n        chunk = text[start:end]\n        chunks.append(Document(page_content=chunk, metadata={"index": len(chunks), "text": text}))\n        start += chunk_size - chunk_overlap\n    return chunks\n\nchunks_size = 400\nchunk_overlap = 200\ndocs = split_text_to_chunks_with_indices(content, chunks_size, chunk_overlap)\n\nembeddings = OpenAIEmbeddings()\nvectorstore = FAISS.from_documents(docs, embeddings)\nchunks_query_retriever = vectorstore.as_retriever(search_kwargs={"k": 1})\n\ndef get_chunk_by_index(vectorstore, target_index: int) -> Document:\n    """\n    Retrieve a chunk from the vectorstore based on its index in the metadata.\n    \n    Args:\n    vectorstore (VectorStore): The vectorstore containing the chunks.\n    target_index (int): The index of the chunk to retrieve.\n    \n    Returns:\n    Optional[Document]: The retrieved chunk as a Document object, or None if not found.\n    """\n    # This is a simplified version. In practice, you might need a more efficient method\n    # to retrieve chunks by index, depending on your vectorstore implementation.\n    all_docs = vectorstore.similarity_search("", k=vectorstore.index.ntotal)\n    for doc in all_docs:\n        if doc.metadata.get(\'index\') == target_index:\n            return doc\n    return None\n\nchunk = get_chunk_by_index(vectorstore, 0)\nprint(chunk.page_content)\n\ndef retrieve_with_context_overlap(vectorstore, retriever, query: str, num_neighbors: int = 1, chunk_size: int = 200, chunk_overlap: int = 20) -> List[str]:\n    """\n    Retrieve chunks based on a query, then fetch neighboring chunks and concatenate them, \n    accounting for overlap and correct indexing.\n\n    Args:\n    vectorstore (VectorStore): The vectorstore containing the chunks.\n    retriever: The retriever object to get relevant documents.\n    query (str): The query to search for relevant chunks.\n    num_neighbors (int): The number of chunks to retrieve before and after each relevant chunk.\n    chunk_size (int): The size of each chunk when originally split.\n    chunk_overlap (int): The overlap between chunks when originally split.\n\n    Returns:\n    List[str]: List of concatenated chunk sequences, each centered on a relevant chunk.\n    """\n    relevant_chunks = retriever.get_relevant_documents(query)\n    result_sequences = []\n\n    for chunk in relevant_chunks:\n        current_index = chunk.metadata.get(\'index\')\n        if current_index is None:\n            continue\n\n        # Determine the range of chunks to retrieve\n        start_index = max(0, current_index - num_neighbors)\n        end_index = current_index + num_neighbors + 1  # +1 because range is exclusive at the end\n\n        # Retrieve all chunks in the range\n        neighbor_chunks = []\n        for i in range(start_index, end_index):\n            neighbor_chunk = get_chunk_by_index(vectorstore, i)\n            if neighbor_chunk:\n                neighbor_chunks.append(neighbor_chunk)\n\n        # Sort chunks by their index to ensure correct order\n        neighbor_chunks.sort(key=lambda x: x.metadata.get(\'index\', 0))\n\n        # Concatenate chunks, accounting for overlap\n        concatenated_text = neighbor_chunks[0].page_content\n        for i in range(1, len(neighbor_chunks)):\n            current_chunk = neighbor_chunks[i].page_content\n            overlap_start = max(0, len(concatenated_text) - chunk_overlap)\n            concatenated_text = concatenated_text[:overlap_start] + current_chunk\n\n        result_sequences.append(concatenated_text)\n\n    return result_sequences\n\n# Baseline approach\nquery = "Explain the role of deforestation and fossil fuels in climate change."\nbaseline_chunk = chunks_query_retriever.get_relevant_documents(query\n    ,\n    k=1\n)\n# Focused context enrichment approach\nenriched_chunks = retrieve_with_context_overlap(\n    vectorstore,\n    chunks_query_retriever,\n    query,\n    num_neighbors=1,\n    chunk_size=400,\n    chunk_overlap=200\n)\n\nprint("Baseline Chunk:")\nprint(baseline_chunk[0].page_content)\nprint("\\nEnriched Chunks:")\nprint(enriched_chunks[0])\n\n\ndocument_content = """\nArtificial Intelligence (AI) has a rich history dating back to the mid-20th century. The term "Artificial Intelligence" was coined in 1956 at the Dartmouth Conference, marking the field\'s official beginning.\n\nIn the 1950s and 1960s, AI research focused on symbolic methods and problem-solving. The Logic Theorist, created in 1955 by Allen Newell and Herbert A. Simon, is often considered the first AI program.\n\nThe 1960s saw the development of expert systems, which used predefined rules to solve complex problems. DENDRAL, created in 1965, was one of the first expert systems, designed to analyze chemical compounds.\n\nHowever, the 1970s brought the first "AI Winter," a period of reduced funding and interest in AI research, largely due to overpromised capabilities and underdelivered results.\n\nThe 1980s saw a resurgence with the popularization of expert systems in corporations. The Japanese government\'s Fifth Generation Computer Project also spurred increased investment in AI research globally.\n\nNeural networks gained prominence in the 1980s and 1990s. The backpropagation algorithm, although discovered earlier, became widely used for training multi-layer networks during this time.\n\nThe late 1990s and 2000s marked the rise of machine learning approaches. Support Vector Machines (SVMs) and Random Forests became popular for various classification and regression tasks.\n\nDeep Learning, a subset of machine learning using neural networks with many layers, began to show promising results in the early 2010s. The breakthrough came in 2012 when a deep neural network significantly outperformed other machine learning methods in the ImageNet competition.\n\nSince then, deep learning has revolutionized many AI applications, including image and speech recognition, natural language processing, and game playing. In 2016, Google\'s AlphaGo defeated a world champion Go player, a landmark achievement in AI.\n\nThe current era of AI is characterized by the integration of deep learning with other AI techniques, the development of more efficient and powerful hardware, and the ethical considerations surrounding AI deployment.\n\nTransformers, introduced in 2017, have become a dominant architecture in natural language processing, enabling models like GPT (Generative Pre-trained Transformer) to generate human-like text.\n\nAs AI continues to evolve, new challenges and opportunities arise. Explainable AI, robust and fair machine learning, and artificial general intelligence (AGI) are among the key areas of current and future research in the field.\n"""\n\nchunks_size = 250\nchunk_overlap = 20\ndocument_chunks = split_text_to_chunks_with_indices(document_content, chunks_size, chunk_overlap)\ndocument_vectorstore = FAISS.from_documents(document_chunks, embeddings)\ndocument_retriever = document_vectorstore.as_retriever(search_kwargs={"k": 1})\n\nquery = "When did deep learning become prominent in AI?"\ncontext = document_retriever.get_relevant_documents(query)\ncontext_pages_content = [doc.page_content for doc in context]\n\nprint("Regular retrieval:\\n")\nshow_context(context_pages_content)\n\nsequences = retrieve_with_context_overlap(document_vectorstore, document_retriever, query, num_neighbors=1)\nprint("\\nRetrieval with context enrichment:\\n")\nshow_context(sequences)', language="python", label="Recovered notebook code")
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
