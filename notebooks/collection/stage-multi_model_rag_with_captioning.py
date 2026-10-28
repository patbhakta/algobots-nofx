# /// script
# dependencies = ["langchain", "langchain-community", "pillow", "pymupdf", "python-dotenv"]
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
    This code implements one of the multiple ways of multi-model RAG. It extracts and processes text and images from PDFs, utilizing a multi-modal Retrieval-Augmented Generation (RAG) system for summarizing and retrieving content for question answering.

    ### Key Components:
       - **PyMuPDF**: For extracting text and images from PDFs.
       - **Gemini 1.5-flash model**: To summarize images and tables.
       - **Cohere Embeddings**: For embedding document splits.
       - **Chroma Vectorstore**: To store and retrieve document embeddings.
       - **LangChain**: To orchestrate the retrieval and generation pipeline.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Diagram:
       <img src="../images/multi_model_rag_with_captioning.svg" alt="Reliable-RAG" width="300">

    ### Motivation:
    Efficiently summarize complex documents to facilitate easy retrieval and concise responses for multi-modal data.

    ### Method Details:
       - Text and images are extracted from the PDF using PyMuPDF.
       - Summarization is performed on extracted images and tables using Gemini.
       - Embeddings are generated via Cohere for storage in Chroma.
       - A similarity-based retriever fetches relevant sections based on the query.

    ### Benefits:
       - Simplified retrieval from complex, multi-modal documents.
       - Streamlined Q&A process for both text and images.
       - Flexible architecture for expanding to more document types.

    ### Implementation:
       - Documents are split into chunks with overlap using a text splitter.
       - Summarized text and image content are stored as vectors.
       - Queries are handled by retrieving relevant document segments and generating concise answers.

    ### Summary:
    The project enables multi-modal document processing and retrieval, providing concise, relevant responses by combining state-of-the-art LLMs and vector-based retrieval systems.
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
    # packages added via marimo's package management: langchain langchain-community pillow pymupdf python-dotenv !pip install langchain langchain-community pillow pymupdf python-dotenv
    return


@app.cell
def _():
    import fitz  # PyMuPDF
    from PIL import Image
    import io
    import os
    from dotenv import load_dotenv

    import google.generativeai as genai
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.documents import Document
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import Chroma
    from langchain_cohere import ChatCohere, CohereEmbeddings

    load_dotenv()
    return (
        ChatCohere,
        ChatPromptTemplate,
        Chroma,
        CohereEmbeddings,
        Document,
        Image,
        RecursiveCharacterTextSplitter,
        fitz,
        genai,
        io,
        os,
    )


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
    #! mv 1706.03762 attention_is_all_you_need.pdf
    subprocess.call(['mv', '1706.03762', 'attention_is_all_you_need.pdf'])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Data Extraction
    """)
    return


@app.cell
def _():
    text_data = []
    img_data = []
    return img_data, text_data


@app.cell
def _(Image, fitz, io, os, text_data):
    with fitz.open('attention_is_all_you_need.pdf') as pdf_file:
        if not os.path.exists('extracted_images'):  # Create a directory to store the images
            os.makedirs('extracted_images')
        for page_number in range(len(pdf_file)):
            page = pdf_file[page_number]
            text = page.get_text().strip()  # Loop through every page in the PDF
            text_data.append({'response': text, 'name': page_number + 1})
            images = page.get_images(full=True)
            for image_index, _img in enumerate(images, start=0):
                xref = _img[0]  # Get the text on page
                base_image = pdf_file.extract_image(xref)
                image_bytes = base_image['image']
                image_ext = base_image['ext']  # Get the list of images on the page
                _image = Image.open(io.BytesIO(image_bytes))
                _image.save(f'extracted_images/image_{page_number + 1}_{image_index + 1}.{image_ext}')  # Loop through all images found on the page  # Get the XREF of the image  # Extract the image  # Get the image bytes  # Get the image extension  # Load the image using PIL and save it
    return


@app.cell
def _(genai, os):
    genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
    model = genai.GenerativeModel(model_name="gemini-1.5-flash")
    return (model,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Image Captioning
    """)
    return


@app.cell
def _(Image, img_data, model, os):
    for _img in os.listdir('extracted_images'):
        _image = Image.open(f'extracted_images/{_img}')
        response = model.generate_content([_image, 'You are an assistant tasked with summarizing tables, images and text for retrieval.     These summaries will be embedded and used to retrieve the raw text or table elements     Give a concise summary of the table or text that is well optimized for retrieval. Table or text or image:'])
        img_data.append({'response': response.text, 'name': _img})
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Vectostore
    """)
    return


@app.cell
def _(
    CohereEmbeddings,
    Document,
    RecursiveCharacterTextSplitter,
    img_data,
    text_data,
):
    # Set embeddings
    embedding_model = CohereEmbeddings(model="embed-english-v3.0")

    # Load the document
    docs_list = [Document(page_content=text['response'], metadata={"name": text['name']}) for text in text_data]
    img_list = [Document(page_content=img['response'], metadata={"name": img['name']}) for img in img_data]

    # Split
    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=400, chunk_overlap=50
    )

    doc_splits = text_splitter.split_documents(docs_list)
    img_splits = text_splitter.split_documents(img_list)
    return doc_splits, embedding_model, img_splits


@app.cell
def _(Chroma, doc_splits, embedding_model, img_splits):
    # Add to vectorstore
    vectorstore = Chroma.from_documents(
        documents=doc_splits + img_splits, # adding the both text and image splits
        collection_name="multi_model_rag",
        embedding=embedding_model,
    )

    retriever = vectorstore.as_retriever(
                    search_type="similarity",
                    search_kwargs={'k': 1}, # number of documents to retrieve
                )
    return (retriever,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Query
    """)
    return


@app.cell
def _():
    query = "What is the BLEU score of the Transformer (base model)?"
    return (query,)


@app.cell
def _(query, retriever):
    docs = retriever.invoke(query)
    return (docs,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Output
    """)
    return


@app.cell
def _(ChatCohere, ChatPromptTemplate, docs, query):
    from langchain_core.output_parsers import StrOutputParser

    # Prompt
    system = """You are an assistant for question-answering tasks. Answer the question based upon your knowledge.
    Use three-to-five sentences maximum and keep the answer concise."""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            ("human", "Retrieved documents: \n\n <docs>{documents}</docs> \n\n User question: <question>{question}</question>"),
        ]
    )

    # LLM
    llm = ChatCohere(model="command-r-plus", temperature=0)

    # Chain
    rag_chain = prompt | llm | StrOutputParser()

    # Run
    generation = rag_chain.invoke({"documents":docs[0].page_content, "question": query})
    print(generation)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-rag-techniques-views-tracker.cloudfunctions.net/rag-techniques-tracker?notebook=all-rag-techniques--multi-model-rag-with-captioning)
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
