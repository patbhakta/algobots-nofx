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

## Control-plane API (S0.2)

FastAPI service with JWT auth, invite-code registration, tenant-scoped CRUD,
and an audit trail on every mutation. Full details: [docs/control-plane.md](docs/control-plane.md).

```bash
pip install -e ".[dev]"
alembic upgrade head                    # schema: users, invite_codes, accounts,
                                        # strategies, deployments, orders,
                                        # decisions, clamp_events, audit_log
uvicorn algobots.api.main:app --reload

# first user registers with the bootstrap invite code (owner role)
curl -s localhost:8000/api/auth/register -H 'content-type: application/json' -d '{
  "email": "you@example.com", "password": "a-long-password",
  "display_name": "You", "invite_code": "ALGOBOTS-BOOTSTRAP"}'

# login → bearer token → create an invite for the next user
curl -s localhost:8000/api/auth/login -H 'content-type: application/json' \
  -d '{"email": "you@example.com", "password": "a-long-password"}'
curl -s localhost:8000/api/auth/invites -H "authorization: Bearer $TOKEN" -X POST
```

Every mutating request (POST/PUT/PATCH/DELETE) writes an `audit_log` row —
read your tenant's trail at `GET /api/audit`.
