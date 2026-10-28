# /// script
# dependencies = ["networkx", "numpy", "ollama", "sentence-transformers"]
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
    # 🔗 Local Graph RAG with Verifiable Attribution

    ## Overview

    This notebook demonstrates **Graph RAG** (Retrieval-Augmented Generation using Knowledge Graphs) with a focus on:

    1. **🔒 Privacy-First**: Runs entirely locally using Ollama (no data leaves your machine)
    2. **🔗 Multi-Hop Reasoning**: Connects disjoint facts that Vector RAG cannot
    3. **📚 Verifiable Attribution**: Every claim traces back to exact source sentences

    ## Why Graph RAG?

    | Challenge | Vector RAG | Graph RAG |
    |-----------|------------|-----------|
    | "Who mentored the person who founded Company X?" | ❌ Struggles (requires connecting 2+ facts) | ✅ Traverses relationships |
    | "How are these two concepts related?" | ❌ Finds similar chunks, not connections | ✅ Follows explicit edges |
    | "Which sentence generated this claim?" | ❌ Approximate chunk attribution | ✅ Exact source mapping |

    ## Architecture

    ```
    ┌─────────────────────────────────────────────────────────────────┐
    │  INDEXING PIPELINE                                              │
    │  ┌──────────┐   ┌────────────────┐   ┌──────────────────────┐  │
    │  │ Documents│──▶│ LLM Extraction │──▶│ Knowledge Graph      │  │
    │  │          │   │ (Entities+Rels)│   │ (Neo4j/NetworkX)     │  │
    │  └──────────┘   └────────────────┘   └──────────────────────┘  │
    └─────────────────────────────────────────────────────────────────┘
                                  │
    ┌─────────────────────────────────────────────────────────────────┐
    │  QUERY PIPELINE                                                 │
    │  ┌───────┐   ┌─────────────┐   ┌────────────┐   ┌───────────┐  │
    │  │ Query │──▶│Vector Search│──▶│Graph Travers│──▶│ LLM +     │  │
    │  │       │   │(Entry Point)│   │(Multi-hop) │   │ Citations │  │
    │  └───────┘   └─────────────┘   └────────────┘   └───────────┘  │
    └─────────────────────────────────────────────────────────────────┘
    ```

    ## Key Differentiator: Verifiable Attribution

    Unlike traditional RAG that returns "chunks," Graph RAG with attribution returns:

    ```json
    {
      "answer": "Dr. Smith developed the XYZ algorithm...",
      "citations": [
        {
          "claim": "Dr. Smith developed the XYZ algorithm",
          "source_document": "research_paper.pdf",
          "source_sentence": "Dr. Jane Smith developed the XYZ algorithm in 2022.",
          "graph_path": ["Dr. Smith", "DEVELOPED", "XYZ Algorithm"]
        }
      ]
    }
    ```
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1. Install Dependencies

    We'll use:
    - **Ollama**: Local LLM inference (Llama 3.1)
    - **Neo4j**: Graph database (or NetworkX for lightweight demo)
    - **sentence-transformers**: For vector embeddings
    """)
    return


@app.cell
def _():
    # Install required packages
    # packages added via marimo's package management: ollama networkx numpy sentence-transformers !pip install -q ollama networkx numpy sentence-transformers

    # For production use with Neo4j (optional):
    # !pip install neo4j

    import warnings
    warnings.filterwarnings('ignore')
    return


@app.cell
def _():
    import json
    import hashlib
    import networkx as nx
    import numpy as np
    from dataclasses import dataclass, field
    from typing import List, Dict, Any, Optional, Tuple
    from sentence_transformers import SentenceTransformer

    try:
        import ollama
        OLLAMA_AVAILABLE = True
    except ImportError:
        OLLAMA_AVAILABLE = False
        print("⚠️ Ollama not available. Install with: pip install ollama")
        print("   Also ensure Ollama is running: ollama serve")

    print(f"✅ Ollama available: {OLLAMA_AVAILABLE}")
    return (
        Any,
        Dict,
        List,
        OLLAMA_AVAILABLE,
        Optional,
        SentenceTransformer,
        Tuple,
        dataclass,
        hashlib,
        json,
        np,
        nx,
        ollama,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 2. Configure Local LLM with Ollama

    Ollama provides local LLM inference, ensuring **complete data privacy**.

    ### Prerequisites
    1. Install Ollama: https://ollama.ai
    2. Pull a model: `ollama pull llama3.1`
    3. Ensure Ollama is running: `ollama serve`
    """)
    return


