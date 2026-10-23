| # | Hop | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Studio config saved for a strategy | **stubbed** | no /api/studio/strategies (Studio->gateway draft contract, ALG-3352); demo-only studio serves 6 built-in template versions (/demo/studio); NoFX Studio does not save through the gateway |
| 2 | Gateway accepts and dispatches | **stubbed** | GET /health -> 404 (gateway contract health route); redis algobots:cmd:* streams: 0; orders go through the demo order API to worker inboxes, not the gateway (src/algobots/gateway is not deployed) |
| 3 | Nautilus 2.0.0rc6 paper run fills orders | **stubbed** | node nautilus_trader: 1.231.0 (pin 2.0.0rc6); marimo nautilus_trader: 2.0.0rc6; paper workers ready: 3, orders filled: 2; workers run on the API image's Nautilus, not the pinned rc6 node |
| 4 | Market data reaches the node | **missing** | feed path: /feeds/kalshi/observations.jsonl; feed age: absent; intervals processed by workers: 0 |
| 5 | marimo renders evidence from the run | **stubbed** | marimo HTTP: 303; notebooks marked 'ALG-3403 evidence': none; marimo is up but no notebook reads the paper run's fills/PnL/data timestamps |

full loop: FAIL (0/5 hops wired)
exit=1
