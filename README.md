# AlgoBots

Multi-account algorithmic trading platform: dashboards, trading strategies, AI, and automation for friends-and-family accounts.

## Monorepo layout

| Package | Purpose |
| --- | --- |
| `src/algobots/contracts/` | Typed contracts (DTOs, enums, event schemas) |
| `src/algobots/risk/` | Risk policy enforcement, exposure clamps, kill-switch |
| `src/algobots/execution/` | Broker adapters, order routing, fills (paper/live) |
| `src/algobots/models/` | Strategy/model registry and inference interfaces |
| `src/algobots/evals/` | Decision-quality evaluation harness |
| `src/algobots/engine/` | Strategy runners and event-driven orchestration |
| `src/algobots/api/` | Control-plane API (FastAPI) |
| `src/algobots/dashboard/` | User-facing dashboards |

## Quickstart

```bash
cd deploy
cp .env.example .env      # adjust secrets
docker compose up -d --build
docker compose ps         # all services should report healthy
curl http://localhost:8000/healthz
```

Run tests inside the container:

```bash
docker compose exec api pytest
```

## Development

```bash
pip install -e ".[dev]"
pre-commit install
ruff check .
pytest
```

CI runs ruff + pytest on every push and pull request.
