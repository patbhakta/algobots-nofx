# /// script
# dependencies = ["deepeval", "faiss-cpu", "langchain-community", "langchain-openai", "pymupdf", "pypdf", "python-dotenv", "rank-bm25"]
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
    ## 🎬 Watch this notebook explained

    <a href="https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--simple-rag&click=youtube-simple-rag-thumb&target=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DrRCfl4aRYJs&retarget=0&text=youtube-simple-rag-thumb"><img src="https://img.youtube.com/vi/rRCfl4aRYJs/maxresdefault.jpg" alt="RAG Explained: Why AI Gets Your Own Documents Wrong" width="520"></a>

    **[RAG Explained: Why AI Gets Your Own Documents Wrong](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--simple-rag&click=youtube-simple-rag-title&target=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DrRCfl4aRYJs&retarget=0&text=youtube-simple-rag-title)** — the intuition behind every cell below, in 7 minutes: why documents get cut into *overlapping* chunks, what "meaning space" actually is, how a search by meaning finds a passage that shares almost no words with your question, and where simple RAG starts to break.

    ▶ **[Watch on YouTube](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--simple-rag&click=youtube-simple-rag-watch&target=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DrRCfl4aRYJs&retarget=0&text=youtube-simple-rag-watch)**

    ---
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Simple RAG (Retrieval-Augmented Generation) System

    ## Overview

    This code implements a basic Retrieval-Augmented Generation (RAG) system for processing and querying PDF documents. The system encodes the document content into a vector store, which can then be queried to retrieve relevant information.

    ## Key Components

    1. PDF processing and text extraction
    2. Text chunking for manageable processing
    3. Vector store creation using [FAISS](https://engineering.fb.com/2017/03/29/data-infrastructure/faiss-a-library-for-efficient-similarity-search/) and OpenAI embeddings
    4. Retriever setup for querying the processed documents
    5. Evaluation of the RAG system

    ## Method Details

    ### Document Preprocessing

    1. The PDF is loaded using PyPDFLoader.
    2. The text is split into chunks using RecursiveCharacterTextSplitter with specified chunk size and overlap.

    ### Text Cleaning

    A custom function `replace_t_with_space` is applied to clean the text chunks. This likely addresses specific formatting issues in the PDF.

    ### Vector Store Creation

    1. OpenAI embeddings are used to create vector representations of the text chunks.
    2. A FAISS vector store is created from these embeddings for efficient similarity search.

    ### Retriever Setup

    1. A retriever is configured to fetch the top 2 most relevant chunks for a given query.

    ### Encoding Function

    The `encode_pdf` function encapsulates the entire process of loading, chunking, cleaning, and encoding the PDF into a vector store.

    ## Key Features

    1. Modular Design: The encoding process is encapsulated in a single function for easy reuse.
    2. Configurable Chunking: Allows adjustment of chunk size and overlap.
    3. Efficient Retrieval: Uses FAISS for fast similarity search.
    4. Evaluation: Includes a function to evaluate the RAG system's performance.

    ## Usage Example

    The code includes a test query: "What is the main cause of climate change?". This demonstrates how to use the retriever to fetch relevant context from the processed document.

    ## Evaluation

    The system includes an `evaluate_rag` function to assess the performance of the retriever, though the specific metrics used are not detailed in the provided code.

    ## Benefits of this Approach

    1. Scalability: Can handle large documents by processing them in chunks.
    2. Flexibility: Easy to adjust parameters like chunk size and number of retrieved results.
    3. Efficiency: Utilizes FAISS for fast similarity search in high-dimensional spaces.
    4. Integration with Advanced NLP: Uses OpenAI embeddings for state-of-the-art text representation.

    ## Conclusion

    This simple RAG system provides a solid foundation for building more complex information retrieval and question-answering systems. By encoding document content into a searchable vector store, it enables efficient retrieval of relevant information in response to queries. This approach is particularly useful for applications requiring quick access to specific information within large documents or document collections.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Package Installation and Imports

    The cell below installs all necessary packages required to run this notebook.
    """)
    return


@app.cell
def _():
    # Install required packages
    # packages added via marimo's package management: pypdf==5.6.0 !pip install pypdf==5.6.0
    # packages added via marimo's package management: PyMuPDF==1.26.1 !pip install PyMuPDF==1.26.1
    # packages added via marimo's package management: python-dotenv==1.1.0 !pip install python-dotenv==1.1.0
    # packages added via marimo's package management: langchain-community==0.3.25 !pip install langchain-community==0.3.25
    # packages added via marimo's package management: langchain_openai==0.3.23 !pip install langchain_openai==0.3.23
    # packages added via marimo's package management: rank_bm25==0.2.2 !pip install rank_bm25==0.2.2
    # packages added via marimo's package management: faiss-cpu==1.11.0 !pip install faiss-cpu==1.11.0
    # packages added via marimo's package management: deepeval==3.1.0 !pip install deepeval==3.1.0
    return


@app.cell
def _(subprocess):
    # Clone the repository to access helper functions and evaluation modules
    #! git clone https://github.com/NirDiamant/RAG_TECHNIQUES.git
    subprocess.call(['git', 'clone', 'https://github.com/NirDiamant/RAG_TECHNIQUES.git'])
    import sys
    sys.path.append('RAG_TECHNIQUES')

    # If you need to run with the latest data
    # !cp -r RAG_TECHNIQUES/data .
    return


@app.cell
def _():
    import os
    from dotenv import load_dotenv
    from google.colab import userdata
    load_dotenv()
    if not userdata.get('OPENAI_API_KEY'):
        os.environ['OPENAI_API_KEY'] = input('Please enter your OpenAI API key: ')
    else:
    # Load environment variables from a .env file
        os.environ['OPENAI_API_KEY'] = userdata.get('OPENAI_API_KEY')
    from langchain.document_loaders import PyPDFLoader
    # Set the OpenAI API key environment variable (comment out if not using OpenAI)
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from helper_functions import EmbeddingProvider, retrieve_context_per_question, replace_t_with_space, get_langchain_embedding_provider, show_context
    from evaluation.evalute_rag import evaluate_rag
    # Original path append replaced for Colab compatibility
    from langchain.vectorstores import FAISS

    return (
        EmbeddingProvider,
        FAISS,
        PyPDFLoader,
        RecursiveCharacterTextSplitter,
        evaluate_rag,
        get_langchain_embedding_provider,
        os,
        replace_t_with_space,
        retrieve_context_per_question,
        show_context,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Read Docs
    """)
    return