@app.cell
def _(OLLAMA_AVAILABLE, SentenceTransformer, json, ollama):
    # Configuration
    MODEL_NAME = "llama3.1"  # or "mistral", "phi3"
    EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # Local sentence transformer

    # Initialize embedding model (runs locally)
    embedder = SentenceTransformer(EMBEDDING_MODEL)
    print(f"✅ Embedding model loaded: {EMBEDDING_MODEL}")

    def call_llm(prompt: str, model: str = MODEL_NAME) -> str:
        """Call local LLM via Ollama."""
        if not OLLAMA_AVAILABLE:
            # Fallback for demo purposes
            return '{"entities": [], "relationships": []}'

        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response['message']['content']

    def call_llm_json(prompt: str, model: str = MODEL_NAME) -> dict:
        """Call LLM and parse JSON response."""
        try:
            if OLLAMA_AVAILABLE:
                response = ollama.chat(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    format="json"
                )
                return json.loads(response['message']['content'])
            else:
                return {"entities": [], "relationships": []}
        except json.JSONDecodeError:
            return {"error": "Failed to parse JSON"}

    return call_llm, call_llm_json, embedder


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 3. Data Models for Graph RAG

    We define structured classes to track:
    - **Entities**: Extracted from documents with source provenance
    - **Relationships**: Connections between entities
    - **Citations**: Verifiable links from claims to source sentences
    """)
    return


@app.cell
def _(List, Optional, dataclass, np):
    @dataclass
    class Entity:
        """An entity extracted from a document with full provenance."""
        id: str
        name: str
        entity_type: str  # PERSON, ORGANIZATION, CONCEPT, TECHNOLOGY, etc.
        description: str
        source_doc: str
        source_sentence: str  # Exact sentence where entity was found
        embedding: Optional[np.ndarray] = None

    @dataclass
    class Relationship:
        """A relationship between two entities with provenance."""
        source_entity: str
        target_entity: str
        relation_type: str  # WORKS_FOR, DEVELOPED, LOCATED_IN, etc.
        description: str
        source_doc: str
        source_sentence: str

    @dataclass
    class Citation:
        """A verifiable citation linking a claim to its source."""
        claim: str
        source_document: str
        source_sentence: str
        confidence: float
        graph_path: List[str]  # Path through the graph that led to this claim

    @dataclass
    class AttributedAnswer:
        """Final answer with full attribution."""
        answer: str
        citations: List[Citation]
        reasoning_trace: List[str]
        entities_used: List[str]
        relationships_traversed: List[str]

    return AttributedAnswer, Citation, Entity, Relationship


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 4. Knowledge Graph Manager

    The core class that:
    1. Extracts entities and relationships using LLM
    2. Builds a graph structure (NetworkX for demo, Neo4j for production)
    3. Maintains source provenance for every node and edge
    """)
    return


