# /// script
# dependencies = ["faiss-cpu", "llama-index", "python-dotenv"]
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
    # Simple RAG (Retrieval-Augmented Generation) System

    ## Overview

    This code implements a basic Retrieval-Augmented Generation (RAG) system for processing and querying PDF document(s). The system uses a pipeline that encodes the documents and creates nodes. These nodes then can be used to build a vector index to retrieve relevant information.

    ## Key Components

    1. PDF processing and text extraction
    2. Text chunking for manageable processing
    3. Ingestion pipeline creation using FAISS as vector store and OpenAI embeddings
    4. Retriever setup for querying the processed documents
    5. Evaluation of the RAG system

    ## Method Details

    ### Document Preprocessing

    1. The PDF is loaded using [SimpleDirectoryReader](https://docs.llamaindex.ai/en/stable/module_guides/loading/simpledirectoryreader/).
    2. The text is split into [nodes/chunks](https://docs.llamaindex.ai/en/stable/module_guides/loading/documents_and_nodes/) using [SentenceSplitter](https://docs.llamaindex.ai/en/stable/module_guides/loading/node_parsers/modules/#sentencesplitter) with specified chunk size and overlap.

    ### Text Cleaning

    A custom transformation `TextCleaner` is applied to clean the texts. This likely addresses specific formatting issues in the PDF.

    ### Ingestion Pipeline Creation

    1. OpenAI embeddings are used to create vector representations of the text nodes.
    2. A FAISS vector store is created from these embeddings for efficient similarity search.

    ### Retriever Setup

    1. A retriever is configured to fetch the top 2 most relevant chunks for a given query.

    ## Key Features

    1. Modular Design: The ingestion process is encapsulated in a single function for easy reuse.
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
    # packages added via marimo's package management: faiss-cpu llama-index python-dotenv !pip install faiss-cpu llama-index python-dotenv
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
    from typing import List
    from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
    from llama_index.core.ingestion import IngestionPipeline
    from llama_index.core.schema import BaseNode, TransformComponent
    from llama_index.vector_stores.faiss import FaissVectorStore
    from llama_index.core.text_splitter import SentenceSplitter
    from llama_index.embeddings.openai import OpenAIEmbedding
    from llama_index.core import Settings
    import faiss
    import os
    from dotenv import load_dotenv
    EMBED_DIMENSION = 512
    CHUNK_SIZE = 200
    # Original path append replaced for Colab compatibility
    CHUNK_OVERLAP = 50
    load_dotenv()
    os.environ['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY')
    # Chunk settings are way different than langchain examples
    # Beacuse for the chunk length langchain uses length of the string,
    # while llamaindex uses length of the tokens
    # Load environment variables from a .env file
    # Set the OpenAI API key environment variable
    # Set embeddig model on LlamaIndex global settings
    Settings.embed_model = OpenAIEmbedding(model='text-embedding-3-small', dimensions=EMBED_DIMENSION)
    return (
        BaseNode,
        CHUNK_OVERLAP,
        CHUNK_SIZE,
        EMBED_DIMENSION,
        FaissVectorStore,
        IngestionPipeline,
        List,
        SentenceSplitter,
        SimpleDirectoryReader,
        TransformComponent,
        VectorStoreIndex,
        faiss,
        os,
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
    #! wget -O data/q_a.json https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/q_a.json
    subprocess.call(['wget', '-O', 'data/q_a.json', 'https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/q_a.json'])
    return


@app.cell
def _(SimpleDirectoryReader):
    path = "data/"
    node_parser = SimpleDirectoryReader(input_dir=path, required_exts=['.pdf'])
    documents = node_parser.load_data()
    print(documents[0])
    return (documents,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Vector Store
    """)
    return


@app.cell
def _(EMBED_DIMENSION, FaissVectorStore, faiss):
    # Create FaisVectorStore to store embeddings
    faiss_index = faiss.IndexFlatL2(EMBED_DIMENSION)
    vector_store = FaissVectorStore(faiss_index=faiss_index)
    return (vector_store,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Text Cleaner Transformation
    """)
    return


@app.cell
def _(BaseNode, List, TransformComponent):
    class TextCleaner(TransformComponent):
        """
        Transformation to be used within the ingestion pipeline.
        Cleans clutters from texts.
        """
        def __call__(self, nodes, **kwargs) -> List[BaseNode]:

            for node in nodes:
                node.text = node.text.replace('\t', ' ') # Replace tabs with spaces
                node.text = node.text.replace(' \n', ' ') # Replace paragraph seperator with spacaes

            return nodes

    return (TextCleaner,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Ingestion Pipeline
    """)
    return


@app.cell
def _(
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    IngestionPipeline,
    SentenceSplitter,
    TextCleaner,
    vector_store,
):
    text_splitter = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

    # Create a pipeline with defined document transformations and vectorstore
    pipeline = IngestionPipeline(
        transformations=[
            TextCleaner(),
            text_splitter,
        ],
        vector_store=vector_store,
    )
    return (pipeline,)


@app.cell
def _(documents, pipeline):
    # Run pipeline and get generated nodes from the process
    nodes = pipeline.run(documents=documents)
    return (nodes,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Create retriever
    """)
    return


@app.cell
def _(VectorStoreIndex, nodes):
    vector_store_index = VectorStoreIndex(nodes)
    retriever = vector_store_index.as_retriever(similarity_top_k=2)
    return retriever, vector_store_index


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Test retriever
    """)
    return


@app.function
def show_context(context):
    """
    Display the contents of the provided context list.

    Args:
        context (list): A list of context items to be displayed.

    Prints each context item in the list with a heading indicating its position.
    """
    for i, c in enumerate(context):
        print(f"Context {i+1}:")
        print(c.text)
        print("\n")


@app.cell
def _(retriever):
    test_query = "What is the main cause of climate change?"
    context = retriever.retrieve(test_query)
    show_context(context)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Let's see how well does it perform:
    """)
    return


@app.cell
def _():
    import json
    from deepeval import evaluate
    from deepeval.metrics import GEval, FaithfulnessMetric, ContextualRelevancyMetric
    from deepeval.test_case import LLMTestCaseParams
    from evaluation.evalute_rag import create_deep_eval_test_cases

    # Set llm model for evaluation of the question and answers
    LLM_MODEL = "gpt-4o"

    # Define evaluation metrics
    correctness_metric = GEval(
        name="Correctness",
        model=LLM_MODEL,
        evaluation_params=[
            LLMTestCaseParams.EXPECTED_OUTPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT
        ],
        evaluation_steps=[
            "Determine whether the actual output is factually correct based on the expected output."
        ],
    )

    faithfulness_metric = FaithfulnessMetric(
        threshold=0.7,
        model=LLM_MODEL,
        include_reason=False
    )

    relevance_metric = ContextualRelevancyMetric(
        threshold=1,
        model=LLM_MODEL,
        include_reason=True
    )

    def evaluate_rag(query_engine, num_questions: int = 5) -> None:
        """
        Evaluate the RAG system using predefined metrics.

        Args:
            query_engine: Query engine to ask questions and get answers along with retrieved context.
            num_questions (int): Number of questions to evaluate (default: 5).
        """


        # Load questions and answers from JSON file
        q_a_file_name = "data/q_a.json"
        with open(q_a_file_name, "r", encoding="utf-8") as json_file:
            q_a = json.load(json_file)

        questions = [qa["question"] for qa in q_a][:num_questions]
        ground_truth_answers = [qa["answer"] for qa in q_a][:num_questions]
        generated_answers = []
        retrieved_documents = []

        # Generate answers and retrieve documents for each question
        for question in questions:
            response = query_engine.query(question)
            context = [doc.text for doc in response.source_nodes]
            retrieved_documents.append(context)
            generated_answers.append(response.response)

        # Create test cases and evaluate
        test_cases = create_deep_eval_test_cases(questions, ground_truth_answers, generated_answers, retrieved_documents)
        evaluate(
            test_cases=test_cases,
            metrics=[correctness_metric, faithfulness_metric, relevance_metric]
        )

    return (evaluate_rag,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Evaluate results
    """)
    return


@app.cell
def _(evaluate_rag, vector_store_index):
    query_engine  = vector_store_index.as_query_engine(similarity_top_k=2)
    evaluate_rag(query_engine, num_questions=1)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--simple-rag-with-llamaindex)
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