@app.cell
def _(os, subprocess):
    # Download required data files
    os.makedirs('data', exist_ok=True)
    subprocess.call(['wget', '-O', 'data/Understanding_Climate_Change.pdf', 'https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf'])
    # Download the PDF document used in this notebook
    #! wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf
    subprocess.call(['wget', '-O', 'data/Understanding_Climate_Change.pdf', 'https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf'])
    return


@app.cell
def _():
    path = "data/Understanding_Climate_Change.pdf"
    return (path,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Encode document
    """)
    return


@app.cell
def _(
    EmbeddingProvider,
    FAISS,
    PyPDFLoader,
    RecursiveCharacterTextSplitter,
    get_langchain_embedding_provider,
    replace_t_with_space,
):
    def encode_pdf(path, chunk_size=1000, chunk_overlap=200):
        """
        Encodes a PDF book into a vector store using OpenAI embeddings.

        Args:
            path: The path to the PDF file.
            chunk_size: The desired size of each text chunk.
            chunk_overlap: The amount of overlap between consecutive chunks.

        Returns:
            A FAISS vector store containing the encoded book content.
        """

        # Load PDF documents
        loader = PyPDFLoader(path)
        documents = loader.load()

        # Split documents into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap, length_function=len
        )
        texts = text_splitter.split_documents(documents)
        cleaned_texts = replace_t_with_space(texts)

        # Create embeddings (Tested with OpenAI and Amazon Bedrock)
        embeddings = get_langchain_embedding_provider(EmbeddingProvider.OPENAI)
        #embeddings = get_langchain_embedding_provider(EmbeddingProvider.AMAZON_BEDROCK)

        # Create vector store
        vectorstore = FAISS.from_documents(cleaned_texts, embeddings)

        return vectorstore

    return (encode_pdf,)


@app.cell
def _(encode_pdf, path):
    chunks_vector_store = encode_pdf(path, chunk_size=1000, chunk_overlap=200)
    return (chunks_vector_store,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Create retriever
    """)
    return


@app.cell
def _(chunks_vector_store):
    chunks_query_retriever = chunks_vector_store.as_retriever(search_kwargs={"k": 2})
    return (chunks_query_retriever,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Test retriever
    """)
    return


@app.cell
def _(chunks_query_retriever, retrieve_context_per_question, show_context):
    test_query = "What is the main cause of climate change?"
    context = retrieve_context_per_question(test_query, chunks_query_retriever)
    show_context(context)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Evaluate results
    """)
    return


@app.cell
def _(chunks_query_retriever, evaluate_rag):
    #Note - this currently works with OPENAI only
    evaluate_rag(chunks_query_retriever)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---

    ### 🎬 Now the part the code doesn't show

    You just ran a retriever that answers from your own document. The 7-minute explainer covers *why* it works: why chunks **overlap**, what "meaning space" actually is, and the chunk-boundary failure that quietly breaks retrieval setups that look perfectly healthy from the outside.

    ▶ **[RAG Explained: Why AI Gets Your Own Documents Wrong](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--simple-rag&click=youtube-simple-rag-outro&target=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DrRCfl4aRYJs&retarget=0&text=youtube-simple-rag-outro)**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--simple-rag)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""

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