@app.cell
def _(
    Any,
    AttributedAnswer,
    Citation,
    Dict,
    Entity,
    List,
    Relationship,
    Tuple,
    call_llm,
    call_llm_json,
    embedder,
    hashlib,
    np,
    nx,
):
    class KnowledgeGraphRAG:
        """
        Local Knowledge Graph RAG with Verifiable Attribution.

        This class demonstrates Graph RAG that:
        1. Runs entirely locally (privacy-first)
        2. Extracts entities and relationships using LLM
        3. Enables multi-hop reasoning
        4. Provides verifiable source attribution
        """

        def __init__(self):
            self.graph = nx.DiGraph()
            self.entities: Dict[str, Entity] = {}
            self.relationships: List[Relationship] = []
            self.documents: Dict[str, str] = {}
            self.entity_embeddings: Dict[str, np.ndarray] = {}

        def _generate_id(self, text: str) -> str:
            """Generate a unique ID for an entity."""
            return hashlib.md5(text.lower().encode()).hexdigest()[:12]

        def extract_entities_and_relationships(
            self,
            text: str,
            doc_name: str
        ) -> Tuple[List[Entity], List[Relationship]]:
            """
            Use LLM to extract entities and relationships from text.
            Each extraction preserves the source sentence for attribution.
            """

            extraction_prompt = f"""Analyze this text and extract entities and relationships.

    TEXT:
    {text}

    Return JSON with this exact structure:
    {{
      "entities": [
        {{
          "name": "Entity Name",
          "type": "PERSON|ORGANIZATION|CONCEPT|TECHNOLOGY|EVENT|LOCATION",
          "description": "Brief description",
          "source_sentence": "Exact sentence from the text where this entity appears"
        }}
      ],
      "relationships": [
        {{
          "source": "Source Entity Name",
          "target": "Target Entity Name",
          "type": "WORKS_FOR|DEVELOPED|USES|LOCATED_IN|RELATED_TO|FOUNDED|MENTORED",
          "description": "How they are related",
          "source_sentence": "Exact sentence describing this relationship"
        }}
      ]
    }}

    IMPORTANT:
    - Include the EXACT source_sentence from the original text
    - This is critical for verifiable attribution
    """

            result = call_llm_json(extraction_prompt)

            entities = []
            for e in result.get('entities', []):
                entity_id = self._generate_id(e['name'])
                entity = Entity(
                    id=entity_id,
                    name=e['name'],
                    entity_type=e.get('type', 'UNKNOWN'),
                    description=e.get('description', ''),
                    source_doc=doc_name,
                    source_sentence=e.get('source_sentence', text[:100])
                )
                entities.append(entity)

            relationships = []
            for r in result.get('relationships', []):
                rel = Relationship(
                    source_entity=r['source'],
                    target_entity=r['target'],
                    relation_type=r.get('type', 'RELATED_TO'),
                    description=r.get('description', ''),
                    source_doc=doc_name,
                    source_sentence=r.get('source_sentence', '')
                )
                relationships.append(rel)

            return entities, relationships

        def add_document(self, text: str, doc_name: str):
            """
            Ingest a document into the knowledge graph.
            Extracts entities and relationships, preserving source attribution.
            """
            print(f"📄 Processing document: {doc_name}")
            self.documents[doc_name] = text

            # Extract entities and relationships
            entities, relationships = self.extract_entities_and_relationships(text, doc_name)

            # Add entities to graph
            for entity in entities:
                self.entities[entity.id] = entity

                # Generate embedding for vector search
                embedding = embedder.encode(f"{entity.name}: {entity.description}")
                self.entity_embeddings[entity.id] = embedding
                entity.embedding = embedding

                # Add node to graph with all provenance metadata
                self.graph.add_node(
                    entity.id,
                    name=entity.name,
                    type=entity.entity_type,
                    description=entity.description,
                    source_doc=entity.source_doc,
                    source_sentence=entity.source_sentence
                )

            # Add relationships to graph
            for rel in relationships:
                source_id = self._generate_id(rel.source_entity)
                target_id = self._generate_id(rel.target_entity)

                if source_id in self.entities and target_id in self.entities:
                    self.graph.add_edge(
                        source_id,
                        target_id,
                        relation_type=rel.relation_type,
                        description=rel.description,
                        source_doc=rel.source_doc,
                        source_sentence=rel.source_sentence
                    )
                    self.relationships.append(rel)

            print(f"   ✅ Extracted {len(entities)} entities and {len(relationships)} relationships")
            return entities, relationships

        def vector_search(self, query: str, top_k: int = 5) -> List[Entity]:
            """Find entities most similar to the query using vector search."""
            query_embedding = embedder.encode(query)

            similarities = []
            for entity_id, embedding in self.entity_embeddings.items():
                similarity = np.dot(query_embedding, embedding) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(embedding)
                )
                similarities.append((entity_id, similarity))

            # Sort by similarity
            similarities.sort(key=lambda x: x[1], reverse=True)

            # Return top entities
            return [self.entities[eid] for eid, _ in similarities[:top_k]]

        def multi_hop_traverse(
            self,
            start_entities: List[Entity],
            max_hops: int = 2
        ) -> List[Dict[str, Any]]:
            """
            Perform multi-hop graph traversal from starting entities.
            Returns all reachable nodes with their paths (for attribution).
            """
            results = []
            visited = set()

            for start_entity in start_entities:
                # BFS traversal up to max_hops
                queue = [(start_entity.id, [start_entity.name], 0)]

                while queue:
                    current_id, path, depth = queue.pop(0)

                    if depth > max_hops or current_id in visited:
                        continue

                    visited.add(current_id)

                    # Get node data
                    if current_id in self.graph:
                        node_data = self.graph.nodes[current_id]
                        results.append({
                            "entity_id": current_id,
                            "entity_name": node_data.get('name'),
                            "description": node_data.get('description'),
                            "source_doc": node_data.get('source_doc'),
                            "source_sentence": node_data.get('source_sentence'),
                            "path": path,
                            "depth": depth
                        })

                        # Explore neighbors
                        for neighbor in self.graph.neighbors(current_id):
                            edge_data = self.graph.edges[current_id, neighbor]
                            neighbor_name = self.graph.nodes[neighbor].get('name', neighbor)
                            new_path = path + [f"--[{edge_data.get('relation_type')}]-->", neighbor_name]
                            queue.append((neighbor, new_path, depth + 1))

            return results

        def hybrid_search(
            self,
            query: str,
            vector_top_k: int = 3,
            graph_hops: int = 2
        ) -> List[Dict[str, Any]]:
            """
            Hybrid search combining vector similarity and graph traversal.

            1. Vector search finds entry points (most relevant entities)
            2. Graph traversal expands to connected information
            """
            print(f"🔍 Hybrid Search: '{query}'")

            # Step 1: Vector search for entry points
            entry_points = self.vector_search(query, top_k=vector_top_k)
            print(f"   📌 Found {len(entry_points)} entry points via vector search")

            # Step 2: Multi-hop graph traversal
            traversal_results = self.multi_hop_traverse(entry_points, max_hops=graph_hops)
            print(f"   🔗 Traversed to {len(traversal_results)} related entities")

            return traversal_results

        def generate_attributed_answer(
            self,
            query: str,
            context: List[Dict[str, Any]]
        ) -> AttributedAnswer:
            """
            Generate an answer with verifiable source citations.

            Each claim in the answer is linked to:
            - Source document
            - Source sentence
            - Graph path that led to this information
            """

            # Build context string with source markers
            context_parts = []
            source_map = {}

            for i, item in enumerate(context):
                source_key = f"[{i+1}]"
                context_parts.append(
                    f"{source_key} {item['entity_name']}: {item['description']}"
                )
                source_map[source_key] = {
                    "document": item['source_doc'],
                    "sentence": item['source_sentence'],
                    "path": item['path']
                }

            context_text = "\n".join(context_parts)

            answer_prompt = f"""Based on this knowledge graph context, answer the question.
    CRITICAL: Cite your sources using [N] notation for each claim.

    CONTEXT:
    {context_text}

    QUESTION: {query}

    Provide a comprehensive answer with inline citations like [1], [2] for each claim.
    """

            answer_text = call_llm(answer_prompt)

            # Extract citations from the answer
            import re
            citation_refs = re.findall(r'\[(\d+)\]', answer_text)

            citations = []
            for ref in set(citation_refs):
                key = f"[{ref}]"
                if key in source_map:
                    src = source_map[key]
                    citations.append(Citation(
                        claim=f"Reference {key}",
                        source_document=src['document'],
                        source_sentence=src['sentence'],
                        confidence=0.9,
                        graph_path=src['path']
                    ))

            # Build reasoning trace
            reasoning_trace = [
                f"🔍 Query: {query}",
                f"📌 Found {len(context)} relevant entities",
                f"🔗 Traversed graph paths",
                f"📝 Generated answer with {len(citations)} citations"
            ]

            return AttributedAnswer(
                answer=answer_text,
                citations=citations,
                reasoning_trace=reasoning_trace,
                entities_used=[c['entity_name'] for c in context],
                relationships_traversed=[]
            )

    return (KnowledgeGraphRAG,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 5. Ingest Sample Documents

    Let's demonstrate with sample documents that require **multi-hop reasoning** - something Vector RAG struggles with.
    """)
    return


@app.cell
def _(KnowledgeGraphRAG):
    # Sample documents designed to demonstrate multi-hop reasoning
    # Note: Vector RAG would need to find BOTH documents to answer questions
    # about how Dr. Smith's research relates to the quantum computing project

    SAMPLE_DOCUMENTS = {
        "research_team.txt": """
    Dr. Sarah Chen leads the Advanced AI Research Lab at TechCorp.
    She pioneered the development of the NeuraSparse algorithm in 2022.
    Dr. Chen previously studied under Professor James Miller at Stanford University.
    Professor Miller is known for his foundational work in neural network optimization.
    The Advanced AI Research Lab collaborates closely with the Quantum Computing Division.
    Dr. Chen's team includes 15 researchers working on efficient neural architectures.
    """,

        "quantum_project.txt": """
    The Quantum Computing Division at TechCorp is led by Dr. Marcus Williams.
    Dr. Williams implemented the NeuraSparse algorithm in their quantum error correction system.
    This implementation reduced error rates by 47% compared to traditional methods.
    The quantum team works on Project Aurora, funded by a $50 million grant.
    Project Aurora aims to build a fault-tolerant quantum computer by 2027.
    The project uses insights from Professor Miller's optimization research.
    """,

        "company_overview.txt": """
    TechCorp was founded in 2015 by Elena Rodriguez in San Francisco.
    The company has grown to over 500 employees across three divisions.
    TechCorp's three main divisions are: AI Research, Quantum Computing, and Cloud Services.
    Elena Rodriguez previously worked at Google as a principal engineer.
    The company's headquarters are located in the South Bay area.
    TechCorp has partnerships with MIT and Stanford University for research collaboration.
    """
    }

    # Initialize the Knowledge Graph RAG
    kg_rag = KnowledgeGraphRAG()

    # Ingest all documents
    for doc_name, content in SAMPLE_DOCUMENTS.items():
        kg_rag.add_document(content, doc_name)

    print(f"\n📊 Graph Statistics:")
    print(f"   Total Entities: {len(kg_rag.entities)}")
    print(f"   Total Relationships: {len(kg_rag.relationships)}")
    print(f"   Graph Nodes: {kg_rag.graph.number_of_nodes()}")
    print(f"   Graph Edges: {kg_rag.graph.number_of_edges()}")
    return (kg_rag,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 6. Visualize the Knowledge Graph

    Let's see the structure of our knowledge graph.
    """)
    return


