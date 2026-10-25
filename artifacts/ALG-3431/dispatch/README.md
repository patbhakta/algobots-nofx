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

Fills: the 21:45Z–22:15Z books had p≈0.31–0.37, so both deployments abstained. The
first up-momentum windows (KXBTC15M-26OCT251845, -1900) produced real dispatches at
22:30:30Z and 22:45:31Z; no order was injected.

| pair | before | after |
|---|---|---|
| .243 fills | `ui/live-after-deploy.png` — card shows the deployment, 0 fills | `ui/live-after-fills.png` + `.json` — same funder's card: 2 orders, 2 fills (1 @ 0.50, 1 @ 0.57); `243/fills.txt` — all 4 `dp1-` orders/fills of both deployment nodes |
| kill switch | `243/killswitch-before.txt` — 63e6f7fb running, its paper_node child alive, gateway node reachable | `243/killswitch-stop.txt` — owner `PATCH status=stopped` 200 at 22:53:42Z; `243/killswitch-after.txt` — node "Received stop signal" <1 s later, child gone, gateway node unreachable, probe `POST /v1/orders` → 503 `deployment … is stopped`, 0 rows written; 3d030739 unaffected |

The kill-switch probe is a 1-lot IOC buy at 0.01 against a 0.5x ask, so it could not
fill even if admitted. The NoFX UI has no stop control yet, so the stop used the
owner's session against the same API the UI calls.

Known gaps seen in these fills (follow-ups, not fixed here):
- Each IOC for 8 filled 1: the paper venue only has top-of-book size 1 from the
  observer feed, so the remainder cancels.
- 63e6f7fb's 22:30:30Z buy (limit 0.57) filled at 0.50. That is the previous
  contract's ask: `KXBTC15M/USD.DEP…` is one rolling instrument, and the node's book
  had not yet seen the new contract's first quote. The position also nets across
  contracts (signed_qty 2 spanning -1845 and -1900).

.243 runtime: api+gateway image `algobots-api:alg3431` (rollback tags `*:pre-alg3431`),
`.env` gained `ALGOBOTS_GATEWAY_DEPLOYMENTS=1` + dispatch token (backup `.env.pre-alg3431`),
supervisor container `algobots-deployment-supervisor` (`algobots/nautilus-node:alg3431`),
frontend `algobots/nofx-frontend:alg3431-deploy-fills` (backup compose `docker-compose.yml.pre-alg3431`).

Walkthrough: `node deploy-fills-walkthrough.mjs deploy|live …` (invite + session stay in run scratch).
