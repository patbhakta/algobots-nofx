# /// script
# dependencies = ["faiss-cpu", "llama-index", "pandas", "python-dotenv"]
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
    # Simple RAG (Retrieval-Augmented Generation) System for CSV Files

    ## Overview

    This code implements a basic Retrieval-Augmented Generation (RAG) system for processing and querying CSV documents. The system encodes the document content into a vector store, which can then be queried to retrieve relevant information.

    # CSV File Structure and Use Case
    The CSV file contains dummy customer data, comprising various attributes like first name, last name, company, etc. This dataset will be utilized for a RAG use case, facilitating the creation of a customer information Q&A system.

    ## Key Components

    1. Loading and spliting csv files.
    2. Vector store creation using [FAISS](https://engineering.fb.com/2017/03/29/data-infrastructure/faiss-a-library-for-efficient-similarity-search/) and OpenAI embeddings
    3. Query engine setup for querying the processed documents
    4. Creating a question and answer over the csv data.

    ## Method Details

    ### Document Preprocessing

    1. The csv is loaded using LlamaIndex's [PagedCSVReader](https://docs.llamaindex.ai/en/stable/api_reference/readers/file/#llama_index.readers.file.PagedCSVReader)
    2. This reader converts each row into a LlamaIndex Document along with the respective column names of the table. No further splitting applied.

    ### Vector Store Creation

    1. OpenAI embeddings are used to create vector representations of the text chunks.
    2. A FAISS vector store is created from these embeddings for efficient similarity search.

    ### Query Engine Setup

    1. A query engine is configured to fetch the most relevant chunks for a given query then answer the question.

    ## Benefits of this Approach

    1. Scalability: Can handle large documents by processing them in chunks.
    2. Flexibility: Easy to adjust parameters like chunk size and number of retrieved results.
    3. Efficiency: Utilizes FAISS for fast similarity search in high-dimensional spaces.
    4. Integration with Advanced NLP: Uses OpenAI embeddings for state-of-the-art text representation.

    ## Conclusion

    This simple RAG system provides a solid foundation for building more complex information retrieval and question-answering systems. By encoding document content into a searchable vector store, it enables efficient retrieval of relevant information in response to queries. This approach is particularly useful for applications requiring quick access to specific information within a CSV file.
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
    # packages added via marimo's package management: faiss-cpu llama-index pandas python-dotenv !pip install faiss-cpu llama-index pandas python-dotenv
    return


@app.cell
def _():
    from llama_index.core.readers import SimpleDirectoryReader
    from llama_index.core import Settings
    from llama_index.llms.openai import OpenAI
    from llama_index.embeddings.openai import OpenAIEmbedding
    from llama_index.readers.file import PagedCSVReader
    from llama_index.vector_stores.faiss import FaissVectorStore
    from llama_index.core.ingestion import IngestionPipeline
    from llama_index.core import VectorStoreIndex
    import faiss
    import os
    import pandas as pd
    from dotenv import load_dotenv


    # Load environment variables from a .env file
    load_dotenv()

    # Set the OpenAI API key environment variable
    os.environ["OPENAI_API_KEY"] = os.getenv('OPENAI_API_KEY')


    # Llamaindex global settings for llm and embeddings
    EMBED_DIMENSION=512
    Settings.llm = OpenAI(model="gpt-3.5-turbo")
    Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small", dimensions=EMBED_DIMENSION)
    return (
        EMBED_DIMENSION,
        FaissVectorStore,
        IngestionPipeline,
        PagedCSVReader,
        SimpleDirectoryReader,
        VectorStoreIndex,
        faiss,
        os,
        pd,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### CSV File Structure and Use Case
    The CSV file contains dummy customer data, comprising various attributes like first name, last name, company, etc. This dataset will be utilized for a RAG use case, facilitating the creation of a customer information Q&A system.
    """)
    return


@app.cell
def _(os, subprocess):
    # Download required data files
    os.makedirs('data', exist_ok=True)
    subprocess.call(['wget', '-O', 'data/Understanding_Climate_Change.pdf', 'https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf'])
    # Download the PDF document used in this notebook
    #! wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf
    #! wget -O data/customers-100.csv https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/customers-100.csv
    subprocess.call(['wget', '-O', 'data/customers-100.csv', 'https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/customers-100.csv'])
    return


@app.cell
def _(pd):
    file_path = ('data/customers-100.csv') # insert the path of the csv file
    data = pd.read_csv(file_path)

    # Preview the csv file
    data.head()
    return (file_path,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Vector Store
    """)
    return


@app.cell
def _(EMBED_DIMENSION, FaissVectorStore, faiss):
    # Create FaisVectorStore to store embeddings
    fais_index = faiss.IndexFlatL2(EMBED_DIMENSION)
    vector_store = FaissVectorStore(faiss_index=fais_index)
    return (vector_store,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Load and Process CSV Data as Document
    """)
    return


@app.cell
def _(PagedCSVReader, SimpleDirectoryReader, file_path):
    csv_reader = PagedCSVReader()

    reader = SimpleDirectoryReader(
        input_files=[file_path],
        file_extractor= {".csv": csv_reader}
        )

    docs = reader.load_data()
    return (docs,)


@app.cell
def _(docs):
    # Check a sample chunk
    print(docs[0].text)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Ingestion Pipeline
    """)
    return


@app.cell
def _(IngestionPipeline, docs, vector_store):
    pipeline = IngestionPipeline(
        vector_store=vector_store,
        documents=docs
    )

    nodes = pipeline.run()
    return (nodes,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Create Query Engine
    """)
    return


@app.cell
def _(VectorStoreIndex, nodes):
    vector_store_index = VectorStoreIndex(nodes)
    query_engine = vector_store_index.as_query_engine(similarity_top_k=2)
    return (query_engine,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Query the rag bot with a question based on the CSV data
    """)
    return


@app.cell
def _(query_engine):
    response = query_engine.query("which company does sheryl Baxter work for?")
    response.response
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--simple-csv-rag-with-llamaindex)
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
