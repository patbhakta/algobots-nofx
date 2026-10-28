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
    <p align="center">Reasoning-based RAG&nbsp; ◦ &nbsp;No Vector DB&nbsp; ◦ &nbsp;No Chunking&nbsp; ◦ &nbsp;Human-like Retrieval</p>

    <p align="center">
      <a href="https://vectify.ai">🏠 Homepage</a>&nbsp; • &nbsp;
      <a href="https://chat.pageindex.ai">🖥️ Platform</a>&nbsp; • &nbsp;
      <a href="https://docs.pageindex.ai/quickstart">📚 API Docs</a>&nbsp; • &nbsp;
      <a href="https://github.com/VectifyAI/PageIndex">📦 GitHub</a>&nbsp; • &nbsp;
      <a href="https://discord.com/invite/VuXuf29EUj">💬 Discord</a>&nbsp; • &nbsp;
      <a href="https://ii2abc2jejf.typeform.com/to/tK3AXl8T">✉️ Contact</a>&nbsp;
    </p>

    <div align="center">

    [![Star us on GitHub](https://img.shields.io/github/stars/VectifyAI/PageIndex?style=for-the-badge&logo=github&label=⭐️%20Star%20Us)](https://github.com/VectifyAI/PageIndex) &nbsp;&nbsp; [![Follow us on X](https://img.shields.io/badge/Follow%20Us-000000?style=for-the-badge&logo=x&logoColor=white)](https://twitter.com/VectifyAI)

    </div>

    ---
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Agentic Retrieval with PageIndex Chat API

    Similarity-based RAG based on Vector-DB has shown big limitations in recent AI applications, reasoning-based or agentic retrieval has become important in current developments. However, unlike classic RAG pipeine with embedding input, top-K chunks returns, re-rank, what should a agentic-native retreival API looks like?

    For an agentic-native retrieval system, we need the ability to prompt for retrieval just as naturally as you interact with ChatGPT. Below, we provide an example of how the PageIndex Chat API enables this style of prompt-driven retrieval.

    ## PageIndex Chat API
    [PageIndex Chat](https://chat.pageindex.ai/) is a AI assistant that allow you chat with multiple super-long documents without worrying about limited context or context rot problem. It is based on [PageIndex](https://pageindex.ai/blog/pageindex-intro), a vectorless reasoning-based RAG framework which gives more transparent and reliable results like a human expert.
    <div align="center">
      <img src="https://docs.pageindex.ai/images/cookbook/vectorless-rag.png" width="70%">
    </div>

    You can now access PageIndex Chat with API or SDK.

    ## 📝 Notebook Overview

    This notebook demonstrates a simple, minimal example of agentic retrieval with PageIndex. You will learn:
    - [x] How to use PageIndex Chat API.
    - [x] How to prompt the PageIndex Chat to make it a retrieval system
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Install PageIndex SDK
    """)
    return


@app.cell
def _():
    # '%pip install -q --upgrade pageindex' command supported automatically in marimo
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Setup PageIndex
    """)
    return


@app.cell
def _():
    from pageindex import PageIndexClient

    # Get your PageIndex API key from https://dash.pageindex.ai/api-keys
    PAGEINDEX_API_KEY = "YOUR_PAGEINDEX_API_KEY"
    pi_client = PageIndexClient(api_key=PAGEINDEX_API_KEY)
    return (pi_client,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Upload a document
    """)
    return


@app.cell
def _(pi_client):
    import os, requests

    pdf_url = "https://arxiv.org/pdf/2507.13334.pdf"
    pdf_path = os.path.join("../data", pdf_url.split('/')[-1])
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

    response = requests.get(pdf_url)
    with open(pdf_path, "wb") as f:
        f.write(response.content)
    print(f"Downloaded {pdf_url}")

    doc_id = pi_client.submit_document(pdf_path)["doc_id"]
    print('Document Submitted:', doc_id)
    return (doc_id,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Check the processing status
    """)
    return


@app.cell
def _(doc_id, pi_client):
    from pprint import pprint

    doc_info = pi_client.get_document(doc_id)
    pprint(doc_info)

    if doc_info['status'] == 'completed':
      print(f"\n Document ready! ({doc_info['pageNum']} pages)")
    elif doc_info['status'] == 'processing':
      print("\n Document is still processing. Please wait and check again.")
    return (pprint,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Ask a question about this document
    """)
    return


@app.cell
def _(doc_id, pi_client):
    query = 'What are the evaluation methods used in this paper?'
    for _chunk in pi_client.chat_completions(messages=[{'role': 'user', 'content': query}], doc_id=doc_id, stream=True):
        print(_chunk, end='', flush=True)
    return (query,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Agentic Retrieval with PageIndex Chat API

    You can now easily prompt the PageIndex Chat API to be a retrieval assistant.
    """)
    return


@app.cell
def _(doc_id, pi_client, query):
    retrieval_prompt = f"""\nYour job is to retrieve the raw relevant content from the document based on the user's query.\n\nQuery: {query}\n\nReturn in JSON format:\n```json\n[\n  {{\n    "page": <number>,\n    "content": "<raw text>"\n  }},\n  ...\n]\n```\n"""
    full_response = ''
    for _chunk in pi_client.chat_completions(messages=[{'role': 'user', 'content': retrieval_prompt}], doc_id=doc_id, stream=True):
        print(_chunk, end='', flush=True)
        full_response += _chunk
    return (full_response,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Extract the JSON retreived results
    """)
    return


@app.cell
def _(full_response, pprint):
    # '%pip install -q jsonextractor' command supported automatically in marimo
    def extract_json(content):
        from json_extractor import JsonExtractor
        start_idx = content.find('```json')
        if start_idx != -1:
            start_idx += 7
            end_idx = content.rfind('```')  # Adjust index to start after the delimiter
            json_content = content[start_idx:end_idx].strip()
        return JsonExtractor.extract_valid_json(json_content)
    pprint(extract_json(full_response))
    return



@app.cell(hide_code=True)
def _():
    import marimo as _studio_mo
    studio_notes = _studio_mo.ui.text_area(label="Research notes", placeholder="Record parameters, observations and follow-up questions")
    _studio_mo.vstack([_studio_mo.md("### Research notebook"), studio_notes])
    return (studio_notes,)

if __name__ == "__main__":
    app.run()
