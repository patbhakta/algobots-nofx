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
    ![pageindex_banner](https://pageindex.ai/static/images/pageindex_banner.jpg)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    <div align="center">
    <i>Reasoning-based RAG&nbsp; ◦ &nbsp;No Vector DB&nbsp; ◦ &nbsp;No Chunking&nbsp; ◦ &nbsp;Human-like Retrieval</i>

    </div>

    <div align="center">

      <a href="https://vectify.ai">🏠 Homepage</a>&nbsp; • &nbsp;
      <a href="https://chat.pageindex.ai">💻 Chat</a>&nbsp; • &nbsp;
      <a href="https://pageindex.ai/mcp">🔌 MCP</a>&nbsp; • &nbsp;
      <a href="https://docs.pageindex.ai/quickstart">📚 API</a>&nbsp; • &nbsp;
      <a href="https://github.com/VectifyAI/PageIndex">📦 GitHub</a>&nbsp; • &nbsp;
      <a href="https://discord.com/invite/VuXuf29EUj">💬 Discord</a>&nbsp; • &nbsp;
      <a href="https://ii2abc2jejf.typeform.com/to/tK3AXl8T">✉️ Contact</a>&nbsp;

    </div>

    <div align="center">

    [![Star us on GitHub](https://img.shields.io/github/stars/VectifyAI/PageIndex?style=for-the-badge&logo=github&label=⭐️%20Star%20Us)](https://github.com/VectifyAI/PageIndex) &nbsp;&nbsp; [![Follow us on X](https://img.shields.io/badge/Follow%20Us-000000?style=for-the-badge&logo=x&logoColor=white)](https://twitter.com/VectifyAI)

    </div>

    ---
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    > Check out our blog post, "[Do We Still Need OCR?](https://pageindex.ai/blog/do-we-need-ocr)", for a more detailed discussion.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # A Vision-based, Vectorless RAG System for Long Documents
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    In modern document question answering (QA) systems, Optical Character Recognition (OCR) serves an important role by converting PDF pages into text that can be processed by Large Language Models (LLMs). The resulting text can provide contextual input that enables LLMs to perform question answering over document content.

    Traditional OCR systems typically use a two-stage process that first detects the layout of a PDF — dividing it into text, tables, and images — and then recognizes and converts these elements into plain text. With the rise of vision-language models (VLMs) (such as [Qwen-VL](https://github.com/QwenLM/Qwen3-VL) and [GPT-4.1](https://openai.com/index/gpt-4-1/)), new end-to-end OCR models like [DeepSeek-OCR](https://github.com/deepseek-ai/DeepSeek-OCR) have emerged. These models jointly understand visual and textual information, enabling direct interpretation of PDFs without an explicit layout detection step.

    However, this paradigm shift raises an important question:

    > **If a VLM can already process both the document images and the query to produce an answer directly, do we still need the intermediate OCR step?**

    In this notebook, we give a practical implementation of a vision-based question-answering system for long documents, without relying on OCR. Specifically, we use PageIndex as a reasoning-based retrieval layer and OpenAI's multimodal GPT-4.1 as the VLM for visual reasoning and answer generation.

    See the original [blog post](https://pageindex.ai/blog/do-we-need-ocr) for a more detailed discussion on how VLMs can replace traditional OCR pipelines in document question-answering.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 📝 Notebook Overview

    This notebook demonstrates a *minimal*, **vision-based vectorless RAG** pipeline for long documents with PageIndex, using only visual context from PDF pages. You will learn how to:
    - [x] Build a PageIndex tree structure of a document
    - [x] Perform reasoning-based retrieval with tree search
    - [x] Extract PDF page images of retrieved tree nodes for visual context
    - [x] Generate answers using VLM with PDF image inputs only (no OCR required)

    > ⚡ Note: This example uses PageIndex's reasoning-based retrieval with OpenAI's multimodal GPT-4.1 model for both tree search and visual context reasoning.

    ---
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Step 0: Preparation

    This notebook demonstrates **Vision-based RAG** with PageIndex, using PDF page images as visual context for retrieval and answer generation.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    #### 0.1 Install PageIndex
    """)
    return


@app.cell
def _():
    # '%pip install -q --upgrade pageindex requests openai PyMuPDF' command supported automatically in marimo
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    #### 0.2 Setup PageIndex
    """)
    return


@app.cell
def _():
    from pageindex import PageIndexClient
    import pageindex.utils as utils

    # Get your PageIndex API key from https://dash.pageindex.ai/api-keys
    PAGEINDEX_API_KEY = "YOUR_PAGEINDEX_API_KEY"
    pi_client = PageIndexClient(api_key=PAGEINDEX_API_KEY)
    return pi_client, utils


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    #### 0.3 Setup VLM

    Choose your preferred VLM — in this notebook, we use OpenAI's multimodal GPT-4.1 as the VLM.
    """)
    return


@app.cell
def _():
    import openai, fitz, base64, os

    # Setup OpenAI client
    OPENAI_API_KEY = "YOUR_OPENAI_API_KEY"

    async def call_vlm(prompt, image_paths=None, model="gpt-4.1"):
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        messages = [{"role": "user", "content": prompt}]
        if image_paths:
            content = [{"type": "text", "text": prompt}]
            for image in image_paths:
                if os.path.exists(image):
                    with open(image, "rb") as image_file:
                        image_data = base64.b64encode(image_file.read()).decode('utf-8')
                        content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}"
                            }
                        })
            messages[0]["content"] = content
        response = await client.chat.completions.create(model=model, messages=messages, temperature=0)
        return response.choices[0].message.content.strip()

    return call_vlm, fitz, os


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    #### 0.4 PDF Image Extraction Helper Functions
    """)
    return


@app.cell
def _(fitz, os):
    def extract_pdf_page_images(pdf_path, output_dir="pdf_images"):
        os.makedirs(output_dir, exist_ok=True)
        pdf_document = fitz.open(pdf_path)
        page_images = {}
        total_pages = len(pdf_document)
        for page_number in range(len(pdf_document)):
            page = pdf_document.load_page(page_number)
            # Convert page to image
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better quality
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("jpeg")
            image_path = os.path.join(output_dir, f"page_{page_number + 1}.jpg")
            with open(image_path, "wb") as image_file:
                image_file.write(img_data)
            page_images[page_number + 1] = image_path
            print(f"Saved page {page_number + 1} image: {image_path}")
        pdf_document.close()
        return page_images, total_pages

    def get_page_images_for_nodes(node_list, node_map, page_images):
        # Get PDF page images for retrieved nodes
        image_paths = []
        seen_pages = set()
        for node_id in node_list:
            node_info = node_map[node_id]
            for page_num in range(node_info['start_index'], node_info['end_index'] + 1):
                if page_num not in seen_pages:
                    image_paths.append(page_images[page_num])
                    seen_pages.add(page_num)
        return image_paths

    return extract_pdf_page_images, get_page_images_for_nodes


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Step 1: PageIndex Tree Generation
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    #### 1.1 Submit a document for generating PageIndex tree
    """)
    return


@app.cell
def _(extract_pdf_page_images, os, pi_client):
    import requests
    pdf_url = 'https://arxiv.org/pdf/1706.03762.pdf'
    # You can also use our GitHub repo to generate PageIndex tree
    # https://github.com/VectifyAI/PageIndex
    pdf_path = os.path.join('../data', pdf_url.split('/')[-1])
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)  # the "Attention Is All You Need" paper
    response = requests.get(pdf_url)
    with open(pdf_path, 'wb') as f:
        f.write(response.content)
    print(f'Downloaded {pdf_url}\n')
    print('Extracting page images...')
    page_images, total_pages = extract_pdf_page_images(pdf_path)
    print(f'Extracted {len(page_images)} page images from {total_pages} total pages.\n')
    doc_id = pi_client.submit_document(pdf_path)['doc_id']
    # Extract page images from PDF
    print('Document Submitted:', doc_id)
    return doc_id, page_images, total_pages


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    #### 1.2 Get the generated PageIndex tree structure
    """)
    return


@app.cell
def _(doc_id, pi_client, utils):
    if pi_client.is_retrieval_ready(doc_id):
        tree = pi_client.get_tree(doc_id, node_summary=True)['result']
        print('Simplified Tree Structure of the Document:')
        utils.print_tree(tree, exclude_fields=['text'])
    else:
        print("Processing document, please try again later...")
    return (tree,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Step 2: Reasoning-Based Retrieval with Tree Search
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    #### 2.1 Reasoning-based retrieval with PageIndex to identify nodes that might contain relevant context
    """)
    return


@app.cell
async def _(call_vlm, tree, utils):
    import json

    query = "What is the last operation in the Scaled Dot-Product Attention figure?"

    tree_without_text = utils.remove_fields(tree.copy(), fields=['text'])

    search_prompt = f"""
    You are given a question and a tree structure of a document.
    Each node contains a node id, node title, and a corresponding summary.
    Your task is to find all tree nodes that are likely to contain the answer to the question.

    Question: {query}

    Document tree structure:
    {json.dumps(tree_without_text, indent=2)}

    Please reply in the following JSON format:
    {{
        "thinking": "<Your thinking process on which nodes are relevant to the question>",
        "node_list": ["node_id_1", "node_id_2", ..., "node_id_n"]
    }}
    Directly return the final JSON structure. Do not output anything else.
    """

    tree_search_result = await call_vlm(search_prompt)
    return json, query, tree_search_result


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    #### 2.2 Print retrieved nodes and reasoning process
    """)
    return


@app.cell
def _(json, total_pages, tree, tree_search_result, utils):
    node_map = utils.create_node_mapping(tree, include_page_ranges=True, max_page=total_pages)
    tree_search_result_json = json.loads(tree_search_result)

    print('Reasoning Process:\n')
    utils.print_wrapped(tree_search_result_json['thinking'])

    print('\nRetrieved Nodes:\n')
    for node_id in tree_search_result_json["node_list"]:
        node_info = node_map[node_id]
        node = node_info['node']
        start_page = node_info['start_index']
        end_page = node_info['end_index']
        page_range = start_page if start_page == end_page else f"{start_page}-{end_page}"
        print(f"Node ID: {node['node_id']}\t Pages: {page_range}\t Title: {node['title']}")
    return node_map, tree_search_result_json


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    #### 2.3 Get corresponding PDF page images of retrieved nodes
    """)
    return


@app.cell
def _(
    get_page_images_for_nodes,
    node_map,
    page_images,
    tree_search_result_json,
):
    retrieved_nodes = tree_search_result_json["node_list"]
    retrieved_page_images = get_page_images_for_nodes(retrieved_nodes, node_map, page_images)
    print(f'\nRetrieved {len(retrieved_page_images)} PDF page image(s) for visual context.')
    return (retrieved_page_images,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Step 3: Answer Generation
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    #### 3.1 Generate answer using VLM with visual context
    """)
    return


@app.cell
async def _(call_vlm, query, retrieved_page_images, utils):
    # Generate answer using VLM with only PDF page images as visual context
    answer_prompt = f"""
    Answer the question based on the images of the document pages as context.

    Question: {query}

    Provide a clear, concise answer based only on the context provided.
    """

    print('Generated answer using VLM with retrieved PDF page images as visual context:\n')
    answer = await call_vlm(answer_prompt, retrieved_page_images)
    utils.print_wrapped(answer)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Conclusion

    In this notebook, we demonstrated a *minimal* **vision-based, vectorless RAG pipeline** using PageIndex and a VLM. The system retrieves relevant pages by reasoning over the document’s hierarchical tree index and answers questions directly from PDF images — no OCR required.

    If you’re interested in building your own **reasoning-based document QA system**, try [PageIndex Chat](https://chat.pageindex.ai), or integrate via [PageIndex MCP](https://pageindex.ai/mcp) and the [API](https://docs.pageindex.ai/quickstart). You can also explore the [GitHub repo](https://github.com/VectifyAI/PageIndex) for open-source implementations and additional examples.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    © 2025 [Vectify AI](https://vectify.ai)
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
