# /// script
# dependencies = ["faiss-cpu", "jrag", "numpy", "sentence-transformers"]
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
    # Building a Smart Search for JSON Data: A Beginner's Guide
    Imagine you have a lot of information stored in JSON files (a common format for structured data). Standard searching might only find exact word matches. What if you want to search based on the meaning or concept behind your query, not just keywords? That's where semantic search comes in!

    This tutorial will show you how to build a simple semantic search system using your JSON data. We'll use a helpful tool called jrag to prepare the data, turn text into special numerical representations called "embeddings,
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Why Do We Need This?
    AI models we use for semantic search understand numbers much better than raw text or complex JSON structures. So, our main challenge is to convert our JSON data into meaningful text and then into these numerical representations (embeddings) that capture the text's meaning.

    While you could just flatten a whole JSON into one big string, that often includes irrelevant information. The [jRAG](https://pypi.org/project/jrag/) library helps us carefully select and combine only the important fields from our JSON into a clean text string, perfect for creating high-quality embeddings. jRAG uses [jsonpath-ng](https://pypi.org/project/jsonpath-ng/) expressions to precisely target the data you want to extract.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Installs
    """)
    return


@app.cell
def _():
    # packages added via marimo's package management: sentence-transformers faiss-cpu numpy jrag !pip install sentence-transformers faiss-cpu numpy jrag
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Imports
    """)
    return


@app.cell
def _():
    import json
    import requests
    import numpy as np
    import faiss
    from sentence_transformers import SentenceTransformer
    import time
    import jrag

    return SentenceTransformer, faiss, jrag, json, requests, time


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # JSON Data - Nobel Prizes
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Download

    Before we can process data, we need some data. This cell uses the requests library to download a sample dataset - information about Nobel Prizes - from a public web address. It then parses the downloaded JSON data into a Python variable (a dictionary containing a list called 'prizes')
    """)
    return


@app.cell
def _(json, requests):
    url = "https://api.nobelprize.org/v1/prize.json"

    try:
        # Send an HTTP GET request to the URL
        response = requests.get(url, timeout=15)
        # Check if the request was successful (status code 200)
        response.raise_for_status()
        # Parse the JSON data from the response
        data = response.json()

        print("Successfully fetched and parsed JSON data.")

        if isinstance(data, dict) and 'prizes' in data and isinstance(data['prizes'], list):
             print(f"Number of events found: {len(data['prizes'])}")
             if len(data['prizes']) > 0:
                  print("\nFirst 3 records:\n", json.dumps(data['prizes'][:3], indent=2))
        else:
             print("The data structure might be different than expected.")

    except requests.exceptions.Timeout:
        print(f"The request to {url} timed out.")
    except requests.exceptions.ConnectionError as e:
        print(f"Could not connect to {url}. Please check the URL and your connection.")
        print(f"Error details: {e}")
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error occurred: {e.response.status_code} {e.response.reason}")
    except requests.exceptions.RequestException as e:
        print(f"Error during requests to {url}: {e}")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON. The response might not be valid JSON.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    return (data,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Data processing

    In this specific dataset, Nobel laureates (winners) might have their first and last names in separate fields (`firstname`, `surname`). For better searching, this cell loops through the prize data. For each laureate, it checks if both name fields exist and combines them into a single `full_name` field. It also handles cases where the full name might already be in the firstname field or if names are missing. This makes the name information more consistent for `jrag` to process later.
    """)
    return


@app.cell
def _(data):
    prizes_lst = data['prizes']

    for prize_info in prizes_lst:
        laureates_list = prize_info.get('laureates', [])

        # Iterate through each laureate dictionary in the laureates list
        for laureate in laureates_list:
            # Check if both firstname and surname exist before combining
            if 'firstname' in laureate and 'surname' in laureate:
                # Create the full name string using an f-string
                first_name = laureate['firstname']
                last_name = laureate['surname']
                full_name = f"{first_name} {last_name}"

                # Add the new 'full_name' key-value pair to the laureate dictionary
                laureate['full_name'] = full_name
            # Some instances have the full name in the firstname field
            elif 'surname' not in laureate and len(laureate['firstname'].split(' ')) > 1:
                laureate['full_name'] = laureate['firstname']
            else:
                # Optional: Handle cases where names might be missing
                print(f"Warning: Missing 'firstname' or 'surname' for laureate ID {laureate.get('id', 'N/A')}:\n")
    return (prizes_lst,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Text to be embed
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Single Example

    This cell demonstrates how `jrag` works on a single JSON record before we apply it to all of them.

    1. `jrag_config` Dictionary: We define a Python dictionary called `jrag_config`. The keys of this dictionary are descriptive labels (like 'Year', 'Category', 'Laureats', 'Motivation'). The values are special strings called `jsonpath-ng` expressions (e.g., `$.year`, `$.laureates[*].full_name`). These expressions tell jrag exactly where to find the corresponding data within the JSON structure. For instance, `$.laureates[*].full_name` means "go into the 'laureates' list, look at every item (*), and get the 'full_name' field from each."
    2. `jrag.to_text()`: We take the first Nobel prize record (first_record) and pass it, along with our jrag_config, to the `jrag.to_text()` function.
    3. Output: This function extracts the data specified by the config, formats it nicely using the labels we provided (e.g., "Year: 2023, Category: Physics, ..."), and combines it into a single text string (example_text). This string is what we would potentially turn into an embedding. The cell prints this example text and the original JSON it came from, so you can see the transformation.
    """)
    return


@app.cell
def _(jrag, json, prizes_lst):
    first_record = prizes_lst[0]
    _jrag_config = {'Year': '$.year', 'Category': '$.category', 'Laureats': '$.laureates[*].full_name', 'Motivation': '$.laureates[0].motivation'}
    example_text = jrag.to_text(first_record, _jrag_config)
    print(f'Text to embed:\n"{example_text}"')
    print('\nBuilt from:')
    print(json.dumps(first_record, indent=2))  # Here we only return the motivation field of the first instance ($.laureates[0]) as they're all the same
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Add to all records

    We now run the same process over all records in the JSON using `jrag.tag_list`
    """)
    return


