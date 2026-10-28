The 78 `stage-*.py` notebooks are recovered marimo editions of the October 13 collection.

Sources:

- Nir Diamant, RAG Techniques: https://github.com/NirDiamant/RAG_Techniques at `ec1289f1f6ea52fc9eabe30c774ff145849fc3e0`.
- Nir Diamant, Agent Memory Techniques: https://github.com/NirDiamant/Agent_Memory_Techniques at `c6e32bad6c6c168ee91f3b2abe54f4038f8d1aef`.
- Existing converted source hashes and original graph failures are recorded in `audit.json`.
- Both upstream Apache 2.0 licenses are included here.

Changes made October 28, 2026: added editable research notes to native apps; recovered invalid conversions from original notebook cells; added code editors, explicit run controls, captured stdout/stderr and matplotlib output to sequential wrappers. Repaired missing commas, unmatched delimiters and detached class methods in five source notebooks. Top-level await is supported by the wrapper runner. Installation/magic commands remain commented setup instructions and do not mutate the runtime automatically.

42 notebooks retain their native reactive cells; 36 use a sequential computation wrapped in a reactive marimo app. All 78 load and initialize their marimo dependency graphs. This structural audit does not assert that every external API, paid model, GPU, source document or optional dependency is available. Those computations run only with their required environment and credentials. Original files remain unchanged on FunnyTree.
