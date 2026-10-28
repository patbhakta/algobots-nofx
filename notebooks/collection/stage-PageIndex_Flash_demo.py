# /// script
# dependencies = ["pageindex"]
# ///

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
    # PageIndex Flash Demo

    This notebook demonstrates how to use the PageIndex local SDK to build vectorless RAG for a document.

    PageIndex Flash is the default tree-indexing model used by the PageIndex client in local mode.

    Learn more about PageIndex integrations in the [documentation](https://docs.pageindex.ai/).

    PageIndex Flash is fully open-source. You can find it in the [PageIndex GitHub repository](https://github.com/VectifyAI/PageIndex).
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Prepare a document
    """)
    return


@app.cell
def _():
    import requests
    url = 'https://arxiv.org/pdf/2607.24653'
    file_name = 'kimi_report.pdf'
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(file_name, 'wb') as f:
            for _chunk in response.iter_content(chunk_size=8192):  # Raise an exception for bad status codes (4xx or 5xx)
                f.write(_chunk)
        print(f"Successfully downloaded '{file_name}'")
    except requests.exceptions.RequestException as e:
        print(f'Error downloading the report: {e}')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Install PageIndex SDK
    """)
    return


@app.cell
def _():
    # packages added via marimo's package management: pageindex !pip install -U pageindex
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Choose your index and chat model
    """)
    return


@app.cell
def _():
    import os
    from pageindex import PageIndexClient

    os.environ["OPENAI_API_KEY"] = "Your OpenAI API key here"

    client = PageIndexClient(
        index="gpt-5.6-luna",
        chat="gpt-5.6-sol",
    )
    return (client,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Index a document
    """)
    return


@app.cell
def _(client):
    doc_id = client.submit_document("kimi_report.pdf")["doc_id"]
    print("Tree index generation successfully,  the document id is", doc_id)
    return (doc_id,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Ask a query
    """)
    return


@app.cell
def _(client, doc_id):
    for _chunk in client.chat('What benchmarks have been tested?', doc_id=doc_id, stream=True):
        print(_chunk, end='', flush=True)
    return



@app.cell(hide_code=True)
def _():
    import marimo as _studio_mo
    studio_notes = _studio_mo.ui.text_area(label="Research notes", placeholder="Record parameters, observations and follow-up questions")
    _studio_mo.vstack([_studio_mo.md("### Research notebook"), studio_notes])
    return (studio_notes,)

if __name__ == "__main__":
    app.run()
