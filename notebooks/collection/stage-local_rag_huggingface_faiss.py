# /// script
# dependencies = ["accelerate", "faiss-cpu", "huggingface-hub", "langchain", "langchain-community", "langchain-huggingface", "pypdf", "sentence-transformers", "transformers"]
# ///

import marimo

__generated_with = "0.25.1"
app = marimo.App()


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _():
    import subprocess

    return (subprocess,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    [![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/NirDiamant/RAG_Techniques/blob/main/all_rag_techniques/local_rag_huggingface_faiss.ipynb)

    # Fully Local RAG with HuggingFace Embeddings and FAISS 🤗

    ## Overview

    This notebook demonstrates a **fully local, zero-cost RAG pipeline** using open-source models from HuggingFace and FAISS for vector search — no paid API key required. Unlike most RAG implementations that rely on OpenAI, this approach runs entirely on your own machine, making it ideal for privacy-sensitive domains such as banking, healthcare, and legal.

    ## Motivation

    Most RAG tutorials depend on paid APIs (OpenAI, Anthropic, etc.), which creates barriers for:
    - Developers in cost-sensitive or early-stage projects
    - Organizations with strict data privacy requirements
    - Researchers experimenting without API budgets

    This notebook removes those barriers by using:
    - 🤗 **HuggingFace `BAAI/bge-base-en-v1.5`** — top-ranked free embedding model (MTEB leaderboard)
    - ⚡ **FAISS** — fast local vector similarity search by Meta AI
    - 🦜 **LangChain LCEL** — clean, composable pipeline orchestration
    - 🤖 **HuggingFace `Zephyr-7b-beta`** — powerful open-source instruction-tuned LLM

    ## Pipeline

    ```
    PDF Document
         │
         ▼
    [ PDF Loader + Text Splitter ]  →  Chunks
         │
         ▼
    [ HuggingFace Embeddings ]  →  Vectors
         │
         ▼
    [ FAISS Vector Store ]  ←──── Embedded User Query
         │
         ▼
    [ Top-K Retrieved Chunks ]
         │
         ▼
    [ Zephyr-7b LLM + Context ]  →  Grounded Answer
    ```

    ## Key Benefits
    - ✅ **Zero cost** — no OpenAI or paid API needed
    - ✅ **Privacy preserving** — data never leaves your machine
    - ✅ **Production ready** — FAISS index can be saved/loaded for repeated use
    - ✅ **Source attribution** — answers cite which document chunks were used
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Install Required Packages
    """)
    return


@app.cell
def _():
    # Install required packages
    # packages added via marimo's package management: langchain langchain-community langchain-huggingface faiss-cpu sentence-transformers transformers huggingface_hub accelerate pypdf !pip install -qU langchain langchain-community langchain-huggingface faiss-cpu sentence-transformers transformers huggingface_hub accelerate pypdf
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Clone Repository and Download Data
    """)
    return


@app.cell
def _(subprocess):
    # Clone the repository to access helper functions and evaluation modules
    #! git clone https://github.com/NirDiamant/RAG_Techniques.git
    subprocess.call(['git', 'clone', 'https://github.com/NirDiamant/RAG_Techniques.git'])
    import sys
    sys.path.append('RAG_Techniques')

    # Create data directory and download PDF
    import os
    os.makedirs('data', exist_ok=True)

    #! wget -q -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_Techniques/main/data/Understanding_Climate_Change.pdf
    subprocess.call(['wget', '-q', '-O', 'data/Understanding_Climate_Change.pdf', 'https://raw.githubusercontent.com/NirDiamant/RAG_Techniques/main/data/Understanding_Climate_Change.pdf'])

    print('Data downloaded successfully.')
    return (os,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Set Up HuggingFace Token

    Get your **free** token at: https://huggingface.co/settings/tokens
    This is needed to call the HuggingFace Inference API for text generation.
    """)
    return


@app.cell
def _(os):
    from dotenv import load_dotenv
    load_dotenv()
    HF_TOKEN = os.getenv('HUGGINGFACEHUB_API_TOKEN')
    # Load token from .env file, or set it directly below
    assert HF_TOKEN, 'Please set HUGGINGFACEHUB_API_TOKEN. Get your free token at https://huggingface.co/settings/tokens'
    # Option: set directly (not recommended for shared notebooks)
    # os.environ["HUGGINGFACEHUB_API_TOKEN"] = "your_token_here"
    print('HuggingFace token loaded successfully.')
    return (HF_TOKEN,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Import Libraries
    """)
    return


@app.cell
def _():
    import warnings
    warnings.filterwarnings('ignore')

    from langchain_community.document_loaders import PyPDFLoader
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import FAISS
    from langchain_huggingface import HuggingFaceEmbeddings, HuggingFaceEndpoint
    from langchain.prompts import PromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.runnables import RunnablePassthrough, RunnableParallel

    print('Libraries imported successfully.')
    return (
        FAISS,
        HuggingFaceEmbeddings,
        HuggingFaceEndpoint,
        PromptTemplate,
        PyPDFLoader,
        RecursiveCharacterTextSplitter,
        RunnableParallel,
        RunnablePassthrough,
        StrOutputParser,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Define Configuration Parameters
    """)
    return


@app.cell
def _():
    # Path to the document
    PDF_PATH = "data/Understanding_Climate_Change.pdf"

    # Embedding model — top ranked on MTEB leaderboard, runs on CPU
    EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"

    # Open-source instruction-tuned LLM via HuggingFace Inference API
    LLM_REPO_ID = "HuggingFaceH4/zephyr-7b-beta"

    # Chunking parameters — tune based on your document type
    CHUNK_SIZE = 1000    # Characters per chunk
    CHUNK_OVERLAP = 200  # Overlap to preserve context at chunk boundaries

    # Number of chunks to retrieve per query
    TOP_K = 3

    print(f'Config: chunk_size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP}, top_k={TOP_K}')
    print(f'Embedding model: {EMBEDDING_MODEL}')
    print(f'LLM: {LLM_REPO_ID}')
    return (
        CHUNK_OVERLAP,
        CHUNK_SIZE,
        EMBEDDING_MODEL,
        LLM_REPO_ID,
        PDF_PATH,
        TOP_K,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Load and Split the PDF Document
    """)
    return


@app.cell
def _(
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    PDF_PATH,
    PyPDFLoader,
    RecursiveCharacterTextSplitter,
):
    def load_and_split_pdf(path, chunk_size=1000, chunk_overlap=200):
        """
        Load a PDF and split it into overlapping chunks.

        Args:
            path: Path to the PDF file
            chunk_size: Max characters per chunk
            chunk_overlap: Characters shared between adjacent chunks

        Returns:
            List of Document chunks with metadata
        """
        loader = PyPDFLoader(path)
        documents = loader.load()

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
        )
        chunks = text_splitter.split_documents(documents)
        return chunks


    chunks = load_and_split_pdf(PDF_PATH, CHUNK_SIZE, CHUNK_OVERLAP)

    print(f'Loaded PDF: {PDF_PATH}')
    print(f'Total chunks created: {len(chunks)}')
    print(f'\nSample chunk (first 200 chars):')
    print(chunks[0].page_content[:200])
    print(f'\nMetadata: {chunks[0].metadata}')
    return (chunks,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Create HuggingFace Embeddings

    `BAAI/bge-base-en-v1.5` is a top performer on the [MTEB leaderboard](https://huggingface.co/spaces/mteb/leaderboard). It runs efficiently on CPU and produces 768-dimensional embeddings. Setting `normalize_embeddings=True` ensures correct cosine similarity during retrieval.
    """)
    return


@app.cell
def _(EMBEDDING_MODEL, HuggingFaceEmbeddings):
    def create_embeddings(model_name=EMBEDDING_MODEL):
        """
        Initialize HuggingFace embedding model.

        Args:
            model_name: HuggingFace model identifier

        Returns:
            HuggingFaceEmbeddings instance
        """
        return HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": "cpu"},           # Change to 'cuda' if GPU available
            encode_kwargs={"normalize_embeddings": True},  # Required for cosine similarity
        )


    embeddings = create_embeddings()

    # Sanity check
    test_vec = embeddings.embed_query("What causes climate change?")
    print(f'Embedding model loaded: {EMBEDDING_MODEL}')
    print(f'Embedding dimension: {len(test_vec)}')
    return (embeddings,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Build FAISS Vector Store

    FAISS indexes all chunk embeddings locally in memory. For large document sets, save the index to disk to avoid re-embedding on every run.
    """)
    return


@app.cell
def _(FAISS, chunks, embeddings):
    def encode_to_faiss(chunks, embeddings):
        """
        Embed document chunks and build a FAISS vector store.

        Args:
            chunks: List of Document objects
            embeddings: Embedding model instance

        Returns:
            FAISS vector store
        """
        vectorstore = FAISS.from_documents(
            documents=chunks,
            embedding=embeddings,
        )
        return vectorstore


    vectorstore = encode_to_faiss(chunks, embeddings)

    print(f'FAISS index built with {vectorstore.index.ntotal} vectors')

    # Optional: persist index to disk for reuse
    # vectorstore.save_local("faiss_climate_index")
    # vectorstore = FAISS.load_local("faiss_climate_index", embeddings, allow_dangerous_deserialization=True)
    return (vectorstore,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Set Up Retriever and Test It

    Always test the retriever independently before attaching the LLM — this isolates retrieval quality from generation quality.
    """)
    return


@app.cell
def _(TOP_K, vectorstore):
    retriever = vectorstore.as_retriever(search_type='similarity', search_kwargs={'k': TOP_K})
    test_query = 'What are the main causes of climate change?'
    retrieved_docs = retriever.invoke(test_query)
    print(f'Query: "{test_query}"')
    print(f'Retrieved {len(retrieved_docs)} chunks:\n')
    # Test retrieval independently
    for i, _doc in enumerate(retrieved_docs):
        print(f"  Chunk {i + 1} (page {_doc.metadata.get('page', '?')}): {_doc.page_content[:120]}...")
        print()
    return (retriever,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Initialize HuggingFace LLM

    `zephyr-7b-beta` is a strong open-source instruction-tuned model. It runs via the HuggingFace Inference API (free tier available). For fully offline inference, replace with `HuggingFacePipeline` using a locally downloaded model.
    """)
    return


@app.cell
def _(HF_TOKEN, HuggingFaceEndpoint, LLM_REPO_ID):
    llm = HuggingFaceEndpoint(
        repo_id=LLM_REPO_ID,
        task="text-generation",
        max_new_tokens=256,
        temperature=0.1,       # Low temperature for factual, grounded answers
        do_sample=False,
        huggingfacehub_api_token=HF_TOKEN,
    )

    print(f'LLM loaded: {LLM_REPO_ID}')
    return (llm,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Define RAG Prompt Template

    The prompt explicitly instructs the LLM to answer **only** from retrieved context. This is the key hallucination mitigation technique in RAG — if the answer is not in the context, the model should say so rather than fabricate.
    """)
    return


@app.cell
def _(PromptTemplate):
    RAG_PROMPT_TEMPLATE = """\
    You are a helpful assistant. Answer the question using ONLY the context provided below.
    If the answer is not contained in the context, respond with:
    "I don't have enough information in the provided context to answer this question."
    Do not use any prior knowledge or make assumptions.

    Context:
    {context}

    Question: {question}

    Answer:"""

    prompt = PromptTemplate(
        input_variables=["context", "question"],
        template=RAG_PROMPT_TEMPLATE,
    )

    print('Prompt template defined.')
    return (prompt,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Build the Full RAG Chain Using LCEL

    LangChain Expression Language (LCEL) allows composing the full RAG pipeline declaratively. Each component is a runnable that can be chained with `|`.
    """)
    return


@app.cell
def _(RunnablePassthrough, StrOutputParser, llm, prompt, retriever):
    def format_docs(docs):
        """Concatenate retrieved chunks with page source attribution."""
        return "\n\n".join(
            f"[Page {doc.metadata.get('page', '?')}]\n{doc.page_content}"
            for doc in docs
        )


    # Build RAG chain: retrieve → format → prompt → LLM → parse
    rag_chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    print('RAG chain built successfully.')
    return (rag_chain,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Run Queries and Compare with Basic RAG

    We test several queries — including an **out-of-scope question** to verify that the model correctly refuses to answer when context is insufficient.
    """)
    return


@app.cell
def _(rag_chain):
    def ask(question, chain=rag_chain):
        """Run a query through the RAG chain and return a clean answer."""
        raw = chain.invoke(question)
        answer = raw.strip().split('Answer:')[-1].strip()  # Extract only the answer portion (after 'Answer:')
        return answer
    test_queries = ['What are the main causes of climate change?', 'What are the effects of climate change on biodiversity?', 'What solutions are proposed to address climate change?', 'What is the GDP of India in 2024?']
    for _query in test_queries:
        print(f"{'=' * 65}")
        print(f'Q: {_query}')
        print(f"{'-' * 65}")
        _answer = ask(_query)
        print(f'A: {_answer}')
        print()  # Out-of-scope — should be refused
    return (ask,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Return Answers with Source Attribution

    In production RAG systems, showing which source chunks were used builds user trust and enables auditability — especially important in regulated industries like banking and healthcare.
    """)
    return


@app.cell
def _(RunnableParallel, rag_chain, retriever):
    # Chain that returns both the answer and the retrieved source documents
    rag_chain_with_sources = RunnableParallel(answer=rag_chain, sources=retriever)
    _query = 'What are the impacts of rising sea levels?'
    result = rag_chain_with_sources.invoke(_query)
    _answer = result['answer'].strip().split('Answer:')[-1].strip()
    print(f'Q: {_query}\n')
    print(f'A: {_answer}\n')
    print('Sources used:')
    for _doc in result['sources']:
        page = _doc.metadata.get('page', '?')
        preview = _doc.page_content[:100].replace('\n', ' ')
        print(f'  - Page {page}: {preview}...')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Evaluate the RAG System
    """)
    return


@app.cell
def _(ask, rag_chain, retriever):
    # Evaluation using the repo's built-in evaluate_rag helper
    try:
        from evaluation.evalute_rag import evaluate_rag
        evaluate_rag(rag_chain, retriever)
    except ImportError:
        print('Running manual evaluation...\n')  # Fallback: manual evaluation on known questions
        eval_pairs = [{'question': 'What gases are primarily responsible for the greenhouse effect?', 'expected_keywords': ['carbon dioxide', 'CO2', 'methane', 'greenhouse']}, {'question': 'How does deforestation contribute to climate change?', 'expected_keywords': ['carbon', 'forest', 'absorb', 'emissions']}]
        for pair in eval_pairs:
            _answer = ask(pair['question']).lower()
            hits = [kw for kw in pair['expected_keywords'] if kw.lower() in _answer]
            score = len(hits) / len(pair['expected_keywords'])
            print(f"Q: {pair['question']}")
            print(f'   Keyword hit rate: {score:.0%} ({hits})')
            print()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Comparison: Local RAG vs Standard RAG

    | Aspect | Standard RAG (OpenAI) | Local RAG (This Notebook) |
    |--------|----------------------|---------------------------|
    | Cost | ~$0.002/1K tokens | **Free** |
    | Data privacy | Data sent to API | **Stays local** |
    | Setup | API key required | HuggingFace token (free) |
    | Embedding model | text-embedding-ada-002 | BAAI/bge-base-en-v1.5 |
    | LLM | GPT-3.5/4 | Zephyr-7b-beta |
    | Answer quality | Higher (larger model) | Good for most use cases |
    | Offline support | ❌ | ✅ (with local model) |

    ## When to Use This Approach

    - 🏥 **Healthcare / Legal / Finance** — data cannot leave your infrastructure
    - 💰 **Cost-sensitive projects** — no per-token billing
    - 🔬 **Research / prototyping** — iterate freely without API budget concerns
    - 🌍 **Low-connectivity environments** — fully offline with local model variant

    ## Next Steps

    - Replace `HuggingFaceEndpoint` with `HuggingFacePipeline` for **fully offline** inference
    - Try `MMR` (Max Marginal Relevance) retrieval for more **diverse** results
    - Combine with **reranking** (see `reranking.ipynb`) for better precision
    - Scale to millions of docs by migrating from FAISS to **Milvus or Pinecone**
    - Evaluate with **RAGAS** framework for faithfulness and context relevance metrics
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--local-rag-huggingface-faiss)
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
