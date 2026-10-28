# Marimo Studio collection restored — 2026-10-28

Studio: http://100.82.57.72:8202/

OpenBB example: http://100.82.57.72:8202/?file=openbb_spy_history.py

Use the existing Studio login. Expand `collection` in the Workspace file list to open the recovered notebooks. Open an OpenBB notebook and submit **Fetch history and write catalog** to fetch data and render the chart.

## Counts

The requested October 13 collection has **42 native true apps / 36 executable sequential wrappers / 0 unfixable**. Every served `.py` is a real `marimo.App` with cells and UI controls. Three new native OpenBB apps bring the workspace to **81 notebooks: 45 native / 36 wrapped / 0 unfixable**.

The original converted files were syntactically valid Python containers, but 36 contained invalid marimo cells. Recovery used original notebook sources, retained markdown, restored executable code, repaired known delimiters and detached class methods, and added explicit execution controls plus captured output/chart rendering. Wrappers are labeled as sequential recovery; they do not claim independently reactive computation for every original Jupyter cell. All 81 app dependency graphs validate. The initial lint pass found zero breaking diagnostics; inherited formatting and reusable-definition ordering advisories remain.

## Live verification

Real Playwright browser sessions opened the :8202 workspace, expanded the collection, submitted the SPY, QQQ and AAPL forms, and observed a chart plus a successful Nautilus catalog read-back message for each. Each dataset has 10 real daily bars for the query September 1–15, 2026, obtained through `obb.equity.price.historical(provider="yfinance")`. No provider responses were mocked. Screenshots and machine-readable results accompany this report.

The data path is OpenBB SDK → UTC-normalized OHLCV → rc6 `ParquetDataCatalog.write_instruments/write_bars` → `query_bars` verification → matplotlib chart and interactive table. Each snapshot includes query parameters, retrieval time, row count and a content hash. Listing venues are SPY.ARCA, QQQ.NASDAQ and AAPL.NASDAQ. Daily availability is approximated as next UTC midnight for research; these timestamps are not exchange execution truth.

## Deployment

Service `nautilus` / container `nautilus-marimo` serves :8202 using the OpenBB/Nautilus base runtime plus plotting dependencies. Its quantlab worker entrypoint is disabled; the existing separate :8205 quantlab service is unchanged. The overlay and rollback instructions are committed under `deploy/` and `scripts/research/marimo_collection/README.md`.

Source notebooks mount from `/mnt/funnytree/algobots/studio-notebooks` to `/app/notebooks`. Catalog storage mounts from `/mnt/funnytree/algobots/ntl_catalog` to `/app/data/nautilus`. Bulk data remains on FunnyTree. Original notebook files remain untouched.

Runtime: marimo 0.25.1, OpenBB 4.7.2, NautilusTrader 2.0.0rc6. Runtime package inventory contains zero Jupyter/IPython/ipykernel/notebook packages. The pre-existing marimo configuration bind remains mounted, AI remains enabled, and its configured custom provider remains `zai` with `glm-4.7-flash` and `glm-5.3`.

## Verification scope

All 78 recovered notebooks load as apps with cells and UI; only the three OpenBB workloads are claimed as fully executed live here. Optional RAG packages, original documents, GPUs and paid provider credentials remain prerequisites for those source workloads. The recovery does not invent credentials or substitute mocked data. Shell/package-install cells in the wrappers are retained as commented setup instructions.
