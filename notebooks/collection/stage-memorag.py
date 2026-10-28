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
    mo.md('<div style="text-align:center; font-size:32px; font-weight:bold; line-height:1.2;">\n    MemoRAG: Enhancing Retrieval-Augmented Generation<br>\n    with Memory Models\n</div>\n\n## Overview\nMemoRAG is a Retrieval-Augmented Generation (RAG) framework that incorporates a memory model as an auxiliary step before the retrieval phase. In doing so, it bridges the gap in contextual understanding and reasoning that standard RAG techniques face when addressing queries with implicit or ambiguous information needs and unstructured external knowledge.\n\n## Motivation\nStandard RAG techniques rely heavily on lexical or semantic matching between the query and the knowledge base. While this approach works well for clear question answering tasks with structured knowledge, it often falls short when handling queries with implicit or ambiguous information (e.g., describing the relationships between main characters in a novel) or when the knowledge base is unstructured (e.g., fiction books). In such cases, lexical or semantic matching seldom produces the desired outputs.\n\n## Key Components\n1. **Memory**: A compressed representation of the database created by a long-context model, designed to handle and summarize extensive inputs efficiently.\n2. **Retriever**: A standard RAG retrieval model responsible for selecting relevant context from the knowledge base to support the generator.\n3. **Generator**: A generative language model that produces responses by combining the query with the retrieved context, similar to standard RAG setups.\n\n## Method Details\n### 1. Memory\n- The memory module serves as an auxiliary component to enhance the retriever’s ability to identify better matches between queries and relevant parts of the database. It takes the original query and the database as inputs and produces staging answers — intermediate outputs like clues, surrogate queries, or key points — which the retriever uses instead of the original query.\n- Long-term memory is constructed by running a long-context model, such as Qwen2-7B-Instruct or Mistral-7B-Instruct-v0.2, over the entire database. This process generates a compressed representation of the database through an attention mechanism.\n- The compressed representation is stored as key-value pairs (kv-cache), facilitating efficient and accurate retrieval.\n- Released memory models include memorag-qwen2-7b-inst and memorag-mistral-7b-inst, derived from Qwen2-7B-Instruct and Mistral-7B-Instruct-v0.2, respectively.\n\n### 2. Retriever\n- The retriever is a standard retrieval model, adapted to take processed queries (created by the memory module as staging answers) instead of the original query.\n- It outputs the retrieved **context**, which serves as the basis for generating the final answer.\n\n\n### 3. Generator\n- The generator produces the final response by combining the retriever’s output (retrieved context) with the original query.\n- MemoRAG ensures compatibility and consistency by using the memory module’s underlying model as the default generator.\n\n## Benefits of the Approach\n1. **Extended Scope of Queries:** MemoRAG\'s preprocessing capabilities enable it to handle complex and long-context tasks that conventional RAG methods struggle with.\n\n2. **Improved Accuracy:** By simplifying and adjusting queries before retrieval, MemoRAG enhances performance over standard RAG methods.\n\n3. **Flexibility:** Adapts to diverse tasks, datasets, and retrieval scenarios.\n\n4. **Robustness:** Improved performance remains consistent across various generators, datasets, and query types.\n\n5. **Efficiency**: The use of key-value compression reduces computational overhead.\n\n## Conclusion\nThe memory module in MemoRAG significantly enhances comprehension of both the queries and the database, enabling more effective retrieval. Its ability to preprocess queries, generate staging answers, and leverage long-context memory models ensures high-quality responses, making MemoRAG a significant step forward in the evolution of retrieval-augmented generation.\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('<div style="text-align: center;">\n\n<img src="../images/memo_rag.svg" alt="MemoRAG" style="width:100%; height:auto;">\n</div>')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Implementation')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Imports')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### OpenAI Setup for querying GPT's API")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Memory Module Classes')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('#### Helper classes\nUsed for initial memorization')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('#### MemoryStore\nA class for memory creation and knowledge extraction from it when necessary.\n<br>\nOnce memory is established, the updated retrieval queries can be created from it.\n<br>\nNote that the obtained memory can be saved for future use.\n<br>\nBelow are prompts that are used in the memorization / retrieval queries creation, and then the class itself.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('A system prompt for assigning the model with the role of an expert of memorization')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('A prompt instructing the LLM about the process of memory creation')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('A system prompt for assigning the model with the role of an expert for creating queries for info retrieval')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('A prompt guiding the LLM on how to find clues in the memory that can help answer the given question')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('A prompt guiding the LLM on how to create surrogate (helper) queries from memory')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('The Memory Class - as mentioned above it can "memorize" the text by creating kv pairs, and later on creating adjusted queries that, in turn, will be transferred to the retrieval model')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Retrieval Function\nFor extracting relevant context for generation')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("### Generation Function\nFor getting the final answer using the original user's query + context obtained by the retrieval function")
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Query Processing Function\n\nfor executing the whole pipeline, creating retrival queries from memory, using these queries to retrieve from the DB (vectorstore)\n\nthe relevant context which in turn is used for generating the final response to the query\n')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Initialize Components')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Memorize document chunks and save memory into a file\nNote: this cell might run for a long time and take quite a lot of the tokens credit, so be careful.\nOnce done, the memory is saved into a file, and then you can use it for as many queries as you like.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Usage Examples')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Loading the saved memory')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Running some queries')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Comparison between MemorRAG and Simple RAG.\n#### Will be done for both short context and long context')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Importing the evaluation functions')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Simple RAG Short Context')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Using the climate_vectorstore created above')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('The evaluate_rag function takes questions from the climate change q_a file, generates answers with Simple RAG and then compares them to the ground truth answers from the q_a file.\nIt then evaluates the quality of Simple RAG responses using an LLM by 3 criteria:\n1. Correctness - plain comparison between the final answers and how much they match\n2. Faithfulness - checks if the generated answers indeed align with the retrieved context\n3. Context Relevancy - checks if the retrieved context from the vectorstore is indeed relevant for the given query')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### MemoRAG Short Context')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('An adjustment of the original evaluate_rag function to MemoRAG.\nNote that one of the parameters here is the memory_store.\nSince the part of generating answers with MemoRAG might be costly, it allows using pre-saved results if they exist.\nAnother advantage of use_saved_results is the option to use results from original MemoRAG run made in Colab.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Running evaluate_memo_rag on the same climate change q_a as above')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Long Context - the book "The Wealth of Nations" by Adam Smith\nTaken from Project Gutenberg.\n<br>\nContains ~600 pages.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('#### Initialize Components')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Memorize document chunks and save memory into a file\nNote: this cell might run for a long time and take quite a lot of the tokens credit, so be careful.\nOnce done, the memory is saved into a file, and then you can use it for as many queries as you like.')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Loading the saved memory')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Simple RAG Long Context')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Using the wealth_vectorstore created above')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Using the evaluate_rag function on the q_a file for the long book')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### MemoRAG Long Context')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Using the adjusted evaluate_memo_rag function on the q_a file for the long book')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('## Evaluate original MemoRAG Long Context')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('Original MemoRAG is rather heavy and had to be run on Colab with an A100 GPU.\nIts answers to the questions from the Smith q_a file are in the following cell')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md('### Initialize components')
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md("Using the adjusted evaluate_memo_rag function on the q_a file for the long book with original MemoRAG's answers")
    return

