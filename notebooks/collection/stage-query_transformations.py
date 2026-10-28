# /// script
# dependencies = ["langchain", "langchain-openai", "python-dotenv"]
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

    **[Why Does RAG Miss an Answer That's Right There in Your Documents? (7 min)](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--query-transformations&click=youtube-query-transformations-notebook&target=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3Dz7bAHKWeA3A&retarget=0&text=youtube-query-transformations-notebook)** — the intuition behind this notebook: why the words in a question never quite line up with the words on the page, the three transformations (rewrite, step back, split) that fix the question instead of the index, and the rule that keeps the original question in charge of the answer.

    ---
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Query Transformations for Improved Retrieval in RAG Systems

    ## Overview

    This code implements three query transformation techniques to enhance the retrieval process in Retrieval-Augmented Generation (RAG) systems:

    1. Query Rewriting
    2. Step-back Prompting
    3. Sub-query Decomposition

    Each technique aims to improve the relevance and comprehensiveness of retrieved information by modifying or expanding the original query.

    ## Motivation

    RAG systems often face challenges in retrieving the most relevant information, especially when dealing with complex or ambiguous queries. These query transformation techniques address this issue by reformulating queries to better match relevant documents or to retrieve more comprehensive information.

    ## Key Components

    1. Query Rewriting: Reformulates queries to be more specific and detailed.
    2. Step-back Prompting: Generates broader queries for better context retrieval.
    3. Sub-query Decomposition: Breaks down complex queries into simpler sub-queries.

    ## Method Details

    ### 1. Query Rewriting

    - **Purpose**: To make queries more specific and detailed, improving the likelihood of retrieving relevant information.
    - **Implementation**:
      - Uses a GPT-4 model with a custom prompt template.
      - Takes the original query and reformulates it to be more specific and detailed.

    ### 2. Step-back Prompting

    - **Purpose**: To generate broader, more general queries that can help retrieve relevant background information.
    - **Implementation**:
      - Uses a GPT-4 model with a custom prompt template.
      - Takes the original query and generates a more general "step-back" query.

    ### 3. Sub-query Decomposition

    - **Purpose**: To break down complex queries into simpler sub-queries for more comprehensive information retrieval.
    - **Implementation**:
      - Uses a GPT-4 model with a custom prompt template.
      - Decomposes the original query into 2-4 simpler sub-queries.

    ## Benefits of these Approaches

    1. **Improved Relevance**: Query rewriting helps in retrieving more specific and relevant information.
    2. **Better Context**: Step-back prompting allows for retrieval of broader context and background information.
    3. **Comprehensive Results**: Sub-query decomposition enables retrieval of information that covers different aspects of a complex query.
    4. **Flexibility**: Each technique can be used independently or in combination, depending on the specific use case.

    ## Implementation Details

    - All techniques use OpenAI's GPT-4 model for query transformation.
    - Custom prompt templates are used to guide the model in generating appropriate transformations.
    - The code provides separate functions for each transformation technique, allowing for easy integration into existing RAG systems.

    ## Example Use Case

    The code demonstrates each technique using the example query:
    "What are the impacts of climate change on the environment?"

    - **Query Rewriting** expands this to include specific aspects like temperature changes and biodiversity.
    - **Step-back Prompting** generalizes it to "What are the general effects of climate change?"
    - **Sub-query Decomposition** breaks it down into questions about biodiversity, oceans, weather patterns, and terrestrial environments.

    ## Conclusion

    These query transformation techniques offer powerful ways to enhance the retrieval capabilities of RAG systems. By reformulating queries in various ways, they can significantly improve the relevance, context, and comprehensiveness of retrieved information. These methods are particularly valuable in domains where queries can be complex or multifaceted, such as scientific research, legal analysis, or comprehensive fact-finding tasks.
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
    # packages added via marimo's package management: langchain langchain-openai python-dotenv !pip install langchain langchain-openai python-dotenv
    return


@app.cell
def _():
    from langchain_openai import ChatOpenAI
    from langchain.prompts import PromptTemplate

    import os
    from dotenv import load_dotenv

    # Load environment variables from a .env file
    load_dotenv()

    # Set the OpenAI API key environment variable
    os.environ["OPENAI_API_KEY"] = os.getenv('OPENAI_API_KEY')
    return ChatOpenAI, PromptTemplate


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 1 - Query Rewriting: Reformulating queries to improve retrieval.
    """)
    return


@app.cell
def _(ChatOpenAI, PromptTemplate):
    re_write_llm = ChatOpenAI(temperature=0, model_name="gpt-4o", max_tokens=4000)

    # Create a prompt template for query rewriting
    query_rewrite_template = """You are an AI assistant tasked with reformulating user queries to improve retrieval in a RAG system.
    Given the original query, rewrite it to be more specific, detailed, and likely to retrieve relevant information.

    Original query: {original_query}

    Rewritten query:"""

    query_rewrite_prompt = PromptTemplate(
        input_variables=["original_query"],
        template=query_rewrite_template
    )

    # Create an LLMChain for query rewriting
    query_rewriter = query_rewrite_prompt | re_write_llm

    def rewrite_query(original_query):
        """
        Rewrite the original query to improve retrieval.

        Args:
        original_query (str): The original user query

        Returns:
        str: The rewritten query
        """
        response = query_rewriter.invoke(original_query)
        return response.content

    return (rewrite_query,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Demonstrate on a use case
    """)
    return


