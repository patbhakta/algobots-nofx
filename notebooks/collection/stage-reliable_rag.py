# /// script
# dependencies = ["langchain", "langchain-community", "python-dotenv"]
# ///

import marimo

__generated_with = "0.25.1"
app = marimo.App()


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 🎬 Watch it explained

    **[How Do You Know Your RAG Answer Isn't Made Up? (8 min)](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--reliable-rag&click=youtube-reliable-rag-notebook&target=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DoVI2GA8jn7w&retarget=0&text=youtube-reliable-rag-notebook)** — the intuition behind this notebook: grade each retrieved chunk before the model sees it, check the finished answer back against its own sources, then show the exact line it came from so a reader can verify it themselves.

    ---
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Visual Representation

    <img src="../images/reliable_rag.svg" alt="Reliable-RAG" width="300">
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
    # packages added via marimo's package management: langchain langchain-community python-dotenv !pip install langchain langchain-community python-dotenv
    return


@app.cell
def _():
    ### LLMs
    import os
    from dotenv import load_dotenv

    # Load environment variables from '.env' file
    load_dotenv()

    os.environ['GROQ_API_KEY'] = os.getenv('GROQ_API_KEY') # For LLM -- llama-3.1-8b (small) & mixtral-8x7b-32768 (large)
    os.environ['COHERE_API_KEY'] = os.getenv('COHERE_API_KEY') # For embedding
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Create Vectorstore
    """)
    return


@app.cell
def _():
    ### Build Index
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_community.document_loaders import WebBaseLoader
    from langchain_community.vectorstores import Chroma
    from langchain_cohere import CohereEmbeddings

    # Set embeddings
    embedding_model = CohereEmbeddings(model="embed-english-v3.0")

    # Docs to index
    urls = [
        "https://www.deeplearning.ai/the-batch/how-agents-can-improve-llm-performance/?ref=dl-staging-website.ghost.io",
        "https://www.deeplearning.ai/the-batch/agentic-design-patterns-part-2-reflection/?ref=dl-staging-website.ghost.io",
        "https://www.deeplearning.ai/the-batch/agentic-design-patterns-part-3-tool-use/?ref=dl-staging-website.ghost.io",
        "https://www.deeplearning.ai/the-batch/agentic-design-patterns-part-4-planning/?ref=dl-staging-website.ghost.io",
        "https://www.deeplearning.ai/the-batch/agentic-design-patterns-part-5-multi-agent-collaboration/?ref=dl-staging-website.ghost.io"
    ]

    # Load
    docs = [WebBaseLoader(url).load() for url in urls]
    docs_list = [item for sublist in docs for item in sublist]

    # Split
    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=500, chunk_overlap=0
    )
    doc_splits = text_splitter.split_documents(docs_list)

    # Add to vectorstore
    vectorstore = Chroma.from_documents(
        documents=doc_splits,
        collection_name="rag",
        embedding=embedding_model,
    )

    retriever = vectorstore.as_retriever(
                    search_type="similarity",
                    search_kwargs={'k': 4}, # number of documents to retrieve
                )
    return (retriever,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Question
    """)
    return


@app.cell
def _():
    question = "what are the differnt kind of agentic design patterns?"
    return (question,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Retrieve docs
    """)
    return


@app.cell
def _(question, retriever):
    docs_1 = retriever.invoke(question)
    return (docs_1,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Check what our doc looklike
    """)
    return


@app.cell
def _(docs_1):
    print(f"Title: {docs_1[0].metadata['title']}\n\nSource: {docs_1[0].metadata['source']}\n\nContent: {docs_1[0].page_content}\n")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Check document relevancy
    """)
    return


@app.cell
def _():
    from langchain_core.prompts import ChatPromptTemplate
    from pydantic import BaseModel, Field
    from langchain_groq import ChatGroq

    # Data model
    class GradeDocuments(BaseModel):
        """Binary score for relevance check on retrieved documents."""
        binary_score: str = Field(description="Documents are relevant to the question, 'yes' or 'no'")
    _llm = ChatGroq(model='llama-3.1-8b-instant', temperature=0)
    _structured_llm_grader = _llm.with_structured_output(GradeDocuments)
    _system = "You are a grader assessing relevance of a retrieved document to a user question. \n \n    If the document contains keyword(s) or semantic meaning related to the user question, grade it as relevant. \n\n    It does not need to be a stringent test. The goal is to filter out erroneous retrievals. \n\n    Give a binary score 'yes' or 'no' score to indicate whether the document is relevant to the question."
    grade_prompt = ChatPromptTemplate.from_messages([('system', _system), ('human', 'Retrieved document: \n\n {document} \n\n User question: {question}')])
    # LLM with function call
    # Prompt
    retrieval_grader = grade_prompt | _structured_llm_grader
    return BaseModel, ChatGroq, ChatPromptTemplate, Field, retrieval_grader


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Filter out the non-relevant docs
    """)
    return


