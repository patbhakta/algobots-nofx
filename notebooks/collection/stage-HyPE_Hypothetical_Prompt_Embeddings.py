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
    mo.md('# Hypothetical Prompt Embeddings (HyPE)\n\n## Overview\n\nThis code implements a Retrieval-Augmented Generation (RAG) system enhanced by Hypothetical Prompt Embeddings (HyPE). Unlike traditional RAG pipelines that struggle with query-document style mismatch, HyPE precomputes hypothetical questions during the indexing phase. This transforms retrieval into a question-question matching problem, eliminating the need for expensive runtime query expansion techniques.\n\n## Key Components of notebook\n\n1. PDF processing and text extraction\n2. Text chunking to maintain coherent information units\n3. **Hypothetical Prompt Embedding Generation** using an LLM to create multiple proxy questions per chunk\n4. Vector store creation using [FAISS](https://engineering.fb.com/2017/03/29/data-infrastructure/faiss-a-library-for-efficient-similarity-search/) and OpenAI embeddings\n5. Retriever setup for querying the processed documents\n6. Evaluation of the RAG system\n\n## Method Details\n\n### Document Preprocessing\n\n1. The PDF is loaded using `PyPDFLoader`.\n2. The text is split into chunks using `RecursiveCharacterTextSplitter` with specified chunk size and overlap.\n\n### Hypothetical Question Generation\n\nInstead of embedding raw text chunks, HyPE **generates multiple hypothetical prompts** for each chunk. These **precomputed questions** simulate user queries, improving alignment with real-world searches. This removes the need for runtime synthetic answer generation needed in techniques like HyDE.\n\n### Vector Store Creation\n\n1. Each hypothetical question is embedded using OpenAI embeddings.\n2. A FAISS vector store is built, associating **each question embedding with its original chunk**.\n3. This approach **stores multiple representations per chunk**, increasing retrieval flexibility.\n\n### Retriever Setup\n\n1. The retriever is optimized for **question-question matching** rather than direct document retrieval.\n2. The FAISS index enables **efficient nearest-neighbor** search over the hypothetical prompt embeddings.\n3. Retrieved chunks provide a **richer and more precise context** for downstream LLM generation.\n\n## Key Features\n\n1. **Precomputed Hypothetical Prompts** – Improves query alignment without runtime overhead.\n2. **Multi-Vector Representation**– Each chunk is indexed multiple times for broader semantic coverage.\n3. **Efficient Retrieval** – FAISS ensures fast similarity search over the enhanced embeddings.\n4. **Modular Design** – The pipeline is easy to adapt for different datasets and retrieval settings. Additionally it\'s compatible with most optimizations like reranking etc.\n\n## Evaluation\n\nHyPE\'s effectiveness is evaluated across multiple datasets, showing:\n\n- Up to 42 percentage points improvement in retrieval precision\n- Up to 45 percentage points improvement in claim recall\n    (See full evaluation results in [preprint](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5139335))\n\n## Benefits of this Approach\n\n1. **Eliminates Query-Time Overhead** – All hypothetical generation is done offline at indexing.\n2. **Enhanced Retrieval Precision** – Better alignment between queries and stored content.\n3. **Scalable & Efficient** – No addinal per-query computational cost; retrieval is as fast as standard RAG.\n4. **Flexible & Extensible** – Can be combined with advanced RAG techniques like reranking.\n\n## Conclusion\n\nHyPE provides a scalable and efficient alternative to traditional RAG systems, overcoming query-document style mismatch while avoiding the computational cost of runtime query expansion. By moving hypothetical prompt generation to indexing, it significantly enhances retrieval precision and efficiency, making it a practical solution for real-world applications.\n\nFor further details, refer to the full paper: [preprint](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5139335)\n\n\n<div style="text-align: center;">\n\n<img src="../images/hype.svg" alt="HyPE" style="width:70%; height:auto;">\n</div>')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('# Package Installation and Imports\n\nThe cell below installs all necessary packages required to run this notebook.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define constants\n\n- `PATH`: path to the data, to be embedded into the RAG pipeline\n\nThis tutorial uses OpenAI endpoint ([avalible models](https://platform.openai.com/docs/pricing)). \n- `LANGUAGE_MODEL_NAME`: The name of the language model to be used. \n- `EMBEDDING_MODEL_NAME`: The name of the embedding model to be used.\n\nThe tutroial uses a `RecursiveCharacterTextSplitter` chunking approach where the chunking length function used is python `len` function. The chunking varables to be tweaked here are:\n- `CHUNK_SIZE`: The minimum length of one chunk\n- `CHUNK_OVERLAP`: The overlap of two consecutive chunks.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Define generation of Hypothetical Prompt Embeddings\n\nThe code block below generates hypothetical questions for each text chunk and embeds them for retrieval.\n\n- An LLM extracts key questions from the input chunk.\n- These questions are embedded using OpenAI's model.\n- The function returns the original chunk and its prompt embeddings later used for retrieval.\n\nTo ensure clean output, extra newlines are removed, and regex parsing can improve list formatting when needed.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define creation and population of FAISS Vector Store\n\nThe code block below builds a FAISS vector store by embedding text chunks in parallel.\n\nWhat happens?\n- Parallel processing – Uses threading to generate embeddings faster.\n- FAISS initialization – Sets up an L2 index for efficient similarity search.\n- Chunk embedding – Each chunk is stored multiple times, once for each generated question embedding.\n- In-memory storage – Uses InMemoryDocstore for fast lookup.\n\nThis ensures efficient retrieval, improving query alignment with precomputed question embeddings.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Encode PDF into a FAISS Vector Store\n\nThe code block below processes a PDF file and stores its content as embeddings for retrieval.\n\nWhat happens?\n- PDF loading – Extracts text from the document.\n- Chunking – Splits text into overlapping segments for better context retention.\n- Preprocessing – Cleans text to improve embedding quality.\n- Vector store creation – Generates embeddings and stores them in FAISS for retrieval.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Create HyPE vector store\n\nNow we process the PDF and store its embeddings.\nThis step initializes the FAISS vector store with the encoded document.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Create retriever\n\nNow we set up the retriever to fetch relevant chunks from the vector store.\n\nRetrieves the top `k=3` most relevant chunks based on query similarity.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Test retriever\n\nNow we test retrieval using a sample query.\n\n- Queries the vector store to find the most relevant chunks.\n- Deduplicates results to remove potentially repeated chunks.\n- Displays the retrieved context for inspection.\n\nThis step verifies that the retriever returns meaningful and diverse information for the given question.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Evaluate results')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--hype-hypothetical-prompt-embeddings)')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# Install required packages\n# SETUP (run separately): !pip install faiss-cpu futures langchain-community python-dotenv tqdm\n\n# Clone the repository to access helper functions and evaluation modules\n# SETUP (run separately): !git clone https://github.com/NirDiamant/RAG_TECHNIQUES.git\nimport sys\nsys.path.append(\'RAG_TECHNIQUES\')\n# If you need to run with the latest data\n# !cp -r RAG_TECHNIQUES/data .\n\nimport os\nimport sys\nimport faiss\nfrom tqdm import tqdm\nfrom dotenv import load_dotenv\nfrom concurrent.futures import ThreadPoolExecutor, as_completed\nfrom langchain_community.docstore.in_memory import InMemoryDocstore\n\n\n# Load environment variables from a .env file\nload_dotenv()\n\n# Set the OpenAI API key environment variable (comment out if not using OpenAI)\nif not os.getenv(\'OPENAI_API_KEY\'):\n    os.environ["OPENAI_API_KEY"] = input("Please enter your OpenAI API key: ")\nelse:\n    os.environ["OPENAI_API_KEY"] = os.getenv(\'OPENAI_API_KEY\')\n\n# Original path append replaced for Colab compatibility\nfrom helper_functions import *\nfrom evaluation.evalute_rag import *\n\n# Download required data files\nimport os\nos.makedirs(\'data\', exist_ok=True)\n\n# Download the PDF document used in this notebook\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n\nPATH = "data/Understanding_Climate_Change.pdf"\nLANGUAGE_MODEL_NAME = "gpt-4o-mini"\nEMBEDDING_MODEL_NAME = "text-embedding-3-small"\nCHUNK_SIZE = 1000\nCHUNK_OVERLAP = 200\n\ndef generate_hypothetical_prompt_embeddings(chunk_text: str):\n    """\n    Uses the LLM to generate multiple hypothetical questions for a single chunk.\n    These questions will be used as \'proxies\' for the chunk during retrieval.\n\n    Parameters:\n    chunk_text (str): Text contents of the chunk\n\n    Returns:\n    chunk_text (str): Text contents of the chunk. This is done to make the \n        multithreading easier\n    hypothetical prompt embeddings (List[float]): A list of embedding vectors\n        generated from the questions\n    """\n    llm = ChatOpenAI(temperature=0, model_name=LANGUAGE_MODEL_NAME)\n    embedding_model = OpenAIEmbeddings(model=EMBEDDING_MODEL_NAME)\n\n    question_gen_prompt = PromptTemplate.from_template(\n        "Analyze the input text and generate essential questions that, when answered, \\\n        capture the main points of the text. Each question should be one line, \\\n        without numbering or prefixes.\\n\\n \\\n        Text:\\n{chunk_text}\\n\\nQuestions:\\n"\n    )\n    question_chain = question_gen_prompt | llm | StrOutputParser()\n\n    # parse questions from response\n    # Notes: \n    # - gpt4o likes to split questions by \\n\\n so we remove one \\n\n    # - for production or if using smaller models from ollama, it\'s beneficial to use regex to parse \n    # things like (un)ordeed lists\n    # r"^\\s*[\\-\\*\\•]|\\s*\\d+\\.\\s*|\\s*[a-zA-Z]\\)\\s*|\\s*\\(\\d+\\)\\s*|\\s*\\([a-zA-Z]\\)\\s*|\\s*\\([ivxlcdm]+\\)\\s*"\n    questions = question_chain.invoke({"chunk_text": chunk_text}).replace("\\n\\n", "\\n").split("\\n")\n    \n    return chunk_text, embedding_model.embed_documents(questions)\n\ndef prepare_vector_store(chunks: List[str]):\n    """\n    Creates and populates a FAISS vector store from a list of text chunks.\n\n    This function processes a list of text chunks in parallel, generating \n    hypothetical prompt embeddings for each chunk.\n    The embeddings are stored in a FAISS index for efficient similarity search.\n\n    Parameters:\n    chunks (List[str]): A list of text chunks to be embedded and stored.\n\n    Returns:\n    FAISS: A FAISS vector store containing the embedded text chunks.\n    """\n\n    # Wait with initialization to see vector lengths\n    vector_store = None  \n\n    with ThreadPoolExecutor() as pool:  \n        # Use threading to speed up generation of prompt embeddings\n        futures = [pool.submit(generate_hypothetical_prompt_embeddings, c) for c in chunks]\n        \n        # Process embeddings as they complete\n        for f in tqdm(as_completed(futures), total=len(chunks)):  \n            \n            chunk, vectors = f.result()  # Retrieve the processed chunk and its embeddings\n            \n            # Initialize the FAISS vector store on the first chunk\n            if vector_store == None:  \n                vector_store = FAISS(\n                    embedding_function=OpenAIEmbeddings(model=EMBEDDING_MODEL_NAME),  # Define embedding model\n                    index=faiss.IndexFlatL2(len(vectors[0])),  # Define an L2 index for similarity search\n                    docstore=InMemoryDocstore(),  # Use in-memory document storage\n                    index_to_docstore_id={}  # Maintain index-to-document mapping\n                )\n            \n            # Pair the chunk\'s content with each generated embedding vector.\n            # Each chunk is inserted multiple times, once for each prompt vector\n            chunks_with_embedding_vectors = [(chunk.page_content, vec) for vec in vectors]\n            \n            # Add embeddings to the store\n            vector_store.add_embeddings(chunks_with_embedding_vectors)  \n\n    return vector_store  # Return the populated vector store\n\ndef encode_pdf(path, chunk_size=1000, chunk_overlap=200):\n    """\n    Encodes a PDF book into a vector store using OpenAI embeddings.\n\n    Args:\n        path: The path to the PDF file.\n        chunk_size: The desired size of each text chunk.\n        chunk_overlap: The amount of overlap between consecutive chunks.\n\n    Returns:\n        A FAISS vector store containing the encoded book content.\n    """\n\n    # Load PDF documents\n    loader = PyPDFLoader(path)\n    documents = loader.load()\n\n    # Split documents into chunks\n    text_splitter = RecursiveCharacterTextSplitter(\n        chunk_size=chunk_size, chunk_overlap=chunk_overlap, length_function=len\n    )\n    texts = text_splitter.split_documents(documents)\n    cleaned_texts = replace_t_with_space(texts)\n\n    vectorstore = prepare_vector_store(cleaned_texts)\n\n    return vectorstore\n\n# Chunk size can be quite large with HyPE as we are not loosing percision with more\n# information. For production, test how exhaustive your model is in generating sufficient \n# amount of questions per chunk. This will mostly depend on your information density.\nchunks_vector_store = encode_pdf(PATH, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)\n\nchunks_query_retriever = chunks_vector_store.as_retriever(search_kwargs={"k": 3})\n\ntest_query = "What is the main cause of climate change?"\ncontext = retrieve_context_per_question(test_query, chunks_query_retriever)\ncontext = list(set(context))\nshow_context(context)\n\nevaluate_rag(chunks_query_retriever)', language="python", label="Recovered notebook code")
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
