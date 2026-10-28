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
    mo.md('# Self-RAG: A Dynamic Approach to Retrieval-Augmented Generation\n\n## Overview\n\nSelf-RAG is an advanced algorithm that combines the power of retrieval-based and generation-based approaches in natural language processing. It dynamically decides whether to use retrieved information and how to best utilize it in generating responses, aiming to produce more accurate, relevant, and useful outputs.\n\n## Motivation\n\nTraditional question-answering systems often struggle with balancing the use of retrieved information and the generation of new content. Some systems might rely too heavily on retrieved data, leading to responses that lack flexibility, while others might generate responses without sufficient grounding in factual information. Self-RAG addresses these issues by implementing a multi-step process that carefully evaluates the necessity and relevance of retrieved information, and assesses the quality of generated responses.\n\n## Key Components\n\n1. **Retrieval Decision**: Determines if retrieval is necessary for a given query.\n2. **Document Retrieval**: Fetches potentially relevant documents from a vector store.\n3. **Relevance Evaluation**: Assesses the relevance of retrieved documents to the query.\n4. **Response Generation**: Generates responses based on relevant contexts.\n5. **Support Assessment**: Evaluates how well the generated response is supported by the context.\n6. **Utility Evaluation**: Rates the usefulness of the generated response.\n\n## Method Details\n\n1. **Retrieval Decision**: The algorithm first decides if retrieval is necessary for the given query. This step prevents unnecessary retrieval for queries that can be answered directly.\n\n2. **Document Retrieval**: If retrieval is deemed necessary, the algorithm fetches the top-k most similar documents from a vector store.\n\n3. **Relevance Evaluation**: Each retrieved document is evaluated for its relevance to the query. This step filters out irrelevant information, ensuring that only pertinent context is used for generation.\n\n4. **Response Generation**: The algorithm generates responses using the relevant contexts. If no relevant contexts are found, it generates a response without retrieval.\n\n5. **Support Assessment**: Each generated response is evaluated to determine how well it is supported by the context. This step helps in identifying responses that are grounded in the provided information.\n\n6. **Utility Evaluation**: The utility of each response is rated, considering how well it addresses the original query.\n\n7. **Response Selection**: The final step involves selecting the best response based on the support assessment and utility evaluation.\n\n## Benefits of the Approach\n\n1. **Dynamic Retrieval**: By deciding whether retrieval is necessary, the system can adapt to different types of queries efficiently.\n\n2. **Relevance Filtering**: The relevance evaluation step ensures that only pertinent information is used, reducing noise in the generation process.\n\n3. **Quality Assurance**: The support assessment and utility evaluation provide a way to gauge the quality of generated responses.\n\n4. **Flexibility**: The system can generate responses with or without retrieval, adapting to the available information.\n\n5. **Improved Accuracy**: By grounding responses in relevant retrieved information and assessing their support, the system can produce more accurate outputs.\n\n## Conclusion\n\nSelf-RAG represents a sophisticated approach to question-answering and information retrieval tasks. By incorporating multiple evaluation steps and dynamically deciding on the use of retrieved information, it aims to produce responses that are not only relevant and accurate but also useful to the end-user. This method showcases the potential of combining retrieval and generation techniques in a thoughtful, evaluated manner to enhance the quality of AI-generated responses.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('<div style="text-align: center;">\n\n<img src="../images/self_rag.svg" alt="Self RAG" style="width:80%; height:auto;">\n</div>')
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
    mo.md('### Create a vector store ')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Initialize the language model\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Defining prompt templates')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Defining the self RAG logic flow')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Test the self-RAG function easy query with high relevance\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Test the self-RAG function with a more challenging query with low relevance\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--self-rag)')
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='# Install required packages\n# SETUP (run separately): !pip install langchain langchain-openai python-dotenv\n\n# Clone the repository to access helper functions and evaluation modules\n# SETUP (run separately): !git clone https://github.com/NirDiamant/RAG_TECHNIQUES.git\nimport sys\nsys.path.append(\'RAG_TECHNIQUES\')\n# If you need to run with the latest data\n# !cp -r RAG_TECHNIQUES/data .\n\nimport os\nimport sys\nfrom dotenv import load_dotenv\nfrom langchain.prompts import PromptTemplate\nfrom langchain_openai import ChatOpenAI\nfrom langchain_core.pydantic_v1 import BaseModel, Field\n\n\n# Original path append replaced for Colab compatibility\nfrom helper_functions import *\nfrom evaluation.evalute_rag import *\n\n# Load environment variables from a .env file\nload_dotenv()\n\n# Set the OpenAI API key environment variable\nos.environ["OPENAI_API_KEY"] = os.getenv(\'OPENAI_API_KEY\')\n\n# Download required data files\nimport os\nos.makedirs(\'data\', exist_ok=True)\n\n# Download the PDF document used in this notebook\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n# SETUP (run separately): !wget -O data/Understanding_Climate_Change.pdf https://raw.githubusercontent.com/NirDiamant/RAG_TECHNIQUES/main/data/Understanding_Climate_Change.pdf\n\npath = "data/Understanding_Climate_Change.pdf"\n\nvectorstore = encode_pdf(path)\n\nllm = ChatOpenAI(model="gpt-4o-mini", max_tokens=1000, temperature=0)\n\nclass RetrievalResponse(BaseModel):\n    response: str = Field(..., title="Determines if retrieval is necessary", description="Output only \'Yes\' or \'No\'.")\nretrieval_prompt = PromptTemplate(\n    input_variables=["query"],\n    template="Given the query \'{query}\', determine if retrieval is necessary. Output only \'Yes\' or \'No\'."\n)\n\nclass RelevanceResponse(BaseModel):\n    response: str = Field(..., title="Determines if context is relevant", description="Output only \'Relevant\' or \'Irrelevant\'.")\nrelevance_prompt = PromptTemplate(\n    input_variables=["query", "context"],\n    template="Given the query \'{query}\' and the context \'{context}\', determine if the context is relevant. Output only \'Relevant\' or \'Irrelevant\'."\n)\n\nclass GenerationResponse(BaseModel):\n    response: str = Field(..., title="Generated response", description="The generated response.")\ngeneration_prompt = PromptTemplate(\n    input_variables=["query", "context"],\n    template="Given the query \'{query}\' and the context \'{context}\', generate a response."\n)\n\nclass SupportResponse(BaseModel):\n    response: str = Field(..., title="Determines if response is supported", description="Output \'Fully supported\', \'Partially supported\', or \'No support\'.")\nsupport_prompt = PromptTemplate(\n    input_variables=["response", "context"],\n    template="Given the response \'{response}\' and the context \'{context}\', determine if the response is supported by the context. Output \'Fully supported\', \'Partially supported\', or \'No support\'."\n)\n\nclass UtilityResponse(BaseModel):\n    response: int = Field(..., title="Utility rating", description="Rate the utility of the response from 1 to 5.")\nutility_prompt = PromptTemplate(\n    input_variables=["query", "response"],\n    template="Given the query \'{query}\' and the response \'{response}\', rate the utility of the response from 1 to 5."\n)\n\n# Create LLMChains for each step\nretrieval_chain = retrieval_prompt | llm.with_structured_output(RetrievalResponse)\nrelevance_chain = relevance_prompt | llm.with_structured_output(RelevanceResponse)\ngeneration_chain = generation_prompt | llm.with_structured_output(GenerationResponse)\nsupport_chain = support_prompt | llm.with_structured_output(SupportResponse)\nutility_chain = utility_prompt | llm.with_structured_output(UtilityResponse)\n\ndef self_rag(query, vectorstore, top_k=3):\n    print(f"\\nProcessing query: {query}")\n    \n    # Step 1: Determine if retrieval is necessary\n    print("Step 1: Determining if retrieval is necessary...")\n    input_data = {"query": query}\n    retrieval_decision = retrieval_chain.invoke(input_data).response.strip().lower()\n    print(f"Retrieval decision: {retrieval_decision}")\n    \n    if retrieval_decision == \'yes\':\n        # Step 2: Retrieve relevant documents\n        print("Step 2: Retrieving relevant documents...")\n        docs = vectorstore.similarity_search(query, k=top_k)\n        contexts = [doc.page_content for doc in docs]\n        print(f"Retrieved {len(contexts)} documents")\n        \n        # Step 3: Evaluate relevance of retrieved documents\n        print("Step 3: Evaluating relevance of retrieved documents...")\n        relevant_contexts = []\n        for i, context in enumerate(contexts):\n            input_data = {"query": query, "context": context}\n            relevance = relevance_chain.invoke(input_data).response.strip().lower()\n            print(f"Document {i+1} relevance: {relevance}")\n            if relevance == \'relevant\':\n                relevant_contexts.append(context)\n        \n        print(f"Number of relevant contexts: {len(relevant_contexts)}")\n        \n        # If no relevant contexts found, generate without retrieval\n        if not relevant_contexts:\n            print("No relevant contexts found. Generating without retrieval...")\n            input_data = {"query": query, "context": "No relevant context found."}\n            return generation_chain.invoke(input_data).response\n        \n        # Step 4: Generate response using relevant contexts\n        print("Step 4: Generating responses using relevant contexts...")\n        responses = []\n        for i, context in enumerate(relevant_contexts):\n            print(f"Generating response for context {i+1}...")\n            input_data = {"query": query, "context": context}\n            response = generation_chain.invoke(input_data).response\n            \n            # Step 5: Assess support\n            print(f"Step 5: Assessing support for response {i+1}...")\n            input_data = {"response": response, "context": context}\n            support = support_chain.invoke(input_data).response.strip().lower()\n            print(f"Support assessment: {support}")\n            \n            # Step 6: Evaluate utility\n            print(f"Step 6: Evaluating utility for response {i+1}...")\n            input_data = {"query": query, "response": response}\n            utility = int(utility_chain.invoke(input_data).response)\n            print(f"Utility score: {utility}")\n            \n            responses.append((response, support, utility))\n        \n        # Select the best response based on support and utility\n        print("Selecting the best response...")\n        best_response = max(responses, key=lambda x: (x[1] == \'fully supported\', x[2]))\n        print(f"Best response support: {best_response[1]}, utility: {best_response[2]}")\n        return best_response[0]\n    else:\n        # Generate without retrieval\n        print("Generating without retrieval...")\n        input_data = {"query": query, "context": "No retrieval necessary."}\n        return generation_chain.invoke(input_data).response\n\nquery = "What is the impact of climate change on the environment?"\nresponse = self_rag(query, vectorstore)\n\nprint("\\nFinal response:")\nprint(response)\n\nquery = "how did harry beat quirrell?"\nresponse = self_rag(query, vectorstore)\n\nprint("\\nFinal response:")\nprint(response)', language="python", label="Recovered notebook code")
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