@app.cell
def _(jrag, prizes_lst):
    _jrag_config = {'Year': '$.year', 'Category': '$.category', 'Laureats': '$.laureates[*].full_name', 'Motivation': '$.laureates[0].motivation'}
    prizes_tagged_lst = jrag.tag_list(prizes_lst, _jrag_config)
    # Inspect first example
    print(prizes_tagged_lst[0]['jrag_text'])
    return (prizes_tagged_lst,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Build corpus

    We need two things to proceed: the text we want to embed and a way to link back to the original data. This cell creates two lists:

    1. `corpus_texts`: It loops through our `prizes_tagged_lst`. For each item, it takes the text string stored in the 'jrag_text' key and adds it to the `corpus_texts` list. This list will be fed into the embedding model.
    2. `corpus_metadat`a: At the same time, it adds the entire original JSON object (which now includes the 'jrag_text') to the corpus_metadata list. This list runs parallel to `corpus_texts`. So, the first text in corpus_texts corresponds to the first JSON object in corpus_metadata, the second text to the second JSON, and so on. This link is crucial for retrieving the full JSON details after finding a match using the embeddings.
    """)
    return


@app.cell
def _(prizes_tagged_lst):
    # Extract the text content and keep track of original data reference
    # We store the original index to map FAISS results back to our JSON objects
    corpus_texts = []
    corpus_metadata = []  # To store original dicts or just IDs
    for _i, item in enumerate(prizes_tagged_lst):
        jrag_text = item.get('jrag_text')
        if jrag_text and isinstance(jrag_text, str):
            corpus_texts.append(jrag_text)
            corpus_metadata.append({'original_index': _i, 'data': item})  # Store the original item or just its ID for later retrieval
        else:  # Storing the whole item is easier for this example
            print(f"Warning: Item at index {_i} is missing 'content' key or it's not a string. Skipping.")
    if not corpus_texts:
        print('Error: No valid text content found in the JSON data.')
        exit()
    print(f'Loaded {len(corpus_texts)} items with text content.')
    return corpus_metadata, corpus_texts


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Generate embeddings

    This is where the magic of semantic understanding happens.

    1. Load Model: We specify the name of a pre-trained model (all-MiniLM-L6-v2 is a popular choice – good balance of speed and accuracy) and load it using SentenceTransformer(MODEL_NAME). Downloading the model might take a moment the first time.
    2. `model.encode()`: We pass our list of text strings (corpus_texts) to the model's encode method. The model processes each string and converts it into a high-dimensional vector (a list of numbers, often 384 numbers long for this specific model) that represents its meaning. convert_to_numpy=True ensures the output is in a format (numpy arrays) suitable for the next step. show_progress_bar=True gives visual feedback as it can take time for large datasets.
    3. `corpus_embeddings`: The result is stored in `corpus_embeddings`, which is essentially a list where each item is an embedding vector corresponding to a text string in corpus_texts.
    4. `.astype('float32')`: We convert the embeddings to a specific numerical type (float32) because the FAISS library (our next step) requires it.
    """)
    return


