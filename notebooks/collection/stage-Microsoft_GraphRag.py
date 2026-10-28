# /// script
# dependencies = ["beautifulsoup4", "openai", "python-dotenv", "pyyaml"]
# ///

import marimo

__generated_with = "0.25.1"
app = marimo.App()


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(subprocess):
    #! [](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--microsoft-graphrag)
    subprocess.call(['[](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--microsoft-graphrag)'])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Microsoft GraphRAG: Enhancing Retrieval-Augmented Generation with Knowledge Graphs


    ## Overview


    Microsoft GraphRAG is an advanced Retrieval-Augmented Generation (RAG) system that integrates knowledge graphs to improve the performance of large language models (LLMs). Developed by Microsoft Research, GraphRAG addresses limitations in traditional RAG approaches by using LLM-generated knowledge graphs to enhance document analysis and improve response quality.

    ## Motivation


    Traditional RAG systems often struggle with complex queries that require synthesizing information from disparate sources. GraphRAG aims to:
    Connect related information across datasets.
    Enhance understanding of semantic concepts.
    Improve performance on global sensemaking tasks.

    ## Key Components

    Knowledge Graph Generation: Constructs graphs with entities as nodes and relationships as edges.
    Community Detection: Identifies clusters of related entities within the graph.
    Summarization: Generates summaries for each community to provide context for LLMs.
    Query Processing: Uses these summaries to enhance the LLM's ability to answer complex questions.
    ## Method Details

    Indexing Stage


    Text Chunking: Splits source texts into manageable chunks.
    Element Extraction: Uses LLMs to identify entities and relationships.
    Graph Construction: Builds a graph from the extracted elements.
    Community Detection: Applies algorithms like Leiden to find communities.
    Community Summarization: Creates summaries for each community.

    Query Stage


    Local Answer Generation: Uses community summaries to generate preliminary answers.
    Global Answer Synthesis: Combines local answers to form a comprehensive response.

    ## Benefits of GraphRAG
    GraphRAG is a powerful tool that addresses some of the key limitations of the baseline RAG model. Unlike the standard RAG model, GraphRAG excels at identifying connections between disparate pieces of information and drawing insights from them. This makes it an ideal choice for users who need to extract insights from large data collections or documents that are difficult to summarize. By leveraging its advanced graph-based architecture, GraphRAG is able to provide a holistic understanding of complex semantic concepts, making it an invaluable tool for anyone who needs to find information quickly and accurately. Whether you're a researcher, analyst, or just someone who needs to stay informed, GraphRAG can help you connect the dots and uncover new insights.

    ## Conclusion

    Microsoft GraphRAG represents a significant step forward in retrieval-augmented generation, particularly for tasks requiring a global understanding of datasets. By incorporating knowledge graphs, it offers improved performance, making it ideal for complex information retrieval and analysis.

    For those experienced with basic RAG systems, GraphRAG offers an opportunity to explore more sophisticated solutions, although it may not be necessary for all use cases.
    Retrieval Augmented Generation (RAG) is often performed by chunking long texts, creating a text embedding for each chunk, and retrieving chunks for including in the LLM generation context based on a similarity search against the query. This approach works well in many scenarios, and at compelling speed and cost trade-offs, but doesn't always cope well in scenarios where a detailed understanding of the text is required.

    GraphRag ( [microsoft.github.io/graphrag](https://microsoft.github.io/graphrag/) )
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    <div style="text-align: center;">

    <img src="../images/Microsoft_GraphRag.svg" alt="adaptive retrieval" style="width:100%; height:auto;">
    </div>
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    To run this notebook you can use either OpenAI API key or Azure OpenAI key.
    Create a `.env` file and fill in the credentials for your OpenAI or Azure Open AI deployment. The following code loads these environment variables and sets up our AI client.
    """)
    return


@app.cell
def _():
    AZURE_OPENAI_API_KEY=""
    AZURE_OPENAI_ENDPOINT=""
    GPT4O_MODEL_NAME="gpt-4o"
    TEXT_EMBEDDING_3_LARGE_DEPLOYMENT_NAME=""
    AZURE_OPENAI_API_VERSION="2024-06-01"

    OPENAI_API_KEY=""
    return


@app.cell
def _():
    # '%pip install graphrag' command supported automatically in marimo
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
    # packages added via marimo's package management: beautifulsoup4 openai python-dotenv pyyaml !pip install beautifulsoup4 openai python-dotenv pyyaml
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Package Installation

    The cell below installs all necessary packages required to run this notebook. If you're running this notebook in a new environment, execute this cell first to ensure all dependencies are installed.
    """)
    return


@app.cell
def _():
    # Install required packages
    # packages added via marimo's package management: openai python-dotenv !pip install openai python-dotenv
    return


@app.cell
def _():
    from dotenv import load_dotenv
    import os
    load_dotenv()
    from openai import AzureOpenAI, OpenAI
    AZURE = True
    if AZURE:  #Change to False to use OpenAI
        AZURE_OPENAI_API_KEY_1 = os.getenv('AZURE_OPENAI_API_KEY')
        AZURE_OPENAI_ENDPOINT_1 = os.getenv('AZURE_OPENAI_ENDPOINT')
        GPT4O_DEPLOYMENT_NAME = os.getenv('GPT4O_MODEL_NAME')
        TEXT_EMBEDDING_3_LARGE_NAME = os.getenv('TEXT_EMBEDDING_3_LARGE_DEPLOYMENT_NAME')
        AZURE_OPENAI_API_VERSION_1 = os.getenv('AZURE_OPENAI_API_VERSION')
        oai = AzureOpenAI(azure_endpoint=AZURE_OPENAI_ENDPOINT_1, api_key=AZURE_OPENAI_API_KEY_1, api_version=AZURE_OPENAI_API_VERSION_1)
    else:
        OPENAI_API_KEY_1 = os.getenv('OPENAI_API_KEY')
        oai = OpenAI(api_key=OPENAI_API_KEY_1)
    return (
        AZURE,
        AZURE_OPENAI_API_KEY_1,
        AZURE_OPENAI_API_VERSION_1,
        AZURE_OPENAI_ENDPOINT_1,
        GPT4O_DEPLOYMENT_NAME,
        OPENAI_API_KEY_1,
        TEXT_EMBEDDING_3_LARGE_NAME,
        os,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    We'll start by getting a text to work with. The Wikipedia article on Elon Musk
    """)
    return


@app.cell
def _(os):
    import requests
    from bs4 import BeautifulSoup
    url = 'https://en.wikipedia.org/wiki/Elon_Musk'
    response = requests.get(url)  # Replace with the URL of the web page you want to scrape
    soup = BeautifulSoup(response.text, 'html.parser')
    if not os.path.exists('data'):
        os.makedirs('data')
    if not os.path.exists('data/elon.md'):
        elon = soup.text.split('\nSee also')[0]
        with open('data/elon.md', 'w', encoding='utf-8') as _f:
            _f.write(elon)
    else:
        with open('data/elon.md', 'r') as _f:
            elon = _f.read()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    GraphRag has a convenient set of CLI commands we can use. We'll start by configuring the system, then run the indexing operation. Indexing with GraphRag is a much lengthier process, and one that costs significantly more, since rather than just calculating embeddings, GraphRag makes many LLM calls to analyse the text, extract entities, and construct the graph. That's a one-time expense, though.
    """)
    return


@app.cell
def _(
    AZURE,
    AZURE_OPENAI_API_KEY_1,
    AZURE_OPENAI_API_VERSION_1,
    AZURE_OPENAI_ENDPOINT_1,
    GPT4O_DEPLOYMENT_NAME,
    OPENAI_API_KEY_1,
    TEXT_EMBEDDING_3_LARGE_NAME,
    os,
    subprocess,
):
    import yaml
    if not os.path.exists('data/graphrag'):
        subprocess.call(['python', '-m', 'graphrag.index', '--init', '--root', 'data/graphrag'])
    with open('data/graphrag/settings.yaml', 'r') as _f:
        settings_yaml = yaml.load(_f, Loader=yaml.FullLoader)
    settings_yaml['llm']['model'] = 'gpt-4o'
    settings_yaml['llm']['api_key'] = AZURE_OPENAI_API_KEY_1 if AZURE else OPENAI_API_KEY_1
    settings_yaml['llm']['type'] = 'azure_openai_chat' if AZURE else 'openai_chat'
    settings_yaml['embeddings']['llm']['api_key'] = AZURE_OPENAI_API_KEY_1 if AZURE else OPENAI_API_KEY_1
    settings_yaml['embeddings']['llm']['type'] = 'azure_openai_embedding' if AZURE else 'openai_embedding'
    settings_yaml['embeddings']['llm']['model'] = TEXT_EMBEDDING_3_LARGE_NAME if AZURE else 'text-embedding-3-large'
    if AZURE:
        settings_yaml['llm']['api_version'] = AZURE_OPENAI_API_VERSION_1
        settings_yaml['llm']['deployment_name'] = GPT4O_DEPLOYMENT_NAME
        settings_yaml['llm']['api_base'] = AZURE_OPENAI_ENDPOINT_1
        settings_yaml['embeddings']['llm']['api_version'] = AZURE_OPENAI_API_VERSION_1
        settings_yaml['embeddings']['llm']['deployment_name'] = TEXT_EMBEDDING_3_LARGE_NAME
        settings_yaml['embeddings']['llm']['api_base'] = AZURE_OPENAI_ENDPOINT_1
    with open('data/graphrag/settings.yaml', 'w') as _f:
        yaml.dump(settings_yaml, _f)
    if not os.path.exists('data/graphrag/input'):
        os.makedirs('data/graphrag/input')
        subprocess.call(['cp', 'data/elon.md', 'data/graphrag/input/elon.txt'])
        subprocess.call(['python', '-m', 'graphrag.index', '--root', './data/graphrag'])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    You should get an output:
    🚀 All workflows completed successfully.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    To query GraphRag we'll use its CLI again, making sure to configure it with a context length equivalent to what we use in our embeddings search.
    """)
    return


@app.cell
def _(os):
    import subprocess
    import re
    DEFAULT_RESPONSE_TYPE = 'Summarize and explain in 1-2 paragraphs with bullet points using at most 300 tokens'
    DEFAULT_MAX_CONTEXT_TOKENS = 10000

    def remove_data(text):
        return re.sub(r'\[Data:.*?\]', '', text).strip()


    def ask_graph(query,method):
        env = os.environ.copy() | {
          'GRAPHRAG_GLOBAL_SEARCH_MAX_TOKENS': str(DEFAULT_MAX_CONTEXT_TOKENS),
        }
        command = [
          'python', '-m', 'graphrag.query',
          '--root', './data/graphrag',
          '--method', method,
          '--response_type', DEFAULT_RESPONSE_TYPE,
          query,
        ]
        output = subprocess.check_output(command, universal_newlines=True, env=env, stderr=subprocess.DEVNULL)
        return remove_data(output.split('Search Response: ')[1])

    return ask_graph, subprocess


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    GrpahRag offers 2 types of search:
    1. Global Search for reasoning about holistic questions about the corpus by leveraging the community summaries.
    2. Local Search for reasoning about specific entities by fanning-out to their neighbors and associated concepts.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Let's check the local search:
    """)
    return


@app.cell
def _(ask_graph):
    from IPython.display import Markdown
    local_query="What and how many companies and subsidieries founded by Elon Musk"
    local_result = ask_graph(local_query,'local')

    Markdown(local_result)
    return (Markdown,)


@app.cell
def _(Markdown, ask_graph):
    global_query="What are the major accomplishments of Elon Musk?"
    global_result = ask_graph(global_query,'global')

    Markdown(global_result)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--microsoft-graphrag)
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