@app.cell
def _(rewrite_query):
    # example query over the understanding climate change dataset
    _original_query = 'What are the impacts of climate change on the environment?'
    rewritten_query = rewrite_query(_original_query)
    print('Original query:', _original_query)
    print('\nRewritten query:', rewritten_query)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 2 - Step-back Prompting: Generating broader queries for better context retrieval.
    """)
    return


@app.cell
def _(ChatOpenAI, PromptTemplate):
    step_back_llm = ChatOpenAI(temperature=0, model_name="gpt-4o", max_tokens=4000)


    # Create a prompt template for step-back prompting
    step_back_template = """You are an AI assistant tasked with generating broader, more general queries to improve context retrieval in a RAG system.
    Given the original query, generate a step-back query that is more general and can help retrieve relevant background information.

    Original query: {original_query}

    Step-back query:"""

    step_back_prompt = PromptTemplate(
        input_variables=["original_query"],
        template=step_back_template
    )

    # Create an LLMChain for step-back prompting
    step_back_chain = step_back_prompt | step_back_llm

    def generate_step_back_query(original_query):
        """
        Generate a step-back query to retrieve broader context.

        Args:
        original_query (str): The original user query

        Returns:
        str: The step-back query
        """
        response = step_back_chain.invoke(original_query)
        return response.content

    return (generate_step_back_query,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Demonstrate on a use case
    """)
    return


@app.cell
def _(generate_step_back_query):
    # example query over the understanding climate change dataset
    _original_query = 'What are the impacts of climate change on the environment?'
    step_back_query = generate_step_back_query(_original_query)
    print('Original query:', _original_query)
    print('\nStep-back query:', step_back_query)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 3- Sub-query Decomposition: Breaking complex queries into simpler sub-queries.
    """)
    return


@app.cell
def _(ChatOpenAI, PromptTemplate):
    sub_query_llm = ChatOpenAI(temperature=0, model_name="gpt-4o", max_tokens=4000)

    # Create a prompt template for sub-query decomposition
    subquery_decomposition_template = """You are an AI assistant tasked with breaking down complex queries into simpler sub-queries for a RAG system.
    Given the original query, decompose it into 2-4 simpler sub-queries that, when answered together, would provide a comprehensive response to the original query.

    Original query: {original_query}

    example: What are the impacts of climate change on the environment?

    Sub-queries:
    1. What are the impacts of climate change on biodiversity?
    2. How does climate change affect the oceans?
    3. What are the effects of climate change on agriculture?
    4. What are the impacts of climate change on human health?"""


    subquery_decomposition_prompt = PromptTemplate(
        input_variables=["original_query"],
        template=subquery_decomposition_template
    )

    # Create an LLMChain for sub-query decomposition
    subquery_decomposer_chain = subquery_decomposition_prompt | sub_query_llm

    def decompose_query(original_query: str):
        """
        Decompose the original query into simpler sub-queries.

        Args:
        original_query (str): The original complex query

        Returns:
        List[str]: A list of simpler sub-queries
        """
        response = subquery_decomposer_chain.invoke(original_query).content
        sub_queries = [q.strip() for q in response.split('\n') if q.strip() and not q.strip().startswith('Sub-queries:')]
        return sub_queries

    return (decompose_query,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Demonstrate on a use case
    """)
    return


@app.cell
def _(decompose_query):
    # example query over the understanding climate change dataset
    _original_query = 'What are the impacts of climate change on the environment?'
    sub_queries = decompose_query(_original_query)
    print('\nSub-queries:')
    for i, sub_query in enumerate(sub_queries, 1):
        print(sub_query)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--query-transformations)
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