@app.cell
def _(SentenceTransformer, corpus_texts, time):
    # --- Configuration ---
    MODEL_NAME = 'all-MiniLM-L6-v2'  # A good & fast general-purpose model
    print(f"Loading Sentence Transformer model '{MODEL_NAME}'...")
    # --- 2. Load Sentence Transformer Model ---
    _start_time = time.time()
    model = SentenceTransformer(MODEL_NAME)
    _end_time = time.time()
    print(f'Model loaded in {_end_time - _start_time:.2f} seconds.')
    print('Generating embeddings for the corpus...')
    _start_time = time.time()
    # --- 3. Generate Embeddings ---
    corpus_embeddings = model.encode(corpus_texts, convert_to_numpy=True, show_progress_bar=True)
    _end_time = time.time()
    # Ensure convert_to_numpy=True for FAISS compatibility
    print(f'Embeddings generated in {_end_time - _start_time:.2f} seconds.')
    corpus_embeddings = corpus_embeddings.astype('float32')
    embedding_dim = corpus_embeddings.shape[1]
    # FAISS requires float32 type
    # Get the dimensionality of embeddings (required by FAISS)
    print(f'Embedding dimension: {embedding_dim}')
    return corpus_embeddings, embedding_dim, model


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Build FAISS Index

    Now we organize our embeddings for efficient searching.

    1. `faiss.IndexFlatL2(embedding_dim)`: We create a simple FAISS index called IndexFlatL2. `embedding_dim` is the number of dimensions in our embeddings (e.g., 384, which we got from the shape of corpus_embeddings in the previous step). L2 refers to the distance metric (Euclidean distance) it will use to compare vectors – basically, how "far apart" their meanings are. "Flat" means it will perform an exhaustive search, comparing the query to every item, which is fine for smaller datasets but might be slow for millions of items (FAISS has more advanced index types for huge datasets).
    2. `index.add(corpus_embeddings)`: We add all our generated corpus_embeddings to the FAISS index. The index now stores these vectors in an optimized way.
    """)
    return


@app.cell
def _(corpus_embeddings, embedding_dim, faiss):
    # --- 4. Build FAISS Index ---
    # Using IndexFlatL2 - simple baseline, performs exhaustive search
    # L2 distance = Euclidean distance
    print("Building FAISS index (IndexFlatL2)...")
    index = faiss.IndexFlatL2(embedding_dim)

    # --- 5. Add Embeddings to Index ---
    print(f"Adding {len(corpus_embeddings)} embeddings to the index...")
    index.add(corpus_embeddings)
    print(f"Index contains {index.ntotal} vectors.")
    return (index,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Query

    This is where we use the system we've built!

    1. `query_text`: Define the search query as a plain text string.
    2. Encode Query: Use the exact same loaded Sentence Transformer model (model.encode([query_text], ...)) to convert the query text into its own embedding vector. It needs to be in the same "embedding space" as the corpus embeddings for the comparison to be meaningful.
    3. `index.search()`: Use the FAISS index's search method. We provide the query embedding and the desired number of results (NUM_NEIGHBORS). FAISS quickly compares the query embedding to all the embeddings in the index and finds the NUM_NEIGHBORS closest ones based on the L2 distance. It returns two things: distances (how close each match is – lower is better) and indices (the positions/indices of the matches in the original list that we added to FAISS).
    4. Display Results:
    Loop through the returned indices.
    For each index idx returned by FAISS, use it to look up the corresponding original data in our corpus_metadata list (remember, we kept them in the same order!). This gives us back the full JSON object for the match.
    Print the rank (1st, 2nd, 3rd match), the distance score, and details from the retrieved JSON object.

    This final step shows the semantic search in action, retrieving the Nobel prize records that are most contextually relevant to the meaning of your search query, not just keyword matches.
    """)
    return


@app.cell
def _(corpus_metadata, index, model, time):
    # --- 6. Prepare and Perform Search ---
    query_text = 'Breakthrough in medicine or physiology'
    NUM_NEIGHBORS = 5  # How many similar items to retrieve
    print(f"\nPerforming search for query: '{query_text}'")
    print(f'Finding top {NUM_NEIGHBORS} similar items...')
    _start_time = time.time()
    query_embedding = model.encode([query_text], convert_to_numpy=True)
    # Generate embedding for the query
    query_embedding = query_embedding.astype('float32')
    _end_time = time.time()
    print(f'Query embedding generated in {_end_time - _start_time:.2f} seconds.')
    _start_time = time.time()
    distances, indices = index.search(query_embedding, NUM_NEIGHBORS)
    _end_time = time.time()
    # Perform the search
    print(f'Search completed in {_end_time - _start_time:.4f} seconds.')
    # The search function returns distances and indices (IDs) of neighbors
    # query_embedding needs to be 2D array (even if it's just one query)
    print('\nSearch Results:')
    print('--------------')
    if not indices[0].size:
        print('No results found.')
    # --- 7. Display Results ---
    else:
        for _i, idx in enumerate(indices[0]):
            original_item_info = corpus_metadata[idx]
    # indices[0] contains the results for the first (and only) query
    # distances[0] contains the corresponding distances
            original_item = original_item_info['data']
            distance = distances[0][_i]
            print(f'Rank {_i + 1}:')
            print(f'  Distance: {distance:.4f}')
            print(f"  ID: {original_item.get('id', 'N/A')}")  # Map the index `idx` from FAISS back to our original data
            print(f"  Category: {original_item.get('category', 'N/A')}")  # This works because we added embeddings in the same order as corpus_metadata
            print(f'  Content: {original_item}')
            print('-' * 10)
    return



@app.cell(hide_code=True)
def _():
    import marimo as _studio_mo
    studio_notes = _studio_mo.ui.text_area(label="Research notes", placeholder="Record parameters, observations and follow-up questions")
    _studio_mo.vstack([_studio_mo.md("### Research notebook"), studio_notes])
    return (studio_notes,)

if __name__ == "__main__":
    app.run()
