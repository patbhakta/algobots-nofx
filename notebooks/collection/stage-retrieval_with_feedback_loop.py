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
    mo.md("# RAG System with Feedback Loop: Enhancing Retrieval and Response Quality\n\n## Overview\n\nThis system implements a Retrieval-Augmented Generation (RAG) approach with an integrated feedback loop. It aims to improve the quality and relevance of responses over time by incorporating user feedback and dynamically adjusting the retrieval process.\n\n## Motivation\n\nTraditional RAG systems can sometimes produce inconsistent or irrelevant responses due to limitations in the retrieval process or the underlying knowledge base. By implementing a feedback loop, we can:\n\n1. Continuously improve the quality of retrieved documents\n2. Enhance the relevance of generated responses\n3. Adapt the system to user preferences and needs over time\n\n## Key Components\n\n1. **PDF Content Extraction**: Extracts text from PDF documents\n2. **Vectorstore**: Stores and indexes document embeddings for efficient retrieval\n3. **Retriever**: Fetches relevant documents based on user queries\n4. **Language Model**: Generates responses using retrieved documents\n5. **Feedback Collection**: Gathers user feedback on response quality and relevance\n6. **Feedback Storage**: Persists user feedback for future use\n7. **Relevance Score Adjustment**: Modifies document relevance based on feedback\n8. **Index Fine-tuning**: Periodically updates the vectorstore using accumulated feedback\n\n## Method Details\n\n### 1. Initial Setup\n- The system reads PDF content and creates a vectorstore\n- A retriever is initialized using the vectorstore\n- A language model (LLM) is set up for response generation\n\n### 2. Query Processing\n- When a user submits a query, the retriever fetches relevant documents\n- The LLM generates a response based on the retrieved documents\n\n### 3. Feedback Collection\n- The system collects user feedback on the response's relevance and quality\n- Feedback is stored in a JSON file for persistence\n\n### 4. Relevance Score Adjustment\n- For subsequent queries, the system loads previous feedback\n- An LLM evaluates the relevance of past feedback to the current query\n- Document relevance scores are adjusted based on this evaluation\n\n### 5. Retriever Update\n- The retriever is updated with the adjusted document scores\n- This ensures that future retrievals benefit from past feedback\n\n### 6. Periodic Index Fine-tuning\n- At regular intervals, the system fine-tunes the index\n- High-quality feedback is used to create additional documents\n- The vectorstore is updated with these new documents, improving overall retrieval quality\n\n## Benefits of this Approach\n\n1. **Continuous Improvement**: The system learns from each interaction, gradually enhancing its performance.\n2. **Personalization**: By incorporating user feedback, the system can adapt to individual or group preferences over time.\n3. **Increased Relevance**: The feedback loop helps prioritize more relevant documents in future retrievals.\n4. **Quality Control**: Low-quality or irrelevant responses are less likely to be repeated as the system evolves.\n5. **Adaptability**: The system can adjust to changes in user needs or document contents over time.\n\n## Conclusion\n\nThis RAG system with a feedback loop represents a significant advancement over traditional RAG implementations. By continuously learning from user interactions, it offers a more dynamic, adaptive, and user-centric approach to information retrieval and response generation. This system is particularly valuable in domains where information accuracy and relevance are critical, and where user needs may evolve over time.\n\nWhile the implementation adds complexity compared to a basic RAG system, the benefits in terms of response quality and user satisfaction make it a worthwhile investment for applications requiring high-quality, context-aware information retrieval and generation.")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('<div style="text-align: center;">\n\n<img src="../images/retrieval_with_feedback_loop.svg" alt="retrieval with feedback loop" style="width:40%; height:auto;">\n</div>')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('# Package Installation and Imports\n\nThe cell below installs all necessary packages required to run this notebook.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Define documents path')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Create vector store and retrieval QA chain')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Function to format user feedback in a dictionary')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Function to store the feedback in a json file')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Function to read the feedback file')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Function to adjust files relevancy based on the feedbacks file')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Function to fine tune the vector index to include also queries + answers that received good feedbacks')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Demonstration of how to retrieve answers with respect to user feedbacks')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Finetune the vectorstore periodicly')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--retrieval-with-feedback-loop)')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# Install required packages\n# SETUP (run separately): !pip install langchain langchain-openai python-dotenv\n\n# Clone the repository to access helper functions and evaluation modules\n# SETUP (run separately): !git clone https://github.com/NirDiamant/RAG_TECHNIQUES.git\nimport sys\nsys.path.append(\'RAG_TECHNIQUES\')\n# If you need to run with the latest data\n# !cp -r RAG_TECHNIQUES/data .\n\nimport os\nimport sys\nfrom dotenv import load_dotenv\nfrom langchain_text_splitters import RecursiveCharacterTextSplitter\nfrom langchain_openai import ChatOpenAI\nfrom langchain.chains import RetrievalQA\nimport json\nfrom typing import List, Dict, Any\n\n\n# Original path append replaced for Colab compatibility\nfrom helper_functions import *\nfrom evaluation.evalute_rag import *\n\n# Load environment variables from a .env file\nload_dotenv()\n\n# Set the OpenAI API key environment variable\nos.environ["OPENAI_API_KEY"] = os.getenv(\'OPENAI_API_KEY\')\nos.environ["KMP_DUPLICATE_LIB_OK"]="TRUE"\n\n# Download required data files\nimport os\nos.makedirs(\'data\', exist_ok=True)\n\n# Download the PDF document used in this notebook\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n# SETUP (run separately): !wget -O data/feedback_data.json https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/feedback_data.json\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n\npath = "data/Understanding_Climate_Change.pdf"\n\ncontent = read_pdf_to_string(path)\nvectorstore = encode_from_string(content)\nretriever = vectorstore.as_retriever()\n\nllm = ChatOpenAI(temperature=0, model_name="gpt-4o", max_tokens=4000)\nqa_chain = RetrievalQA.from_chain_type(llm, retriever=retriever)\n\ndef get_user_feedback(query, response, relevance, quality, comments=""):\n    return {\n        "query": query,\n        "response": response,\n        "relevance": int(relevance),\n        "quality": int(quality),\n        "comments": comments\n    }\n\ndef store_feedback(feedback):\n    with open("data/feedback_data.json", "a") as f:\n        json.dump(feedback, f)\n        f.write("\\n")\n\ndef load_feedback_data():\n    feedback_data = []\n    try:\n        with open("data/feedback_data.json", "r") as f:\n            for line in f:\n                feedback_data.append(json.loads(line.strip()))\n    except FileNotFoundError:\n        print("No feedback data file found. Starting with empty feedback.")\n    return feedback_data\n\nclass Response(BaseModel):\n    answer: str = Field(..., title="The answer to the question. The options can be only \'Yes\' or \'No\'")\n\ndef adjust_relevance_scores(query: str, docs: List[Any], feedback_data: List[Dict[str, Any]]) -> List[Any]:\n    # Create a prompt template for relevance checking\n    relevance_prompt = PromptTemplate(\n        input_variables=["query", "feedback_query", "doc_content", "feedback_response"],\n        template="""\n        Determine if the following feedback response is relevant to the current query and document content.\n        You are also provided with the Feedback original query that was used to generate the feedback response.\n        Current query: {query}\n        Feedback query: {feedback_query}\n        Document content: {doc_content}\n        Feedback response: {feedback_response}\n        \n        Is this feedback relevant? Respond with only \'Yes\' or \'No\'.\n        """\n    )\n    llm = ChatOpenAI(temperature=0, model_name="gpt-4o", max_tokens=4000)\n\n    # Create an LLMChain for relevance checking\n    relevance_chain = relevance_prompt | llm.with_structured_output(Response)\n\n    for doc in docs:\n        relevant_feedback = []\n        \n        for feedback in feedback_data:\n            # Use LLM to check relevance\n            input_data = {\n                "query": query,\n                "feedback_query": feedback[\'query\'],\n                "doc_content": doc.page_content[:1000],\n                "feedback_response": feedback[\'response\']\n            }\n            result = relevance_chain.invoke(input_data).answer\n            \n            if result == \'yes\':\n                relevant_feedback.append(feedback)\n        \n        # Adjust the relevance score based on feedback\n        if relevant_feedback:\n            avg_relevance = sum(f[\'relevance\'] for f in relevant_feedback) / len(relevant_feedback)\n            doc.metadata[\'relevance_score\'] *= (avg_relevance / 3)  # Assuming a 1-5 scale, 3 is neutral\n    \n    # Re-rank documents based on adjusted scores\n    return sorted(docs, key=lambda x: x.metadata[\'relevance_score\'], reverse=True)\n\ndef fine_tune_index(feedback_data: List[Dict[str, Any]], texts: List[str]) -> Any:\n    # Filter high-quality responses\n    good_responses = [f for f in feedback_data if f[\'relevance\'] >= 4 and f[\'quality\'] >= 4]\n    \n    # Extract queries and responses, and create new documents\n    additional_texts = []\n    for f in good_responses:\n        combined_text = f[\'query\'] + " " + f[\'response\']\n        additional_texts.append(combined_text)\n\n    # make the list a string\n    additional_texts = " ".join(additional_texts)\n    \n    # Create a new index with original and high-quality texts\n    all_texts = texts + additional_texts\n    new_vectorstore = encode_from_string(all_texts)\n    \n    return new_vectorstore\n\n\nquery = "What is the greenhouse effect?"\n\n# Get response from RAG system\nresponse = qa_chain(query)["result"]\n\nrelevance = 5\nquality = 5\n\n# Collect feedback\nfeedback = get_user_feedback(query, response, relevance, quality)\n\n# Store feedback\nstore_feedback(feedback)\n\n# Adjust relevance scores for future retrievals\ndocs = retriever.get_relevant_documents(query)\nadjusted_docs = adjust_relevance_scores(query, docs, load_feedback_data())\n\n# Update the retriever with adjusted docs\nretriever.search_kwargs[\'k\'] = len(adjusted_docs)\nretriever.search_kwargs[\'docs\'] = adjusted_docs\n\n# Periodically (e.g., daily or weekly), fine-tune the index\nnew_vectorstore = fine_tune_index(load_feedback_data(), content)\nretriever = new_vectorstore.as_retriever()', language="python", label="Recovered notebook code")
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
