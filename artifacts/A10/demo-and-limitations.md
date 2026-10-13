# A10 — functional-terminal /demo: account scope, keyboard, mobile (ALG-3261)

Parent: ALG-3248 (demo sprint) · Packet: A10 (spec ALG-3106) · scoped to `/demo`

Built by ALG-3253 (`d8b6f7b`, terminal theme), ALG-3254 (`fe0c8b0`, Accounts /
Positions / Orders / Risk panes and `?account=` context) and ALG-3260 (`1b7de9c`,
server-side grants). This pack adds `make verify-A10` and a live browser journey
test (`93fc9f3`). Paper and synthetic data only. No broker and no live capital.

## How to run the demo

    # API + /demo on the demo stack (tailnet): http://100.101.235.117:8190/demo
    # Local, over any observations feed:
    env -u DATABASE_URL PYTHONPATH=src \
      ALGOBOTS_DEMO_FEED_PATH=<feed.jsonl> ALGOBOTS_DEMO_STATE_DIR=<dir> \
      ALGOBOTS_DEMO_START=2026-10-06 ALGOBOTS_DEMO_ACCOUNT_GRANTS=laya,jev,coin \
      python -m uvicorn algobots.api.main:app --port 8771
    open http://127.0.0.1:8771/demo                 # aggregate of granted accounts
    open http://127.0.0.1:8771/demo?account=jev     # one account; every pane narrows

Keyboard: Tab walks every pane control, and each one shows a focus ring.
In Accounts, ↑/↓ moves the selection and Enter switches the account.
`ALGOBOTS_DEMO_ACCOUNT_GRANTS` lists the accounts the synthetic principal
`demo-viewer` may read. The grant check runs even with the default value.

Verify: `make verify-A10` (set `PYTHON` to a venv with the project installed).
It runs `tests/demo` and `tests/packets/A10` and writes
`test-results/junit.xml` and `test-results/keyboard.txt`.
At `93fc9f3`: 23 passed, 0 skipped.

## Failure path reproduced

The server was started with `ALGOBOTS_DEMO_ACCOUNT_GRANTS=laya` on a synthetic
fresh feed (2026-10-07):

    /demo?account=laya            -> 200
    /demo?account=jev             -> 403   DENIED · 403 · demo-viewer not granted jev
    /demo/api/orders?account=jev  -> 403   {"detail":{"account":"jev","state":"denied","reason":"demo-viewer not granted jev"}}
    /demo?account=nope            -> 404
    /demo                         -> 200   aggregate lists only data-account="laya" (+ "all")

The denied page has no data. It shows the status bar, one BLOCKED line and a
link back to `/demo`, and it does not fall back to the aggregate. Tests:
`test_ungranted_deep_link_is_403_on_page_and_every_json_endpoint` and
`test_aggregate_denied_without_any_grant`.

## Evidence

- `acceptance.json`: one entry per case, with status, commit, test ids and
  evidence paths.
- `test-results/junit.xml`: the run from `make verify-A10`, with run-specific
  attributes removed.
- `test-results/keyboard.txt`: the `keyboard.mjs` output from the live
  journey test (Tab 15/15, focus rings, ArrowDown+Enter switch, 0 foreign
  order ids, 390px status bar, unknown account returns 404).
- `ALG-3260/`: 1440px and 390px screenshots plus the original keyboard run.

## Limitations (honest)

- **BLOCKED: invitation journey.** Not built. `/demo` has no login, and the
  grants come from config, not from invitations.
- **BLOCKED: workspace selector.** Not built. There is one synthetic tenant,
  and only the account selector exists.
- **BLOCKED: overview/advanced mode toggle.** Not built. There is a single
  terminal layout.
- **BLOCKED (deferred): fixture-mode isolation for KPI/market/signal panels.**
  The KPI strip is computed from the grant-narrowed ledger, so ungranted books
  never reach it. No test asserts per-account KPI values, though. `/demo` has
  no market or signal panels.
- "Reconnect" on an account switch is a full server render of the new URL,
  with a 60s meta refresh after that. There is no SSE or WebSocket stream to
  re-scope.
- The principal is synthetic (`demo-viewer` / tenant `demo`). Real identity
  and session auth belong to the platform API, not to this demo.
- The browser journey needs node, `playwright-core` (found under
  `~/.npm/_npx` or set with `A10_NODE_PATH`) and a Playwright Chromium.
  Without them the test skips and says why, so a skipped run is not evidence
  for case A10-3.