@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value='import os\nimport pandas as pd\nfrom dotenv import load_dotenv\nfrom langchain_community.embeddings import OpenAIEmbeddings\nfrom openai import OpenAI\nfrom helper_functions import *\n\nload_dotenv()\nclient = OpenAI(api_key=os.getenv(\'OPENAI_API_KEY\'))\n\nclass KeyValuePair(BaseModel):\n    """ The key-value pairs are the "holders" of memory\n        The keys are topics from the relevant article and the values are details about that topic """\n    topic: str\n    details: str\n\nclass MemoryResponse(BaseModel):\n    """ The obtained memory is a list of topic-details pairs """\n    pairs: List[KeyValuePair]\n\nmemory_store_system_prompt = """\n    You are an expert at extracting structured key-value pairs from text.\n    "Identify key topics, entities, or questions and pair them with relevant, detailed information.\n    "Ensure the output is well-structured, avoiding redundancy while preserving meaning.\n    """\n\nmemory_store_kv_cache_prompt = """\n    You are provided with a long article, chunk by chunk. Read each chunk carefully and extract key topics and their detailed information.\n    For each key topic:\n    1. Identify the main concept, entity, or potential question\n    2. Provide the corresponding detailed information or answer\n\n    Note: the aim is to mimic kv cache memory creation\n\n    Now, the article begins:\n    {document}\n\n    The article ends here.\n\n    RESPONSE FORMAT IS IMPORTANT. You must return a JSON object with the following structure:\n    {{\n        "pairs": [\n            {{\n                "topic": "topic1",\n                "details": "details1"\n            }},\n            {{\n                "topic": "topic2",\n                "details": "details2"\n            }}\n        ]\n    }}\n    """\n\nsystem_prompt_for_queries_creation = "You are an expert in information retrieval. Your task is to extract specific and relevant information from the provided context to help answer the given question."\n\nmemorag_span_prompt_for_queries_creation = """\n    You are given a question related to an article. To answer it effectively, you need to use specific details from the article. You are not provided with the whole article. Instead, you are provided with specific and relevant information from it.\n     Your task is to identify and extract one or more specific clue texts from the provided information that are relevant to the question.\n\n    ### Question: {question}\n    ### Information: {relevant_info}\n    ### Instructions:\n    1. You have a general understanding of the provided information. Your task is to generate one or more specific clues that will help in searching for supporting evidence within the article.\n    2. The clues are in the form of text spans that will assist in answering the question.\n    3. Only output the clues. If there are multiple clues, separate them with a newline.\n    """\n\nmemorag_sur_prompt_for_queries_creation = """\n    You are given a question related to an article. To answer it effectively, you need to use specific details from the article.  You are not provided with the whole article. Instead, you are provided with specific and relevant information from it.\n    Your task is to generate precise clue questions that can help locate the necessary information for answering the question.\n\n    ### Question: {question}\n    ### Information: {relevant_info}\n    ### Instructions:\n    1. You have a general understanding of the provided information. Your task is to generate one or more specific clues that will help in searching for supporting evidence within the article.\n    2. The clues are in the form of precise surrogate questions that clarify the original question.\n    3. Only output the clues. If there are multiple clues, separate them with a newline.\n    """\n\nclass MemoryStore:\n    """The MemoryStore class is a realization of the Memory Module discussed in the paper.\n    Its \'memorize\' method is used to create a prompt cache mimicking a key-value compression of the original text (database).\n    This cache can then be used by the \'create_retrieval_prompt\' method for creating the processed query to be used later for retrieval"""\n\n    def __init__(self):\n        self.embeddings = OpenAIEmbeddings()\n        self.store = None\n        self.processed_count = 0\n        self.json_parse_failures = 0\n        self._last_parse_used_fallback = False\n\n\n    def memorize(self, document: str):\n        """Process document into key-value pairs and store them"""\n        system_prompt = memory_store_system_prompt\n        kv_cache_prompt = memory_store_kv_cache_prompt\n        print(f"Processing chunk {self.processed_count + 1}...")\n\n        response = client.chat.completions.create(\n            model="gpt-4o-mini", # 4o or o1 should be considered\n            messages=[\n                {"role": "system", "content": system_prompt},\n                {"role": "user", "content": kv_cache_prompt.format(document=document)}\n            ],\n            response_format={"type": "json_object"},\n            seed=42  # For reproducibility\n        )\n\n        pairs = self._parse_into_pairs(response.choices[0].message.content)\n        if hasattr(self, \'json_parse_failures\') and self._last_parse_used_fallback:\n            self.json_parse_failures += 1\n            if self.json_parse_failures > 0 and self.json_parse_failures % 5 == 0:\n               print(f"Warning: JSON parsing has failed {self.json_parse_failures} times")\n\n        print(\'*\'*20)\n        print(f\'first extracted pairs: {pairs[0:3]}\\n\\n\')\n\n        # Batch process pairs\n        texts = []\n        metadatas = []\n\n        for topic, details in pairs:\n            if not topic or not details:  # Skip empty pairs\n                continue\n\n            combined_text = f"Topic: {topic}\\nDetails: {details}"\n            texts.append(combined_text)\n            metadatas.append({"topic": topic})\n        print(\'*\'*20)\n        print(f\'num of extracted texts: {len(texts)}\\n\\n\')\n        if self.store is None:\n            self.store = FAISS.from_texts(texts, self.embeddings, metadatas=metadatas)\n        else:\n            existing_docs = self.store.similarity_search("")\n            existing_topics = {doc.metadata.get("topic") for doc in existing_docs}\n\n            # Filter out duplicates\n            new_texts = []\n            new_metadatas = []\n            for text, metadata in zip(texts, metadatas):\n                if metadata["topic"] not in existing_topics:\n                    new_texts.append(text)\n                    new_metadatas.append(metadata)\n\n            if new_texts:\n                self.store.add_texts(new_texts, metadatas=new_metadatas)\n\n        self.processed_count += 1\n        print(f"Processed {self.processed_count} chunks so far\\n\\n")\n\n    def _parse_into_pairs(self, content: str):\n        """Used when LLM returned a valid JSON"""\n        self._last_parse_used_fallback = False\n        try:\n            # Parse JSON and validate with Pydantic\n            data = json.loads(content)\n            validated_data = MemoryResponse(**data)\n            return [(pair.topic, pair.details) for pair in validated_data.pairs]\n        except (json.JSONDecodeError, ValueError) as e:\n            print(f"Error parsing response: {e}")\n            # Fall back to text parsing if JSON fails\n            self._last_parse_used_fallback = True\n            return self._parse_text_into_pairs(content)\n\n    def _parse_text_into_pairs(self, text: str):\n        """Original text parsing method as fallback\n        Used when LLM did not return a valid JSON"""\n        pairs = []\n        lines = text.split(\'\\n\')\n        current_topic = None\n        current_details = []\n\n        for line in lines:\n            if line.startswith(\'Topic:\'):\n                if current_topic:  # Save previous pair\n                    pairs.append((current_topic, \' \'.join(current_details)))\n                current_topic = line[6:].strip()\n                current_details = []\n            elif line.startswith(\'Details:\'):\n                current_details.append(line[8:].strip())\n            elif current_details:  # Continue adding to details if already started\n                current_details.append(line.strip())\n\n        # Add the last pair\n        if current_topic:\n            pairs.append((current_topic, \' \'.join(current_details)))\n\n        return pairs\n\n    def create_retrieval_queries(self, query: str) -> str | None:\n        """Generate staging answers y = Θ_mem(q, D | θ_mem)\n        This should provide rough clues/outline to guide context retrieval"""\n\n        if not self.store:\n            return None\n\n        ## consider increasing k to more than 10. maybe try even top 30% or something\n        results = self.store.similarity_search_with_score(query, k=min(10, self.store.index.ntotal))\n        relevant_info = [\n            f"Topic: {doc.metadata[\'topic\']}\\nDetails: {doc.page_content}"\n            for doc, _ in results\n        ]\n\n        memorag_span_prompt = memorag_span_prompt_for_queries_creation\n        memorag_sur_prompt = memorag_sur_prompt_for_queries_creation\n        system_prompt = system_prompt_for_queries_creation\n\n        text_spans = client.chat.completions.create(\n            model="gpt-4o-mini",\n            messages=[\n                {"role": "system", "content": system_prompt},\n                {"role": "user", "content": memorag_span_prompt.format(question=query, relevant_info = relevant_info)}\n            ]\n        ).choices[0].message.content\n        surrogate_queries = client.chat.completions.create(\n            model="gpt-4o-mini",\n            messages=[\n                {"role": "system", "content": system_prompt},\n                {"role": "user", "content": memorag_sur_prompt.format(question=query, relevant_info = relevant_info)}\n            ],\n            temperature=0.5  # Allow for some creativity in generating clues\n        ).choices[0].message.content\n\n        retrieval_query = text_spans.split("\\n") + surrogate_queries.split("\\n")\n        retrieval_query = [q for q in retrieval_query if len(q.split()) > 3]\n        retrieval_query.append(query)\n\n        return retrieval_query\n\n    def save_store(self, path: str):\n        if self.store:\n            self.store.save_local(path)\n\n    def load_store(self, path: str):\n        self.store = FAISS.load_local(path, self.embeddings, allow_dangerous_deserialization=True)\n\ndef retrieve_context(retrieval_query: str, vectorstore, k: int = 3) -> List[str]:\n    """Retrieve relevant context using the staging answer and the database vectorstore.\n    Implements c = Γ(y, D | γ) from the paper"""\n\n    results = vectorstore.similarity_search(retrieval_query, k=k)\n    contexts = [doc.page_content for doc in results]\n\n    return contexts\n\ndef generate_answer(query: str, contexts: List[str], temperature: float = 0) -> str:\n    """Generate final answer y = Θ(q, c | θ)"""\n    prompt = f"""Based ONLY on the provided context, answer the query.\n\nQuery: {query}\n\nContext:\n{\' \'.join(contexts)}\n\nProvide a clear and concise answer based solely on the information in the context. If the context doesn\'t contain sufficient information to fully answer the query, clearly state that the necessary information is not available in the provided context rather than using any external knowledge.\n"""\n\n    response = client.chat.completions.create(\n        model="gpt-4o-mini",\n        messages=[\n            {"role": "system", "content": "You are an expert in generating answers from given text. Provide clear, concise answers."},\n            {"role": "user", "content": prompt}\n        ],\n        temperature=temperature,\n        max_tokens=500\n    )\n\n    return response.choices[0].message.content\n\ndef process_query(query: str, memory_store, vectorstore):\n    print(\'*\'*20)\n    print("\\nProcessing Query:", query)\n    print("=" * 50)\n\n    # y = Θ_mem(q, D | θ_mem)\n    retrieval_queries = memory_store.create_retrieval_queries(query)\n    print(\'*\'*20)\n    print(f"\\n\\nRetrieval Queries:\\n{retrieval_queries}\\n\\n")\n\n    # c = Γ(y, D | γ)\n    all_contexts = []\n    for retrieval_query in retrieval_queries:\n        contexts = retrieve_context(retrieval_query, vectorstore, k=3)\n        all_contexts.extend(contexts)\n\n    unique_contexts = list(dict.fromkeys(all_contexts))  # Preserves order\n    print(\'*\'*20)\n    print(f"Retrieved Context Example: {unique_contexts[0]}\\n\\n")\n\n    # y = Θ(q, c | θ)\n    final_answer = generate_answer(query, unique_contexts)\n    print(\'*\'*20)\n    print(f"\\nFinal Answer: {final_answer}")\n\n    return unique_contexts, final_answer\n\n# Initialize vector store\npath = "../data/Understanding_Climate_Change.pdf"\nclimate_vectorstore = encode_pdf(path, chunk_size=1000, chunk_overlap=200)\n\n# # Initialize memory store\nclimate_memory_store = MemoryStore()\n\n# loader = PyPDFLoader(path)\n# documents = loader.load()\n# document_text = \'\\n\'.join([doc.page_content for doc in documents])\n# climate_memory_store.memorize(document_text)\n# climate_memory_store.save_store("../data/Understanding_Climate_Change_Memory_Store.faiss")\n\nclimate_memory_store.load_store("../data/Understanding_Climate_Change_Memory_Store.faiss")\n\nquery_1 = "What are the impacts of climate change on biodiversity?"\nquery_2 = "Please summarize the climate change article"\nquery_3 = "Describe the social and economic influence of climate change."\n\nfor query in [query_1, query_2, query_3]:\n    process_query(query, climate_memory_store, climate_vectorstore)\n\nfrom evaluation.evalute_rag import *\n\nchunks_query_retriever = climate_vectorstore.as_retriever(search_kwargs={"k": 2})\n\nevaluate_rag(chunks_query_retriever, q_a_file_name = "../data/q_a.json")\n\ndef evaluate_memo_rag(memory_store = None,vectorstore = None, num_questions: int = 5,\n                      q_a_file_name = "../data/q_a.json",\n                      use_saved_results=True,\n                      use_original_memorag=False,\n                      original_memorag_answers=None,\n                      original_memorag_retrievals=None\n                      )-> None:\n    """\n    Evaluate the MemoRAG system using predefined metrics.\n\n    Args:\n        memory_store: MemoryStore object containing the memory model.\n        vectorstore: FAISS vector store containing the encoded document chunks.\n        num_questions (int): Number of questions to evaluate (default: 5).\n        q_a_file_name (str): Path to the JSON file containing questions and answers (default: "../data/q_a.json").\n        use_saved_results (bool): Whether to load previously saved results or to save generated results to disk.\n        use_original_memorag (bool): Whether to use paper\'s MemoRAG results or simplified MemoRAG implementation from this notebook.\n        original_memorag_answers: Pre-generated answers to use in case use_original_memorag=True.\n        original_memorag_retrievals: Pre-generated retrievals to use in case use_original_memorag=True.\n    """\n    q_a_file_name = q_a_file_name\n    with open(q_a_file_name, "r", encoding="utf-8") as json_file:\n        q_a = json.load(json_file)\n\n    questions = [qa["question"] for qa in q_a][:num_questions]\n    ground_truth_answers = [qa["answer"] for qa in q_a][:num_questions]\n\n    if use_original_memorag:\n        """Results of the original MemoRAG were created externally and loaded here"""\n        generated_answers = original_memorag_answers\n        retrieved_documents = original_memorag_retrievals\n        print("Using original MemoRAG results")\n    else:\n        """When evaluating results of the MemoRAG implementation in this notebook\n        there are 2 options - either using pre-saved results or generating new ones\n        full_results_path is used either to load pre-saved results or for saving\n        the results in case of generation"""\n        q_a_file_base = os.path.splitext(q_a_file_name)[0]\n        results_path_suffix = "saved_evaluation_results"\n        full_results_path = f"{q_a_file_base}_{results_path_suffix}.json"\n\n        if use_saved_results and os.path.exists(full_results_path):\n            with open(full_results_path, "r", encoding="utf-8") as f:\n                saved_data = json.load(f)\n                generated_answers = saved_data["generated_answers"]\n                retrieved_documents = saved_data["retrieved_documents"]\n            print(f"Loaded previously saved results from {full_results_path}")\n        else:\n            if memory_store is None or vectorstore is None:\n                raise ValueError("memory_store and vectorstore are required when not using saved results or original MemoRAG")\n\n            # Generate answers and retrieve documents for each question\n            generated_answers = []\n            retrieved_documents = []\n            for question in questions:\n                contexts, result = process_query(question, memory_store, vectorstore)\n                retrieved_documents.append(contexts)\n                generated_answers.append(result)\n\n            with open(full_results_path, "w", encoding="utf-8") as f:\n                json.dump({\n                    "generated_answers": generated_answers,\n                    "retrieved_documents": retrieved_documents\n                }, f, ensure_ascii=False, indent=2)\n            print(f"Saved results to {full_results_path}")\n\n    # Create test cases and evaluate\n    test_cases = create_deep_eval_test_cases(questions, ground_truth_answers, generated_answers, retrieved_documents)\n    evaluate(\n        test_cases=test_cases,\n        metrics=[correctness_metric, faithfulness_metric, relevance_metric],\n        throttle_value = 5,\n        run_async = False,\n        ignore_errors = True\n    )\n\nevaluate_memo_rag(q_a_file_name = "../data/q_a.json", memory_store=climate_memory_store, vectorstore = climate_vectorstore, use_saved_results=False)\n\n# Initialize vector store\npath = "../data/The_Wealth_of_Nations_Project_Gutenberg.pdf"\nwealth_vectorstore = encode_pdf(path, chunk_size=1000, chunk_overlap=200)\n\n# Initialize memory store\nwealth_memory_store = MemoryStore()\n\n# # Memorize document chunks and save memory into a file\n# loader = PyPDFLoader(path)\n# documents = loader.load()\n# document_text = \'\\n\'.join([doc.page_content for doc in documents])\n\n# # Split document into smaller chunks\n# text_splitter = RecursiveCharacterTextSplitter(\n#     chunk_size=50000,\n#     chunk_overlap=5000\n# )\n# chunks = text_splitter.split_text(document_text)\n#\n# # Memorize each chunk\n# for chunk in chunks:\n#     wealth_memory_store.memorize(chunk)\n# wealth_memory_store.save_store("../data/The_Wealth_of_Nations_Project_Gutenberg_Memory_Store_Long_Context.faiss")\n\nwealth_memory_store.load_store("../data/The_Wealth_of_Nations_Project_Gutenberg_Memory_Store_Long_Context.faiss")\n\nchunks_query_retriever = wealth_vectorstore.as_retriever(search_kwargs={"k": 2})\n\nevaluate_rag(chunks_query_retriever, num_questions = 15, q_a_file_name = "../data/q_a_smith_short.json")\n\nevaluate_memo_rag(num_questions=15, q_a_file_name = "../data/q_a_smith_short.json", memory_store= wealth_memory_store, vectorstore = wealth_vectorstore, use_saved_results=False)\n\noriginal_memorag_answers_wealth = ["Adam Smith",\n"The invisible hand refers to the self-interested actions of individuals in a free market economy that unintentionally lead to economic outcomes.",\n"Land, labor, and capital.",\n"Labor determines the value of goods through the quantity of labor required to produce them.",\n"Adam Smith argues that while individuals act in their self-interest, this pursuit often benefits society more effectively than if they acted solely for personal gain. He illustrates this through examples like trade, where individuals acting in their self-interest actually facilitate economic growth and prosperity for society as a whole.",\n"Smith justifies taxation as necessary for the defense of the state, the maintenance of public order, and the provision of public services.",\n"Supply and demand determine prices. When supply exceeds demand, prices tend to fall; when demand exceeds supply, prices tend to rise.",\n"The division of labor encourages workers to focus on specific tasks, leading to innovation in tools and methods. This innovation enhances productivity and has long-term economic impacts by increasing the quantity of goods produced and the efficiency of production processes.",\n"Smith viewed agriculture as the primary source of wealth, while manufacturing contributed less significantly.",\n"Foreign trade enhances domestic wealth by allowing countries to specialize in producing goods where they have a comparative advantage. This specialization leads to increased efficiency and productivity. Smith\'s \'invisible hand\' refers to the self-interested actions of individuals and businesses that, despite their self-interest, ultimately contribute to economic growth and efficiency.",\n"Capital accumulation increases the quantity of productive labor by enabling more workers to be employed. This leads to a division of labor where each worker specializes in a specific task, enhancing efficiency and productivity.",\n"Challenges include the need for security, the complexity of international transactions, and the potential for fraud and corruption.",\n"Value is the amount of labor required to produce a good or service.",\n"Smith believed that government should not interfere with the natural division of labor, allowing individuals to specialize in their areas of expertise. He argued that government\'s role is to protect property rights, ensure justice, and provide public works and institutions that facilitate economic growth.",\n"Free trade benefits consumers by lowering prices, increasing product variety, and enhancing economic efficiency.",\n"Adam Smith argued that monopolies, whether natural or artificial, are inherently detrimental to society and the economy. They stifle competition, lead to higher prices, and reduce overall economic efficiency. Smith believed that monopolies are a form of corruption and that the benefits they confer on a few at the expense of many are unjust. He advocated for free trade and competition as essential to economic prosperity and social justice"\n]\n\ncsv_path = "../data/wealth_retrieved_passages_from_original_memorag.csv"\ndf = pd.read_csv(csv_path, dtype=str, keep_default_na=False)\n\n# Convert to a 2D list\noriginal_memorag_retrievals_wealth = df.values.tolist()\n\nevaluate_memo_rag(num_questions=15, q_a_file_name = "../data/q_a_smith_short.json", memory_store= wealth_memory_store, vectorstore = wealth_vectorstore, use_saved_results=True, use_original_memorag=True, original_memorag_answers=original_memorag_answers_wealth, original_memorag_retrievals=original_memorag_retrievals_wealth)\n\n', language="python", label="Recovered notebook code")
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
