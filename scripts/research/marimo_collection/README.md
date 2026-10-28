The Studio collection repair is deliberately separate from trading execution and the existing quantlab worker.

`repair_collection.py SOURCE DESTINATION --original-root /path/to/Agent_Memory_Techniques --original-root /path/to/RAG_Techniques` audits real marimo dependency graphs, retains native cells, and wraps failed conversions with an editable sequential runner. The source directory can be the 78 October 13 `stage-*.py` conversions. No notebook workload executes during auditing. Requires marimo 0.25.1.

Build `deploy/marimo_collection/Dockerfile` on .243, where its existing base image is available. It installs plotting/scientific dependencies in the actual `/opt/venv` interpreter, removes the quantlab worker entrypoint, and preserves the OpenBB/Nautilus runtime.

Copy `notebooks/collection/` into `/mnt/funnytree/algobots/studio-notebooks/collection/` and `notebooks/openbb/*.py` into `/mnt/funnytree/algobots/studio-notebooks/`. Apply `deploy/compose.marimo-collection.yaml` after `/opt/algobots-stack/docker-compose.yml`, targeting only service `nautilus`. The overlay retains the original token, tailnet-only port 8202, zai configuration bind, bridge and networks. Notebook source and data live on FunnyTree. `/app/data/nautilus` is bound to its existing catalog directory. Port 8205's quantlab service is unchanged.

The OpenBB notebooks fetch only on form submission. They normalize UTC daily OHLCV, use the actual listing venue, write Nautilus instruments and bars through the rc6 ParquetDataCatalog API, read the bars back and render a chart. Content-addressed snapshot directories and provenance records retain query parameters and row counts. These are historical research bars, with daily availability approximated at next UTC midnight, not execution or official exchange-close timestamps.

`verify_live.py --url http://100.82.57.72:8202/ --chromium /path/to/chromium` uses Playwright to expand the real notebook list, submit all three OpenBB forms, and verify chart images and catalog-readback messages. Authenticate using the existing Studio token if your browser session requires it. It uses real SDK calls and never mocks responses. Evidence goes to `artifacts/marimo-collection`.

Rollback: reapply the base Compose file for service `nautilus` without the overlay. Original notebook files and quantlab mounts remain intact.