@app.cell
def _(docs_1, question, retrieval_grader):
    docs_to_use = []
    for doc in docs_1:
        print(doc.page_content, '\n', '-' * 50)
        res = retrieval_grader.invoke({'question': question, 'document': doc.page_content})
        print(res, '\n')
        if res.binary_score == 'yes':
            docs_to_use.append(doc)
    return (docs_to_use,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Generate Result
    """)
    return


@app.cell
def _(ChatGroq, ChatPromptTemplate, docs_to_use, question):
    from langchain_core.output_parsers import StrOutputParser
    _system = 'You are an assistant for question-answering tasks. Answer the question based upon your knowledge. \nUse three-to-five sentences maximum and keep the answer concise.'
    # Prompt
    _prompt = ChatPromptTemplate.from_messages([('system', _system), ('human', 'Retrieved documents: \n\n <docs>{documents}</docs> \n\n User question: <question>{question}</question>')])
    _llm = ChatGroq(model='llama-3.1-8b-instant', temperature=0)

    def format_docs(docs):
        return '\n'.join((f"<doc{i + 1}>:\nTitle:{doc.metadata['title']}\nSource:{doc.metadata['source']}\nContent:{doc.page_content}\n</doc{i + 1}>\n" for i, doc in enumerate(docs)))
    rag_chain = _prompt | _llm | StrOutputParser()
    generation = rag_chain.invoke({'documents': format_docs(docs_to_use), 'question': question})
    # LLM
    # Post-processing
    # Chain
    # Run
    print(generation)
    return format_docs, generation


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Check for Hallucinations
    """)
    return


@app.cell
def _(
    BaseModel,
    ChatGroq,
    ChatPromptTemplate,
    Field,
    docs_to_use,
    format_docs,
    generation,
):
    # Data model
    class GradeHallucinations(BaseModel):
        """Binary score for hallucination present in 'generation' answer."""
        binary_score: str = Field(..., description="Answer is grounded in the facts, 'yes' or 'no'")
    _llm = ChatGroq(model='llama-3.1-8b-instant', temperature=0)
    _structured_llm_grader = _llm.with_structured_output(GradeHallucinations)
    _system = "You are a grader assessing whether an LLM generation is grounded in / supported by a set of retrieved facts. \n \n    Give a binary score 'yes' or 'no'. 'Yes' means that the answer is grounded in / supported by the set of facts."
    hallucination_prompt = ChatPromptTemplate.from_messages([('system', _system), ('human', 'Set of facts: \n\n <facts>{documents}</facts> \n\n LLM generation: <generation>{generation}</generation>')])
    hallucination_grader = hallucination_prompt | _structured_llm_grader
    # LLM with function call
    response = hallucination_grader.invoke({'documents': format_docs(docs_to_use), 'generation': generation})
    # Prompt
    print(response)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Highlight used docs
    """)
    return


@app.cell
def _(
    BaseModel,
    ChatGroq,
    Field,
    docs_to_use,
    format_docs,
    generation,
    question,
):
    from typing import List
    from langchain.output_parsers import PydanticOutputParser
    from langchain_core.prompts import PromptTemplate

    # Data model
    class HighlightDocuments(BaseModel):
        """Return the specific part of a document used for answering the question."""
        id: List[str] = Field(..., description='List of id of docs used to answers the question')
        title: List[str] = Field(..., description='List of titles used to answers the question')
        source: List[str] = Field(..., description='List of sources used to answers the question')
        segment: List[str] = Field(..., description='List of direct segements from used documents that answers the question')
    _llm = ChatGroq(model='mixtral-8x7b-32768', temperature=0)
    parser = PydanticOutputParser(pydantic_object=HighlightDocuments)
    _system = "You are an advanced assistant for document search and retrieval. You are provided with the following:\n1. A question.\n2. A generated answer based on the question.\n3. A set of documents that were referenced in generating the answer.\n\nYour task is to identify and extract the exact inline segments from the provided documents that directly correspond to the content used to \ngenerate the given answer. The extracted segments must be verbatim snippets from the documents, ensuring a word-for-word match with the text \nin the provided documents.\n\nEnsure that:\n- (Important) Each segment is an exact match to a part of the document and is fully contained within the document text.\n- The relevance of each segment to the generated answer is clear and directly supports the answer provided.\n- (Important) If you didn't used the specific document don't mention it.\n\nUsed documents: <docs>{documents}</docs> \n\n User question: <question>{question}</question> \n\n Generated answer: <answer>{generation}</answer>\n\n<format_instruction>\n{format_instructions}\n</format_instruction>\n"
    _prompt = PromptTemplate(template=_system, input_variables=['documents', 'question', 'generation'], partial_variables={'format_instructions': parser.get_format_instructions()})
    doc_lookup = _prompt | _llm | parser
    # LLM
    # parser
    # Prompt
    # Chain
    # Run
    lookup_response = doc_lookup.invoke({'documents': format_docs(docs_to_use), 'question': question, 'generation': generation})
    return (lookup_response,)


@app.cell
def _(lookup_response):
    for id, title, source, segment in zip(lookup_response.id, lookup_response.title, lookup_response.source, lookup_response.segment):
        print(f"ID: {id}\nTitle: {title}\nSource: {source}\nText Segment: {segment}\n")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Text segment in the source

    ![image.png](attachment:image.png)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--reliable-rag)
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
