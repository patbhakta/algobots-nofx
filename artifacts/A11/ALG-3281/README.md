# ALG-3281 — A11-2 template paper runner: live check

Local API (`ALGOBOTS_DEMO_WORKERS_ENABLED=true`, scratch state dir), three studio
deployments created 6h before start, $400 each:

| deployment | account | template | artifact | orders |
|---|---|---|---|---|
| dep-c76ff035-eq-a | eq-a | Trend crossover v2 (5m, 5/13, SPY) | c76ff035b50d | 5 |
| dep-ce58f755-eq-b | eq-b | Trend crossover v3 (15m, 8/21, QQQ) | ce58f7552d74 | 1 |
| dep-6e9b6af9-eq-a | eq-a | Range / RSI v2 (5m, 6, 35/65, SPY) | 6e9b6af9b534 | 6 |

- All three template workers heartbeat `ready`; `studio.json` flipped each `pending -> running` only after that.
- `/demo/api/orders?account=eq-a` returns only eq-a orders, each with `deployment` + `artifact`.
- Prices are SYNTHETIC BARS (deterministic, not market data), labelled on the page.
- Screenshots: `demo-eq-a-{desktop,mobile}.png` (1440px / 390px, eq-a context), `demo-all-*.png` (aggregate).
- Editing a template mid-run: `tests/engine/workers/test_template.py::test_editing_the_template_mid_run_does_not_change_a_running_deployment`.
