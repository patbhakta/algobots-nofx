# /// script
# dependencies = ["auto-gptq", "base64", "bitsandbytes", "byaldi", "flash-attn", "optimum", "os", "pillow", "python-dotenv", "qwen-vl-utils", "ragmultimodalmodel", "transformers @ git+https://github.com/huggingface/transformers.git"]
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
    ### Overview:
    This code implements one of the multiple ways of multi-model RAG. This project processes a PDF file, retrieves relevant content using Colpali, and generates answers using a multi-modal RAG system. The process includes document indexing, querying, and summarizing with the Gemini model.

    ### Key Components:
    - **RAGMultiModalModel**: Used for document indexing and retrieval.
    - **PDF Processing**: Downloads and processes "Attention is All You Need" paper.
    - **Gemini Model**: Used for content generation from retrieved images and queries.
    - **Base64 Encoding/Decoding**: Manages image data retrieved during search.

    ### Diagram:
       <img src="../images/multi_model_rag_with_colpali.svg" alt="Reliable-RAG" width="300">

    ### Motivation:
    To enable efficient querying and content generation from multi-modal documents (PDFs with text and images) in response to natural language queries.

    ### Method Details:
    - Indexing: The PDF is indexed using the `RAGMultiModalModel`, storing both text and image data.
    - Querying: Natural language queries retrieve relevant document segments.
    - Image Processing: Images from the document are decoded, displayed, and used in conjunction with the Gemini model to generate content.

    ### Benefits:
    - Multi-modal support for both text and images.
    - Streamlined retrieval and summarization pipeline.
    - Flexible content generation using advanced LLMs (Gemini model).

    ### Implementation:
    - PDF is indexed, and the content is split into text and image segments.
    - A query is run against the indexed document to fetch the relevant results.
    - Retrieved image data is decoded and passed through the Gemini model for answer generation.

    ### Summary:
    This project integrates document indexing, retrieval, and content generation in a multi-modal setting, enabling efficient queries on complex documents like research papers.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Setup
    """)
    return


@app.cell
def _():
    # Install required packages
    # packages added via marimo's package management: pillow python-dotenv !pip install pillow python-dotenv
    return


@app.cell
def _():
    # packages added via marimo's package management: git+https://github.com/huggingface/transformers.git qwen-vl-utils flash-attn optimum auto-gptq bitsandbytes !pip install -q git+https://github.com/huggingface/transformers.git qwen-vl-utils flash-attn optimum auto-gptq bitsandbytes
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
    # packages added via marimo's package management: base64 byaldi os ragmultimodalmodel !pip install base64 byaldi os ragmultimodalmodel
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
    # packages added via marimo's package management: byaldi !pip install byaldi
    return


@app.cell
def _():
    import base64
    import os
    os.environ["HF_token"] = 'your-huggingface-api-key' # to download the ColPali model
    from byaldi import RAGMultiModalModel

    return RAGMultiModalModel, base64


@app.cell
def _(RAGMultiModalModel):
    RAG = RAGMultiModalModel.from_pretrained("vidore/colpali-v1.2", verbose=1)
    return (RAG,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Download the "Attention is all you need" paper
    """)
    return


@app.cell
def _(subprocess):
    #! wget https://arxiv.org/pdf/1706.03762
    subprocess.call(['wget', 'https://arxiv.org/pdf/1706.03762'])
    #! mkdir docs
    subprocess.call(['mkdir', 'docs'])
    #! mv 1706.03762 docs/attention_is_all_you_need.pdf
    subprocess.call(['mv', '1706.03762', 'docs/attention_is_all_you_need.pdf'])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Indexing
    """)
    return


@app.cell
def _(RAG):
    RAG.index(
        input_path="./docs/attention_is_all_you_need.pdf",
        index_name="attention_is_all_you_need",
        store_collection_with_index=True, # set this to false if you don't want to store the base64 representation
        overwrite=True
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Query time
    """)
    return


@app.cell
def _():
    query = "What is the BLEU score of the Transformer (base model)?"
    return (query,)


@app.cell
def _(RAG, query):
    results = RAG.search(query, k=1)
    return (results,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Actual image data
    """)
    return


@app.cell
def _(base64, results):
    image_bytes = base64.b64decode(results[0].base64)
    return (image_bytes,)


@app.cell
def _(image_bytes):
    filename = 'image.jpg'  # I assume you have a JPG file
    with open(filename, 'wb') as f:
      f.write(image_bytes)
    return (filename,)


@app.cell
def _(display, filename):
    from IPython.display import Image

    display(Image(filename))
    return (Image,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Test using gemini-1.5-flash
    """)
    return


@app.cell
def _():
    import google.generativeai as genai

    genai.configure(api_key='your-api-key')
    model = genai.GenerativeModel(model_name="gemini-1.5-flash")
    return (model,)


@app.cell
def _(Image, filename):
    image = Image.open(filename)
    return (image,)


@app.cell
def _(image, model, query):
    response = model.generate_content([image, query])
    print(response.text)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--multi-model-rag-with-colpali)
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