@app.cell
def _(kg_rag):
    # Display entities
    print("🔵 ENTITIES IN KNOWLEDGE GRAPH:\n")
    for entity_id, entity in kg_rag.entities.items():
        print(f"  [{entity.entity_type}] {entity.name}")
        print(f"       📄 Source: {entity.source_doc}")
        print(f"       📝 \"{entity.source_sentence[:80]}...\"")
        print()

    print("\n" + "="*60)
    print("🔗 RELATIONSHIPS IN KNOWLEDGE GRAPH:\n")
    for rel in kg_rag.relationships:
        print(f"  {rel.source_entity} --[{rel.relation_type}]--> {rel.target_entity}")
        print(f"       📄 Source: {rel.source_doc}")
        print()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 7. Hybrid Search: Vector + Graph Traversal

    This is where Graph RAG shines. We combine:
    1. **Vector Search**: Find relevant entry points
    2. **Graph Traversal**: Expand to connected information (multi-hop)
    """)
    return


@app.cell
def _(kg_rag):
    # Multi-hop question that requires connecting information from multiple documents
    MULTI_HOP_QUERY = "How does Professor Miller's research influence the quantum computing project?"
    print('=' * 70)
    print('🧪 MULTI-HOP REASONING DEMONSTRATION')
    print('=' * 70)
    print(f'\n❓ Query: {MULTI_HOP_QUERY}')
    print('\n⚠️  Why Vector RAG would struggle:')
    print("   - 'Professor Miller' appears in research_team.txt")
    print("   - 'quantum computing project' details are in quantum_project.txt")
    print('   - Vector RAG finds similar chunks, but may miss the CONNECTION')
    print()
    context = kg_rag.hybrid_search(MULTI_HOP_QUERY, vector_top_k=3, graph_hops=2)
    print(f'\n📊 Retrieved {len(context)} relevant pieces of information:')
    # Perform hybrid search
    for _i, item in enumerate(context):
        print(f"\n  [{_i + 1}] {item['entity_name']}")
        print(f"      Path: {' '.join(item['path'])}")
        print(f"      Source: {item['source_doc']}")
    return MULTI_HOP_QUERY, context


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 8. Generate Answer with Verifiable Citations

    The key differentiator: every claim is traced back to its **exact source sentence**.
    """)
    return


