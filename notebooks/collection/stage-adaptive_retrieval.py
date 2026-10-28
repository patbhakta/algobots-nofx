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
    mo.md("<!-- ![](https://europe-west1-atp-views-tracker.cloudfunctions.net/working-analytics?notebook=adaptive-retrieval) -->\n\n\n\n# Adaptive Retrieval-Augmented Generation (RAG) System\n\n## Overview\n\nThis system implements an advanced Retrieval-Augmented Generation (RAG) approach that adapts its retrieval strategy based on the type of query. By leveraging Language Models (LLMs) at various stages, it aims to provide more accurate, relevant, and context-aware responses to user queries.\n\n## Motivation\n\nTraditional RAG systems often use a one-size-fits-all approach to retrieval, which can be suboptimal for different types of queries. Our adaptive system is motivated by the understanding that different types of questions require different retrieval strategies. For example, a factual query might benefit from precise, focused retrieval, while an analytical query might require a broader, more diverse set of information.\n\n## Key Components\n\n1. **Query Classifier**: Determines the type of query (Factual, Analytical, Opinion, or Contextual).\n\n2. **Adaptive Retrieval Strategies**: Four distinct strategies tailored to different query types:\n   - Factual Strategy\n   - Analytical Strategy\n   - Opinion Strategy\n   - Contextual Strategy\n\n3. **LLM Integration**: LLMs are used throughout the process to enhance retrieval and ranking.\n\n4. **OpenAI GPT Model**: Generates the final response using the retrieved documents as context.\n\n## Method Details\n\n### 1. Query Classification\n\nThe system begins by classifying the user's query into one of four categories:\n- Factual: Queries seeking specific, verifiable information.\n- Analytical: Queries requiring comprehensive analysis or explanation.\n- Opinion: Queries about subjective matters or seeking diverse viewpoints.\n- Contextual: Queries that depend on user-specific context.\n\n### 2. Adaptive Retrieval Strategies\n\nEach query type triggers a specific retrieval strategy:\n\n#### Factual Strategy\n- Enhances the original query using an LLM for better precision.\n- Retrieves documents based on the enhanced query.\n- Uses an LLM to rank documents by relevance.\n\n#### Analytical Strategy\n- Generates multiple sub-queries using an LLM to cover different aspects of the main query.\n- Retrieves documents for each sub-query.\n- Ensures diversity in the final document selection using an LLM.\n\n#### Opinion Strategy\n- Identifies different viewpoints on the topic using an LLM.\n- Retrieves documents representing each viewpoint.\n- Uses an LLM to select a diverse range of opinions from the retrieved documents.\n\n#### Contextual Strategy\n- Incorporates user-specific context into the query using an LLM.\n- Performs retrieval based on the contextualized query.\n- Ranks documents considering both relevance and user context.\n\n### 3. LLM-Enhanced Ranking\n\nAfter retrieval, each strategy uses an LLM to perform a final ranking of the documents. This step ensures that the most relevant and appropriate documents are selected for the next stage.\n\n### 4. Response Generation\n\nThe final set of retrieved documents is passed to an OpenAI GPT model, which generates a response based on the query and the provided context.\n\n## Benefits of This Approach\n\n1. **Improved Accuracy**: By tailoring the retrieval strategy to the query type, the system can provide more accurate and relevant information.\n\n2. **Flexibility**: The system adapts to different types of queries, handling a wide range of user needs.\n\n3. **Context-Awareness**: Especially for contextual queries, the system can incorporate user-specific information for more personalized responses.\n\n4. **Diverse Perspectives**: For opinion-based queries, the system actively seeks out and presents multiple viewpoints.\n\n5. **Comprehensive Analysis**: The analytical strategy ensures a thorough exploration of complex topics.\n\n## Conclusion\n\nThis adaptive RAG system represents a significant advancement over traditional RAG approaches. By dynamically adjusting its retrieval strategy and leveraging LLMs throughout the process, it aims to provide more accurate, relevant, and nuanced responses to a wide variety of user queries.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('<div style="text-align: center;">\n\n<img src="../images/adaptive_retrieval.svg" alt="adaptive retrieval" style="width:100%; height:auto;">\n</div>')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('# Package Installation and Imports\n\nThe cell below installs all necessary packages required to run this notebook.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define the query classifer class')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define the Base Retriever class, such that the complex ones will inherit from it')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define Factual retriever strategy')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define Analytical reriever strategy')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define Opinion retriever strategy')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define Contextual retriever strategy')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define the Adapive retriever class')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define aditional retriever that inherits from langchain BaseRetriever ')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define the Adaptive RAG class')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Demonstrate use of this model')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Showcase the four different types of queries')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--adaptive-retrieval)')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# Install required packages\n# SETUP (run separately): !pip install faiss-cpu langchain langchain-openai python-dotenv\n\n# Clone the repository to access helper functions and evaluation modules\n# SETUP (run separately): !git clone https://github.com/NirDiamant/RAG_TECHNIQUES.git\nimport sys\nsys.path.append(\'RAG_TECHNIQUES\')\n# If you need to run with the latest data\n# !cp -r RAG_TECHNIQUES/data .\n\nimport os\nimport sys\nfrom dotenv import load_dotenv\nfrom langchain.prompts import PromptTemplate\nfrom langchain.vectorstores import FAISS\nfrom langchain.embeddings import OpenAIEmbeddings\nfrom langchain.text_splitter import CharacterTextSplitter\nfrom langchain.prompts import PromptTemplate\n\nfrom langchain_core.retrievers import BaseRetriever\nfrom typing import Dict, Any\nfrom langchain.docstore.document import Document\nfrom langchain_openai import ChatOpenAI\nfrom langchain_core.pydantic_v1 import BaseModel, Field\n\n\n# Original path append replaced for Colab compatibility\nfrom helper_functions import *\nfrom evaluation.evalute_rag import *\n\n# Load environment variables from a .env file\nload_dotenv()\n\n# Set the OpenAI API key environment variable\nos.environ["OPENAI_API_KEY"] = os.getenv(\'OPENAI_API_KEY\')\n\nclass categories_options(BaseModel):\n        category: str = Field(description="The category of the query, the options are: Factual, Analytical, Opinion, or Contextual", example="Factual")\n\n\nclass QueryClassifier:\n    def __init__(self):\n        self.llm = ChatOpenAI(temperature=0, model_name="gpt-4o", max_tokens=4000)\n        self.prompt = PromptTemplate(\n            input_variables=["query"],\n            template="Classify the following query into one of these categories: Factual, Analytical, Opinion, or Contextual.\\nQuery: {query}\\nCategory:"\n        )\n        self.chain = self.prompt | self.llm.with_structured_output(categories_options)\n\n\n    def classify(self, query):\n        print("clasiffying query")\n        return self.chain.invoke(query).category\n\nclass BaseRetrievalStrategy:\n    def __init__(self, texts):\n        self.embeddings = OpenAIEmbeddings()\n        text_splitter = CharacterTextSplitter(chunk_size=800, chunk_overlap=0)\n        self.documents = text_splitter.create_documents(texts)\n        self.db = FAISS.from_documents(self.documents, self.embeddings)\n        self.llm = ChatOpenAI(temperature=0, model_name="gpt-4o", max_tokens=4000)\n\n\n    def retrieve(self, query, k=4):\n        return self.db.similarity_search(query, k=k)\n\nclass relevant_score(BaseModel):\n        score: float = Field(description="The relevance score of the document to the query", example=8.0)\n\nclass FactualRetrievalStrategy(BaseRetrievalStrategy):\n    def retrieve(self, query, k=4):\n        print("retrieving factual")\n        # Use LLM to enhance the query\n        enhanced_query_prompt = PromptTemplate(\n            input_variables=["query"],\n            template="Enhance this factual query for better information retrieval: {query}"\n        )\n        query_chain = enhanced_query_prompt | self.llm\n        enhanced_query = query_chain.invoke(query).content\n        print(f\'enhande query: {enhanced_query}\')\n\n        # Retrieve documents using the enhanced query\n        docs = self.db.similarity_search(enhanced_query, k=k*2)\n\n        # Use LLM to rank the relevance of retrieved documents\n        ranking_prompt = PromptTemplate(\n            input_variables=["query", "doc"],\n            template="On a scale of 1-10, how relevant is this document to the query: \'{query}\'?\\nDocument: {doc}\\nRelevance score:"\n        )\n        ranking_chain = ranking_prompt | self.llm.with_structured_output(relevant_score)\n\n        ranked_docs = []\n        print("ranking docs")\n        for doc in docs:\n            input_data = {"query": enhanced_query, "doc": doc.page_content}\n            score = float(ranking_chain.invoke(input_data).score)\n            ranked_docs.append((doc, score))\n\n        # Sort by relevance score and return top k\n        ranked_docs.sort(key=lambda x: x[1], reverse=True)\n        return [doc for doc, _ in ranked_docs[:k]]\n\nclass SelectedIndices(BaseModel):\n    indices: List[int] = Field(description="Indices of selected documents", example=[0, 1, 2, 3])\n\nclass SubQueries(BaseModel):\n    sub_queries: List[str] = Field(description="List of sub-queries for comprehensive analysis", example=["What is the population of New York?", "What is the GDP of New York?"])\n\nclass AnalyticalRetrievalStrategy(BaseRetrievalStrategy):\n    def retrieve(self, query, k=4):\n        print("retrieving analytical")\n        # Use LLM to generate sub-queries for comprehensive analysis\n        sub_queries_prompt = PromptTemplate(\n            input_variables=["query", "k"],\n            template="Generate {k} sub-questions for: {query}"\n        )\n\n        llm = ChatOpenAI(temperature=0, model_name="gpt-4o", max_tokens=4000)\n        sub_queries_chain = sub_queries_prompt | llm.with_structured_output(SubQueries)\n\n        input_data = {"query": query, "k": k}\n        sub_queries = sub_queries_chain.invoke(input_data).sub_queries\n        print(f\'sub queries for comprehensive analysis: {sub_queries}\')\n\n        all_docs = []\n        for sub_query in sub_queries:\n            all_docs.extend(self.db.similarity_search(sub_query, k=2))\n\n        # Use LLM to ensure diversity and relevance\n        diversity_prompt = PromptTemplate(\n            input_variables=["query", "docs", "k"],\n            template="""Select the most diverse and relevant set of {k} documents for the query: \'{query}\'\\nDocuments: {docs}\\n\n            Return only the indices of selected documents as a list of integers."""\n        )\n        diversity_chain = diversity_prompt | self.llm.with_structured_output(SelectedIndices)\n        docs_text = "\\n".join([f"{i}: {doc.page_content[:50]}..." for i, doc in enumerate(all_docs)])\n        input_data = {"query": query, "docs": docs_text, "k": k}\n        selected_indices_result = diversity_chain.invoke(input_data).indices\n        print(f\'selected diverse and relevant documents\')\n        \n        return [all_docs[i] for i in selected_indices_result if i < len(all_docs)]\n\nclass OpinionRetrievalStrategy(BaseRetrievalStrategy):\n    def retrieve(self, query, k=3):\n        print("retrieving opinion")\n        # Use LLM to identify potential viewpoints\n        viewpoints_prompt = PromptTemplate(\n            input_variables=["query", "k"],\n            template="Identify {k} distinct viewpoints or perspectives on the topic: {query}"\n        )\n        viewpoints_chain = viewpoints_prompt | self.llm\n        input_data = {"query": query, "k": k}\n        viewpoints = viewpoints_chain.invoke(input_data).content.split(\'\\n\')\n        print(f\'viewpoints: {viewpoints}\')\n\n        all_docs = []\n        for viewpoint in viewpoints:\n            all_docs.extend(self.db.similarity_search(f"{query} {viewpoint}", k=2))\n\n        # Use LLM to classify and select diverse opinions\n        opinion_prompt = PromptTemplate(\n            input_variables=["query", "docs", "k"],\n            template="Classify these documents into distinct opinions on \'{query}\' and select the {k} most representative and diverse viewpoints:\\nDocuments: {docs}\\nSelected indices:"\n        )\n        opinion_chain = opinion_prompt | self.llm.with_structured_output(SelectedIndices)\n        \n        docs_text = "\\n".join([f"{i}: {doc.page_content[:100]}..." for i, doc in enumerate(all_docs)])\n        input_data = {"query": query, "docs": docs_text, "k": k}\n        selected_indices = opinion_chain.invoke(input_data).indices\n        print(f\'selected diverse and relevant documents\')\n        \n        return [all_docs[int(i)] for i in selected_indices.split() if i.isdigit() and int(i) < len(all_docs)]\n\nclass ContextualRetrievalStrategy(BaseRetrievalStrategy):\n    def retrieve(self, query, k=4, user_context=None):\n        print("retrieving contextual")\n        # Use LLM to incorporate user context into the query\n        context_prompt = PromptTemplate(\n            input_variables=["query", "context"],\n            template="Given the user context: {context}\\nReformulate the query to best address the user\'s needs: {query}"\n        )\n        context_chain = context_prompt | self.llm\n        input_data = {"query": query, "context": user_context or "No specific context provided"}\n        contextualized_query = context_chain.invoke(input_data).content\n        print(f\'contextualized query: {contextualized_query}\')\n\n        # Retrieve documents using the contextualized query\n        docs = self.db.similarity_search(contextualized_query, k=k*2)\n\n        # Use LLM to rank the relevance of retrieved documents considering the user context\n        ranking_prompt = PromptTemplate(\n            input_variables=["query", "context", "doc"],\n            template="Given the query: \'{query}\' and user context: \'{context}\', rate the relevance of this document on a scale of 1-10:\\nDocument: {doc}\\nRelevance score:"\n        )\n        ranking_chain = ranking_prompt | self.llm.with_structured_output(relevant_score)\n        print("ranking docs")\n\n        ranked_docs = []\n        for doc in docs:\n            input_data = {"query": contextualized_query, "context": user_context or "No specific context provided", "doc": doc.page_content}\n            score = float(ranking_chain.invoke(input_data).score)\n            ranked_docs.append((doc, score))\n\n\n        # Sort by relevance score and return top k\n        ranked_docs.sort(key=lambda x: x[1], reverse=True)\n\n        return [doc for doc, _ in ranked_docs[:k]]\n\nclass AdaptiveRetriever:\n    def __init__(self, texts: List[str]):\n        self.classifier = QueryClassifier()\n        self.strategies = {\n            "Factual": FactualRetrievalStrategy(texts),\n            "Analytical": AnalyticalRetrievalStrategy(texts),\n            "Opinion": OpinionRetrievalStrategy(texts),\n            "Contextual": ContextualRetrievalStrategy(texts)\n        }\n\n    def get_relevant_documents(self, query: str) -> List[Document]:\n        category = self.classifier.classify(query)\n        strategy = self.strategies[category]\n        return strategy.retrieve(query)\n\nclass PydanticAdaptiveRetriever(BaseRetriever):\n    adaptive_retriever: AdaptiveRetriever = Field(exclude=True)\n\n    class Config:\n        arbitrary_types_allowed = True\n\n    def get_relevant_documents(self, query: str) -> List[Document]:\n        return self.adaptive_retriever.get_relevant_documents(query)\n\n    async def aget_relevant_documents(self, query: str) -> List[Document]:\n        return self.get_relevant_documents(query)\n\nclass AdaptiveRAG:\n    def __init__(self, texts: List[str]):\n        adaptive_retriever = AdaptiveRetriever(texts)\n        self.retriever = PydanticAdaptiveRetriever(adaptive_retriever=adaptive_retriever)\n        self.llm = ChatOpenAI(temperature=0, model_name="gpt-4o", max_tokens=4000)\n        \n        # Create a custom prompt\n        prompt_template = """Use the following pieces of context to answer the question at the end. \n        If you don\'t know the answer, just say that you don\'t know, don\'t try to make up an answer.\n\n        {context}\n\n        Question: {question}\n        Answer:"""\n        prompt = PromptTemplate(template=prompt_template, input_variables=["context", "question"])\n        \n        # Create the LLM chain\n        self.llm_chain = prompt | self.llm\n        \n      \n\n    def answer(self, query: str) -> str:\n        docs = self.retriever.get_relevant_documents(query)\n        input_data = {"context": "\\n".join([doc.page_content for doc in docs]), "question": query}\n        return self.llm_chain.invoke(input_data)\n\n# Usage\ntexts = [\n    "The Earth is the third planet from the Sun and the only astronomical object known to harbor life."\n    ]\nrag_system = AdaptiveRAG(texts)\n\nfactual_result = rag_system.answer("What is the distance between the Earth and the Sun?").content\nprint(f"Answer: {factual_result}")\n\nanalytical_result = rag_system.answer("How does the Earth\'s distance from the Sun affect its climate?").content\nprint(f"Answer: {analytical_result}")\n\nopinion_result = rag_system.answer("What are the different theories about the origin of life on Earth?").content\nprint(f"Answer: {opinion_result}")\n\ncontextual_result = rag_system.answer("How does the Earth\'s position in the Solar System influence its habitability?").content\nprint(f"Answer: {contextual_result}")', language="python", label="Recovered notebook code")
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
