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
    mo.md("# Corrective RAG Process: Retrieval-Augmented Generation with Dynamic Correction\n\n## Overview\n\nThe Corrective RAG (Retrieval-Augmented Generation) process is an advanced information retrieval and response generation system. It extends the standard RAG approach by dynamically evaluating and correcting the retrieval process, combining the power of vector databases, web search, and language models to provide accurate and context-aware responses to user queries.\n\n## Motivation\n\nWhile traditional RAG systems have improved information retrieval and response generation, they can still fall short when the retrieved information is irrelevant or outdated. The Corrective RAG process addresses these limitations by:\n\n1. Leveraging pre-existing knowledge bases\n2. Evaluating the relevance of retrieved information\n3. Dynamically searching the web when necessary\n4. Refining and combining knowledge from multiple sources\n5. Generating human-like responses based on the most appropriate knowledge\n\n## Key Components\n\n1. **FAISS Index**: A vector database for efficient similarity search of pre-existing knowledge.\n2. **Retrieval Evaluator**: Assesses the relevance of retrieved documents to the query.\n3. **Knowledge Refinement**: Extracts key information from documents when necessary.\n4. **Web Search Query Rewriter**: Optimizes queries for web searches when local knowledge is insufficient.\n5. **Response Generator**: Creates human-like responses based on the accumulated knowledge.\n\n## Method Details\n\n1. **Document Retrieval**: \n   - Performs similarity search in the FAISS index to find relevant documents.\n   - Retrieves top-k documents (default k=3).\n\n2. **Document Evaluation**:\n   - Calculates relevance scores for each retrieved document.\n   - Determines the best course of action based on the highest relevance score.\n\n3. **Corrective Knowledge Acquisition**:\n   - If high relevance (score > 0.7): Uses the most relevant document as-is.\n   - If low relevance (score < 0.3): Corrects by performing a web search with a rewritten query.\n   - If ambiguous (0.3 ≤ score ≤ 0.7): Corrects by combining the most relevant document with web search results.\n\n4. **Adaptive Knowledge Processing**:\n   - For web search results: Refines the knowledge to extract key points.\n   - For ambiguous cases: Combines raw document content with refined web search results.\n\n5. **Response Generation**:\n   - Uses a language model to generate a human-like response based on the query and acquired knowledge.\n   - Includes source information in the response for transparency.\n\n## Benefits of the Corrective RAG Approach\n\n1. **Dynamic Correction**: Adapts to the quality of retrieved information, ensuring relevance and accuracy.\n2. **Flexibility**: Leverages both pre-existing knowledge and web search as needed.\n3. **Accuracy**: Evaluates the relevance of information before using it, ensuring high-quality responses.\n4. **Transparency**: Provides source information, allowing users to verify the origin of the information.\n5. **Efficiency**: Uses vector search for quick retrieval from large knowledge bases.\n6. **Contextual Understanding**: Combines multiple sources of information when necessary to provide comprehensive responses.\n7. **Up-to-date Information**: Can supplement or replace outdated local knowledge with current web information.\n\n## Conclusion\n\nThe Corrective RAG process represents a sophisticated evolution of the standard RAG approach. By intelligently evaluating and correcting the retrieval process, it overcomes common limitations of traditional RAG systems. This dynamic approach ensures that responses are based on the most relevant and up-to-date information available, whether from local knowledge bases or the web. The system's ability to adapt its information sourcing strategy based on relevance scores makes it particularly suited for applications requiring high accuracy and current information, such as research assistance, dynamic knowledge bases, and advanced question-answering systems.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('<div style="text-align: center;">\n\n<img src="../images/crag.svg" alt="Corrective RAG" style="width:80%; height:auto;">\n</div>')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('# Package Installation and Imports\n\nThe cell below installs all necessary packages required to run this notebook.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define files path')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Create a vector store')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Initialize OpenAI language model\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Initialize search tool')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define retrieval evaluator, knowledge refinement and query rewriter llm chains')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Helper function to parse search results\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define sub functions for the CRAG process')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### CRAG process\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Example query with high relevance to the document\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Example query with low relevance to the document\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--crag)')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# Install required packages\n# SETUP (run separately): !pip install langchain langchain-openai python-dotenv\n\n# Clone the repository to access helper functions and evaluation modules\n# SETUP (run separately): !git clone https://github.com/NirDiamant/RAG_TECHNIQUES.git\nimport sys\nsys.path.append(\'RAG_TECHNIQUES\')\n# If you need to run with the latest data\n# !cp -r RAG_TECHNIQUES/data .\n\nimport os\nimport sys\nfrom dotenv import load_dotenv\nfrom langchain.prompts import PromptTemplate\nfrom langchain_openai import ChatOpenAI\nfrom langchain_core.pydantic_v1 import BaseModel, Field\n\n\n# Original path append replaced for Colab compatibility\nfrom helper_functions import *\nfrom evaluation.evalute_rag import *\n\n# Load environment variables from a .env file\nload_dotenv()\n\n# Set the OpenAI API key environment variable\nos.environ["OPENAI_API_KEY"] = os.getenv(\'OPENAI_API_KEY\')\nfrom langchain.tools import DuckDuckGoSearchResults\n\n# Download required data files\nimport os\nos.makedirs(\'data\', exist_ok=True)\n\n# Download the PDF document used in this notebook\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n\npath = "data/Understanding_Climate_Change.pdf"\n\nvectorstore = encode_pdf(path)\n\nllm = ChatOpenAI(model="gpt-4o-mini", max_tokens=1000, temperature=0)\n\nsearch = DuckDuckGoSearchResults()\n\n# Retrieval Evaluator\nclass RetrievalEvaluatorInput(BaseModel):\n    relevance_score: float = Field(..., description="The relevance score of the document to the query. the score should be between 0 and 1.")\ndef retrieval_evaluator(query: str, document: str) -> float:\n    prompt = PromptTemplate(\n        input_variables=["query", "document"],\n        template="On a scale from 0 to 1, how relevant is the following document to the query? Query: {query}\\nDocument: {document}\\nRelevance score:"\n    )\n    chain = prompt | llm.with_structured_output(RetrievalEvaluatorInput)\n    input_variables = {"query": query, "document": document}\n    result = chain.invoke(input_variables).relevance_score\n    return result\n\n# Knowledge Refinement\nclass KnowledgeRefinementInput(BaseModel):\n    key_points: str = Field(..., description="The document to extract key information from.")\ndef knowledge_refinement(document: str) -> List[str]:\n    prompt = PromptTemplate(\n        input_variables=["document"],\n        template="Extract the key information from the following document in bullet points:\\n{document}\\nKey points:"\n    )\n    chain = prompt | llm.with_structured_output(KnowledgeRefinementInput)\n    input_variables = {"document": document}\n    result = chain.invoke(input_variables).key_points\n    return [point.strip() for point in result.split(\'\\n\') if point.strip()]\n\n# Web Search Query Rewriter\nclass QueryRewriterInput(BaseModel):\n    query: str = Field(..., description="The query to rewrite.")\ndef rewrite_query(query: str) -> str:\n    prompt = PromptTemplate(\n        input_variables=["query"],\n        template="Rewrite the following query to make it more suitable for a web search:\\n{query}\\nRewritten query:"\n    )\n    chain = prompt | llm.with_structured_output(QueryRewriterInput)\n    input_variables = {"query": query}\n    return chain.invoke(input_variables).query.strip()\n\ndef parse_search_results(results_string: str) -> List[Tuple[str, str]]:\n    """\n    Parse a JSON string of search results into a list of title-link tuples.\n\n    Args:\n        results_string (str): A JSON-formatted string containing search results.\n\n    Returns:\n        List[Tuple[str, str]]: A list of tuples, where each tuple contains the title and link of a search result.\n                               If parsing fails, an empty list is returned.\n    """\n    try:\n        # Attempt to parse the JSON string\n        results = json.loads(results_string)\n        # Extract and return the title and link from each result\n        return [(result.get(\'title\', \'Untitled\'), result.get(\'link\', \'\')) for result in results]\n    except json.JSONDecodeError:\n        # Handle JSON decoding errors by returning an empty list\n        print("Error parsing search results. Returning empty list.")\n        return []\n\ndef retrieve_documents(query: str, faiss_index: FAISS, k: int = 3) -> List[str]:\n    """\n    Retrieve documents based on a query using a FAISS index.\n\n    Args:\n        query (str): The query string to search for.\n        faiss_index (FAISS): The FAISS index used for similarity search.\n        k (int): The number of top documents to retrieve. Defaults to 3.\n\n    Returns:\n        List[str]: A list of the retrieved document contents.\n    """\n    docs = faiss_index.similarity_search(query, k=k)\n    return [doc.page_content for doc in docs]\n\ndef evaluate_documents(query: str, documents: List[str]) -> List[float]:\n    """\n    Evaluate the relevance of documents based on a query.\n\n    Args:\n        query (str): The query string.\n        documents (List[str]): A list of document contents to evaluate.\n\n    Returns:\n        List[float]: A list of relevance scores for each document.\n    """\n    return [retrieval_evaluator(query, doc) for doc in documents]\n\ndef perform_web_search(query: str) -> Tuple[List[str], List[Tuple[str, str]]]:\n    """\n    Perform a web search based on a query.\n\n    Args:\n        query (str): The query string to search for.\n\n    Returns:\n        Tuple[List[str], List[Tuple[str, str]]]: \n            - A list of refined knowledge obtained from the web search.\n            - A list of tuples containing titles and links of the sources.\n    """\n    rewritten_query = rewrite_query(query)\n    web_results = search.run(rewritten_query)\n    web_knowledge = knowledge_refinement(web_results)\n    sources = parse_search_results(web_results)\n    return web_knowledge, sources\n\ndef generate_response(query: str, knowledge: str, sources: List[Tuple[str, str]]) -> str:\n    """\n    Generate a response to a query using knowledge and sources.\n\n    Args:\n        query (str): The query string.\n        knowledge (str): The refined knowledge to use in the response.\n        sources (List[Tuple[str, str]]): A list of tuples containing titles and links of the sources.\n\n    Returns:\n        str: The generated response.\n    """\n    response_prompt = PromptTemplate(\n        input_variables=["query", "knowledge", "sources"],\n        template="Based on the following knowledge, answer the query. Include the sources with their links (if available) at the end of your answer:\\nQuery: {query}\\nKnowledge: {knowledge}\\nSources: {sources}\\nAnswer:"\n    )\n    input_variables = {\n        "query": query,\n        "knowledge": knowledge,\n        "sources": "\\n".join([f"{title}: {link}" if link else title for title, link in sources])\n    }\n    response_chain = response_prompt | llm\n    return response_chain.invoke(input_variables).content\n\ndef crag_process(query: str, faiss_index: FAISS) -> str:\n    """\n    Process a query by retrieving, evaluating, and using documents or performing a web search to generate a response.\n\n    Args:\n        query (str): The query string to process.\n        faiss_index (FAISS): The FAISS index used for document retrieval.\n\n    Returns:\n        str: The generated response based on the query.\n    """\n    print(f"\\nProcessing query: {query}")\n\n    # Retrieve and evaluate documents\n    retrieved_docs = retrieve_documents(query, faiss_index)\n    eval_scores = evaluate_documents(query, retrieved_docs)\n    \n    print(f"\\nRetrieved {len(retrieved_docs)} documents")\n    print(f"Evaluation scores: {eval_scores}")\n\n    # Determine action based on evaluation scores\n    max_score = max(eval_scores)\n    sources = []\n    \n    if max_score > 0.7:\n        print("\\nAction: Correct - Using retrieved document")\n        best_doc = retrieved_docs[eval_scores.index(max_score)]\n        final_knowledge = best_doc\n        sources.append(("Retrieved document", ""))\n    elif max_score < 0.3:\n        print("\\nAction: Incorrect - Performing web search")\n        final_knowledge, sources = perform_web_search(query)\n    else:\n        print("\\nAction: Ambiguous - Combining retrieved document and web search")\n        best_doc = retrieved_docs[eval_scores.index(max_score)]\n        # Refine the retrieved knowledge\n        retrieved_knowledge = knowledge_refinement(best_doc)\n        web_knowledge, web_sources = perform_web_search(query)\n        final_knowledge = "\\n".join(retrieved_knowledge + web_knowledge)\n        sources = [("Retrieved document", "")] + web_sources\n\n    print("\\nFinal knowledge:")\n    print(final_knowledge)\n    \n    print("\\nSources:")\n    for title, link in sources:\n        print(f"{title}: {link}" if link else title)\n\n    # Generate response\n    print("\\nGenerating response...")\n    response = generate_response(query, final_knowledge, sources)\n\n    print("\\nResponse generated")\n    return response\n\nquery = "What are the main causes of climate change?"\nresult = crag_process(query, vectorstore)\nprint(f"Query: {query}")\nprint(f"Answer: {result}")\n\nquery = "how did harry beat quirrell?"\nresult = crag_process(query, vectorstore)\nprint(f"Query: {query}")\nprint(f"Answer: {result}")', language="python", label="Recovered notebook code")
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
