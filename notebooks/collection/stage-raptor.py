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
    mo.md("# RAPTOR: Recursive Abstractive Processing and Thematic Organization for Retrieval\n\n## Overview\nRAPTOR is an advanced information retrieval and question-answering system that combines hierarchical document summarization, embedding-based retrieval, and contextual answer generation. It aims to efficiently handle large document collections by creating a multi-level tree of summaries, allowing for both broad and detailed information retrieval.\n\n## Motivation\nTraditional retrieval systems often struggle with large document sets, either missing important details or getting overwhelmed by irrelevant information. RAPTOR addresses this by creating a hierarchical structure of the document collection, allowing it to navigate between high-level concepts and specific details as needed.\n\n## Key Components\n1. **Tree Building**: Creates a hierarchical structure of document summaries.\n2. **Embedding and Clustering**: Organizes documents and summaries based on semantic similarity.\n3. **Vectorstore**: Efficiently stores and retrieves document and summary embeddings.\n4. **Contextual Retriever**: Selects the most relevant information for a given query.\n5. **Answer Generation**: Produces coherent responses based on retrieved information.\n\n## Method Details\n\n### Tree Building\n1. Start with original documents at level 0.\n2. For each level:\n   - Embed the texts using a language model.\n   - Cluster the embeddings (e.g., using Gaussian Mixture Models).\n   - Generate summaries for each cluster.\n   - Use these summaries as the texts for the next level.\n3. Continue until reaching a single summary or a maximum level.\n\n### Embedding and Retrieval\n1. Embed all documents and summaries from all levels of the tree.\n2. Store these embeddings in a vectorstore (e.g., FAISS) for efficient similarity search.\n3. For a given query:\n   - Embed the query.\n   - Retrieve the most similar documents/summaries from the vectorstore.\n\n### Contextual Compression\n1. Take the retrieved documents/summaries.\n2. Use a language model to extract only the most relevant parts for the given query.\n\n### Answer Generation\n1. Combine the relevant parts into a context.\n2. Use a language model to generate an answer based on this context and the original query.\n\n## Benefits of this Approach\n1. **Scalability**: Can handle large document collections by working with summaries at different levels.\n2. **Flexibility**: Capable of providing both high-level overviews and specific details.\n3. **Context-Awareness**: Retrieves information from the most appropriate level of abstraction.\n4. **Efficiency**: Uses embeddings and vectorstore for fast retrieval.\n5. **Traceability**: Maintains links between summaries and original documents, allowing for source verification.\n\n## Conclusion\nRAPTOR represents a significant advancement in information retrieval and question-answering systems. By combining hierarchical summarization with embedding-based retrieval and contextual answer generation, it offers a powerful and flexible approach to handling large document collections. The system's ability to navigate different levels of abstraction allows it to provide relevant and contextually appropriate answers to a wide range of queries.\n\nWhile RAPTOR shows great promise, future work could focus on optimizing the tree-building process, improving summary quality, and enhancing the retrieval mechanism to better handle complex, multi-faceted queries. Additionally, integrating this approach with other AI technologies could lead to even more sophisticated information processing systems.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('<div style="text-align: center;">\n\n<img src="../images/raptor.svg" alt="RAPTOR" style="width:100%; height:auto;">\n</div>')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('# Package Installation and Imports\n\nThe cell below installs all necessary packages required to run this notebook.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define logging, llm and embeddings')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Helper Functions\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### RAPTOR Core Function\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Vectorstore Function\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define tree traversal retrieval')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Create Retriever\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define hierarchical retrieval')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### RAPTOR Query Process (Online Process)')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Example Usage and Visualization\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Define data folder')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Process texts')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Create RAPTOR components instances')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Run a query and observe where it got the data from + results')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--raptor)')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# Install required packages\n# SETUP (run separately): !pip install faiss-cpu langchain langchain-openai matplotlib numpy pandas python-dotenv scikit-learn\n\n# Clone the repository to access helper functions and evaluation modules\n# SETUP (run separately): !git clone https://github.com/NirDiamant/RAG_TECHNIQUES.git\nimport sys\nsys.path.append(\'RAG_TECHNIQUES\')\n# If you need to run with the latest data\n# !cp -r RAG_TECHNIQUES/data .\n\nimport numpy as np\nimport pandas as pd\nfrom typing import List, Dict, Any\nfrom sklearn.mixture import GaussianMixture\nfrom langchain.chains.llm import LLMChain\nfrom langchain.embeddings import OpenAIEmbeddings\nfrom langchain.vectorstores import FAISS\nfrom langchain_openai import ChatOpenAI\nfrom langchain.prompts import ChatPromptTemplate\nfrom langchain.retrievers import ContextualCompressionRetriever\nfrom langchain.retrievers.document_compressors import LLMChainExtractor\nfrom langchain.schema import AIMessage\nfrom langchain.docstore.document import Document\n\nimport matplotlib.pyplot as plt\nimport logging\nimport os\nimport sys\nfrom dotenv import load_dotenv\n\n# Original path append replaced for Colab compatibility\nfrom helper_functions import *\nfrom evaluation.evalute_rag import *\n\n# Load environment variables from a .env file\nload_dotenv()\n\n# Set the OpenAI API key environment variable\nos.environ["OPENAI_API_KEY"] = os.getenv(\'OPENAI_API_KEY\')\n\n# Set up logging\nlogging.basicConfig(level=logging.INFO, format=\'%(asctime)s - %(levelname)s - %(message)s\')\n\nembeddings = OpenAIEmbeddings()\nllm = ChatOpenAI(model_name="gpt-4o-mini")\n\ndef extract_text(item):\n    """Extract text content from either a string or an AIMessage object."""\n    if isinstance(item, AIMessage):\n        return item.content\n    return item\n\ndef embed_texts(texts: List[str]) -> List[List[float]]:\n    """Embed texts using OpenAIEmbeddings."""\n    logging.info(f"Embedding {len(texts)} texts")\n    return embeddings.embed_documents([extract_text(text) for text in texts])\n\ndef perform_clustering(embeddings: np.ndarray, n_clusters: int = 10) -> np.ndarray:\n    """Perform clustering on embeddings using Gaussian Mixture Model."""\n    logging.info(f"Performing clustering with {n_clusters} clusters")\n    gm = GaussianMixture(n_components=n_clusters, random_state=42)\n    return gm.fit_predict(embeddings)\n\ndef summarize_texts(texts: List[str]) -> str:\n    """Summarize a list of texts using OpenAI."""\n    logging.info(f"Summarizing {len(texts)} texts")\n    prompt = ChatPromptTemplate.from_template(\n        "Summarize the following text concisely:\\n\\n{text}"\n    )\n    chain = prompt | llm\n    input_data = {"text": texts}\n    return chain.invoke(input_data)\n\ndef visualize_clusters(embeddings: np.ndarray, labels: np.ndarray, level: int):\n    """Visualize clusters using PCA."""\n    from sklearn.decomposition import PCA\n    pca = PCA(n_components=2)\n    reduced_embeddings = pca.fit_transform(embeddings)\n    \n    plt.figure(figsize=(10, 8))\n    scatter = plt.scatter(reduced_embeddings[:, 0], reduced_embeddings[:, 1], c=labels, cmap=\'viridis\')\n    plt.colorbar(scatter)\n    plt.title(f\'Cluster Visualization - Level {level}\')\n    plt.xlabel(\'First Principal Component\')\n    plt.ylabel(\'Second Principal Component\')\n    plt.show()\n\n\n\ndef build_raptor_tree(texts: List[str], max_levels: int = 3) -> Dict[int, pd.DataFrame]:\n    """Build the RAPTOR tree structure with level metadata and parent-child relationships."""\n    results = {}\n    current_texts = [extract_text(text) for text in texts]\n    current_metadata = [{"level": 0, "origin": "original", "parent_id": None} for _ in texts]\n    \n    for level in range(1, max_levels + 1):\n        logging.info(f"Processing level {level}")\n        \n        embeddings = embed_texts(current_texts)\n        n_clusters = min(10, len(current_texts) // 2)\n        cluster_labels = perform_clustering(np.array(embeddings), n_clusters)\n        \n        df = pd.DataFrame({\n            \'text\': current_texts,\n            \'embedding\': embeddings,\n            \'cluster\': cluster_labels,\n            \'metadata\': current_metadata\n        })\n        \n        results[level-1] = df\n        \n        summaries = []\n        new_metadata = []\n        for cluster in df[\'cluster\'].unique():\n            cluster_docs = df[df[\'cluster\'] == cluster]\n            cluster_texts = cluster_docs[\'text\'].tolist()\n            cluster_metadata = cluster_docs[\'metadata\'].tolist()\n            summary = summarize_texts(cluster_texts)\n            summaries.append(summary)\n            new_metadata.append({\n                "level": level,\n                "origin": f"summary_of_cluster_{cluster}_level_{level-1}",\n                "child_ids": [meta.get(\'id\') for meta in cluster_metadata],\n                "id": f"summary_{level}_{cluster}"\n            })\n        \n        current_texts = summaries\n        current_metadata = new_metadata\n        \n        if len(current_texts) <= 1:\n            results[level] = pd.DataFrame({\n                \'text\': current_texts,\n                \'embedding\': embed_texts(current_texts),\n                \'cluster\': [0],\n                \'metadata\': current_metadata\n            })\n            logging.info(f"Stopping at level {level} as we have only one summary")\n            break\n    \n    return results\n\ndef build_vectorstore(tree_results: Dict[int, pd.DataFrame]) -> FAISS:\n    """Build a FAISS vectorstore from all texts in the RAPTOR tree."""\n    all_texts = []\n    all_embeddings = []\n    all_metadatas = []\n    \n    for level, df in tree_results.items():\n        all_texts.extend([str(text) for text in df[\'text\'].tolist()])\n        all_embeddings.extend([embedding.tolist() if isinstance(embedding, np.ndarray) else embedding for embedding in df[\'embedding\'].tolist()])\n        all_metadatas.extend(df[\'metadata\'].tolist())\n    \n    logging.info(f"Building vectorstore with {len(all_texts)} texts")\n    \n    # Create Document objects manually to ensure correct types\n    documents = [Document(page_content=str(text), metadata=metadata) \n                 for text, metadata in zip(all_texts, all_metadatas)]\n    \n    return FAISS.from_documents(documents, embeddings)\n\ndef tree_traversal_retrieval(query: str, vectorstore: FAISS, k: int = 3) -> List[Document]:\n    """Perform tree traversal retrieval."""\n    query_embedding = embeddings.embed_query(query)\n    \n    def retrieve_level(level: int, parent_ids: List[str] = None) -> List[Document]:\n        if parent_ids:\n            docs = vectorstore.similarity_search_by_vector_with_relevance_scores(\n                query_embedding,\n                k=k,\n                filter=lambda meta: meta[\'level\'] == level and meta[\'id\'] in parent_ids\n            )\n        else:\n            docs = vectorstore.similarity_search_by_vector_with_relevance_scores(\n                query_embedding,\n                k=k,\n                filter=lambda meta: meta[\'level\'] == level\n            )\n        \n        if not docs or level == 0:\n            return docs\n        \n        child_ids = [doc.metadata.get(\'child_ids\', []) for doc, _ in docs]\n        child_ids = [item for sublist in child_ids for item in sublist]  # Flatten the list\n        \n        child_docs = retrieve_level(level - 1, child_ids)\n        return docs + child_docs\n    \n    max_level = max(doc.metadata[\'level\'] for doc in vectorstore.docstore.values())\n    return retrieve_level(max_level)\n\ndef create_retriever(vectorstore: FAISS) -> ContextualCompressionRetriever:\n    """Create a retriever with contextual compression."""\n    logging.info("Creating contextual compression retriever")\n    base_retriever = vectorstore.as_retriever()\n    \n    prompt = ChatPromptTemplate.from_template(\n        "Given the following context and question, extract only the relevant information for answering the question:\\n\\n"\n        "Context: {context}\\n"\n        "Question: {question}\\n\\n"\n        "Relevant Information:"\n    )\n    \n    extractor = LLMChainExtractor.from_llm(llm, prompt=prompt)\n    \n    return ContextualCompressionRetriever(\n        base_compressor=extractor,\n        base_retriever=base_retriever\n    )\n\ndef hierarchical_retrieval(query: str, retriever: ContextualCompressionRetriever, max_level: int) -> List[Document]:\n    """Perform hierarchical retrieval starting from the highest level, handling potential None values."""\n    all_retrieved_docs = []\n    \n    for level in range(max_level, -1, -1):\n        # Retrieve documents from the current level\n        level_docs = retriever.get_relevant_documents(\n            query,\n            filter=lambda meta: meta[\'level\'] == level\n        )\n        all_retrieved_docs.extend(level_docs)\n        \n        # If we\'ve found documents, retrieve their children from the next level down\n        if level_docs and level > 0:\n            child_ids = [doc.metadata.get(\'child_ids\', []) for doc in level_docs]\n            child_ids = [item for sublist in child_ids for item in sublist if item is not None]  # Flatten and filter None\n            \n            if child_ids:  # Only modify query if there are valid child IDs\n                child_query = f" AND id:({\' OR \'.join(str(id) for id in child_ids)})"\n                query += child_query\n    \n    return all_retrieved_docs\n\ndef raptor_query(query: str, retriever: ContextualCompressionRetriever, max_level: int) -> Dict[str, Any]:\n    """Process a query using the RAPTOR system with hierarchical retrieval."""\n    logging.info(f"Processing query: {query}")\n    \n    relevant_docs = hierarchical_retrieval(query, retriever, max_level)\n    \n    doc_details = []\n    for i, doc in enumerate(relevant_docs, 1):\n        doc_details.append({\n            "index": i,\n            "content": doc.page_content,\n            "metadata": doc.metadata,\n            "level": doc.metadata.get(\'level\', \'Unknown\'),\n            "similarity_score": doc.metadata.get(\'score\', \'N/A\')\n        })\n    \n    context = "\\n\\n".join([doc.page_content for doc in relevant_docs])\n    \n    prompt = ChatPromptTemplate.from_template(\n        "Given the following context, please answer the question:\\n\\n"\n        "Context: {context}\\n\\n"\n        "Question: {question}\\n\\n"\n        "Answer:"\n    )\n    chain = LLMChain(llm=llm, prompt=prompt)\n    answer = chain.run(context=context, question=query)\n    \n    logging.info("Query processing completed")\n    \n    result = {\n        "query": query,\n        "retrieved_documents": doc_details,\n        "num_docs_retrieved": len(relevant_docs),\n        "context_used": context,\n        "answer": answer,\n        "model_used": llm.model_name,\n    }\n    \n    return result\n\n\ndef print_query_details(result: Dict[str, Any]):\n    """Print detailed information about the query process, including tree level metadata."""\n    print(f"Query: {result[\'query\']}")\n    print(f"\\nNumber of documents retrieved: {result[\'num_docs_retrieved\']}")\n    print(f"\\nRetrieved Documents:")\n    for doc in result[\'retrieved_documents\']:\n        print(f"  Document {doc[\'index\']}:")\n        print(f"    Content: {doc[\'content\'][:100]}...")  # Show first 100 characters\n        print(f"    Similarity Score: {doc[\'similarity_score\']}")\n        print(f"    Tree Level: {doc[\'metadata\'].get(\'level\', \'Unknown\')}")\n        print(f"    Origin: {doc[\'metadata\'].get(\'origin\', \'Unknown\')}")\n        if \'child_docs\' in doc[\'metadata\']:\n            print(f"    Number of Child Documents: {len(doc[\'metadata\'][\'child_docs\'])}")\n        print()\n    \n    print(f"\\nContext used for answer generation:")\n    print(result[\'context_used\'])\n    \n    print(f"\\nGenerated Answer:")\n    print(result[\'answer\'])\n    \n    print(f"\\nModel Used: {result[\'model_used\']}")\n\n# Download required data files\nimport os\nos.makedirs(\'data\', exist_ok=True)\n\n# Download the PDF document used in this notebook\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n\npath = "data/Understanding_Climate_Change.pdf"\n\nloader = PyPDFLoader(path)\ndocuments = loader.load()\ntexts = [doc.page_content for doc in documents]\n\n# Build the RAPTOR tree\ntree_results = build_raptor_tree(texts)\n\n# Build vectorstore\nvectorstore = build_vectorstore(tree_results)\n\n# Create retriever\nretriever = create_retriever(vectorstore)\n\n# Run the pipeline\nmax_level = 3  # Adjust based on your tree depth\nquery = "What is the greenhouse effect?"\nresult = raptor_query(query, retriever, max_level)\nprint_query_details(result)', language="python", label="Recovered notebook code")
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
