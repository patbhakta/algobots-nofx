# Supervisor component evidence, 2026-10-25

This is component evidence, not the required UI end-to-end acceptance.

- Before: supervisor adapter absent (collection fails); launch symbol lacks /USD
  (regression assertion fails).
- After: 18 focused deployment runtime/supervisor tests pass.
- PostgreSQL check: actual new supervisor/runtime source evaluated in memory
  inside the .243 API container, using its configured database. Read the one
  existing deployment, reject a concurrent advisory-lock owner, release and
  reacquire. No child launched; no deployed file or service changed.
- .243 baseline: one RUNNING paper/auto deployment, orders only on the existing
  demo node, and no deployment command streams.

Commands:

    PYTHONPATH=src /root/repos/algobots/.venv/bin/python -m pytest tests/deployments/test_supervisor.py tests/deployments/test_runtime.py -q
    /root/repos/algobots/.venv/bin/ruff check src/algobots/node/deployment_supervisor.py tests/deployments/test_supervisor.py src/algobots/api/deployments/runtime.py tests/deployments/test_runtime.py
    docker compose -f deploy/compose.nautilus-node.yaml config --quiet

The supervisor is opt-in via the Compose deployments profile; do not commission
it until the frozen signal producer and gateway attribution are connected.
The image now includes the PostgreSQL driver and retains its rc6 assertion.
The supervisor uses a dedicated session advisory lock, never reconnects under a
previous lock claim, and stops children on a failed read or graceful shutdown.
A database outage can leave an old worker running until its next failed query;
strict distributed fencing and abrupt supervisor death are not proven by these
checks. Container termination must terminate all contained workers.

Remaining acceptance: frozen strategy commands, durable command idempotency
across worker restarts, gateway admission and attribution, NoFX live integration,
and before/after UI evidence from the funder-owned deployment on .243.
