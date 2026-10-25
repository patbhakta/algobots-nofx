# ALG-3431 dispatch leg — evidence

Code: `0c50696` (gateway deployment nodes + dispatcher token, supervisor dispatch,
`/api/nofx/studio/live` deployments section); NoFX `cb802b4f` (live-tab card).

| pair | before | after |
|---|---|---|
| unit | `before.txt` — new tests cannot import on main 38c2651 | `after.txt` — 14 passed |
| .243 runtime | `243/before.txt` — gateway knows only `nautilus-paper`; no deployment stream | `243/after.txt` — both RUNNING deployments are gateway nodes, own cmd/event streams, reconciled |
| .243 UI | `ui/live-before.png` — funder's deployment exists, live tab has no card (`summary-before.json` FAIL) | `ui/live-after-deploy.png` — card shows THAT deployment, RUNNING, artifact bb4c4150ddae |

`ui/01-before-deploy.png`, `ui/02-deployed.png`, `summary-deploy.json`: fresh QA funder
registers, backtests (201), marimo evidence gate opens Deploy, deploy → 201 RUNNING
(`63e6f7fb-…`) with frozen exact-hash evidence, all through :8201.

Fills: none yet. The frozen kalshi_momentum.v1 buys YES only when edge ≥ min_edge
(0.02); the 21:45Z and 22:00Z books both had p≈0.37 after the latest settle, so both
deployments correctly abstained. A fill needs a real up-momentum interval; no order
was injected.

.243 runtime: api+gateway image `algobots-api:alg3431` (rollback tags `*:pre-alg3431`),
`.env` gained `ALGOBOTS_GATEWAY_DEPLOYMENTS=1` + dispatch token (backup `.env.pre-alg3431`),
supervisor container `algobots-deployment-supervisor` (`algobots/nautilus-node:alg3431`),
frontend `algobots/nofx-frontend:alg3431-deploy-fills` (backup compose `docker-compose.yml.pre-alg3431`).

Walkthrough: `node deploy-fills-walkthrough.mjs deploy|live …` (invite + session stay in run scratch).