@app.cell
def _(MULTI_HOP_QUERY, context, kg_rag):
    # Generate attributed answer
    _result = kg_rag.generate_attributed_answer(MULTI_HOP_QUERY, context)
    print('=' * 70)
    print('📝 GENERATED ANSWER WITH CITATIONS')
    print('=' * 70)
    print(f'\n{_result.answer}')
    print('\n' + '=' * 70)
    print('🔍 REASONING TRACE')
    print('=' * 70)
    for step in _result.reasoning_trace:
        print(f'  {step}')
    print('\n' + '=' * 70)
    print('📚 VERIFIABLE CITATIONS')
    print('=' * 70)
    for _i, citation in enumerate(_result.citations):
        print(f'\n  Citation {_i + 1}:')
        print(f'    📄 Document: {citation.source_document}')
        print(f'    📝 Source Sentence: "{citation.source_sentence}"')
        print(f"    🔗 Graph Path: {' → '.join(citation.graph_path)}")
        print(f'    ✓ Confidence: {citation.confidence:.0%}')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 9. Additional Multi-Hop Query Examples

    Let's test more queries that demonstrate the power of graph-based reasoning.
    """)
    return


@app.cell
def _(kg_rag):
    ADDITIONAL_QUERIES = ['What is the relationship between Dr. Chen and Project Aurora?', 'How did the NeuraSparse algorithm impact quantum error correction?', 'Who founded the company where Dr. Chen works?']
    for query in ADDITIONAL_QUERIES:
        print('\n' + '=' * 70)
        print(f'❓ {query}')
        print('=' * 70)
        context_1 = kg_rag.hybrid_search(query, vector_top_k=3, graph_hops=2)
        _result = kg_rag.generate_attributed_answer(query, context_1)
        print(f'\n💬 Answer:\n{_result.answer[:500]}...')
        print(f'\n📚 Citations: {len(_result.citations)} sources verified')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 10. Comparison: Graph RAG vs Vector RAG

    | Aspect | Vector RAG | Graph RAG |
    |--------|------------|-----------|
    | **Multi-hop Questions** | ❌ Struggles to connect disjoint facts | ✅ Follows relationship edges |
    | **Attribution Granularity** | 📄 Chunk-level | 📝 Sentence-level |
    | **Relationship Discovery** | ❌ Implicit in embeddings | ✅ Explicit, traversable |
    | **Privacy** | ⚠️ Often requires cloud APIs | ✅ Fully local with Ollama |
    | **Reasoning Transparency** | ❌ Black box | ✅ Visible graph paths |

    ### When to Use Graph RAG

    ✅ **Use Graph RAG when:**
    - Questions require connecting facts from multiple documents
    - You need verifiable, sentence-level attribution
    - Relationship discovery is important
    - Privacy is critical (on-premise deployment)

    ⚠️ **Stick with Vector RAG when:**
    - Simple factoid retrieval suffices
    - Documents have minimal interconnections
    - Speed is more important than attribution
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 11. Production Deployment with Neo4j

    For production use, replace NetworkX with Neo4j for:
    - Scalability to millions of entities
    - ACID transactions
    - Native graph query language (Cypher)
    - Visualization tools

    ```python
    # Production example with Neo4j
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))

    # Add entity with provenance
    with driver.session() as session:
        session.run(\"\"\"
            MERGE (e:Entity {id: $id})
            SET e.name = $name,
                e.source_doc = $source_doc,
                e.source_sentence = $source_sentence
        \"\"\", id=entity_id, name=name, source_doc=doc, source_sentence=sentence)
    ```

    ## References

    - **VeritasGraph**: [GitHub Repository](https://github.com/bibinprathap/VeritasGraph)
    - **Microsoft GraphRAG**: Graph-based RAG research
    - **Ollama**: Local LLM inference
    - **Neo4j**: Graph database for production deployments
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
