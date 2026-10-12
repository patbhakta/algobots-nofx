"""AlgoBots control-plane API — S0.2 skeleton + A03 tenant authorization.

FastAPI app with session-bound JWT auth, invite-only registration, tenant
memberships and role checks, tenant-scoped CRUD,
Alembic-managed schema, and audit + access-log middleware on every mutation.
Run migrations before serving: `alembic upgrade head`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from sqlalchemy import text

from algobots.api.accounts.broker_accounts import router as broker_accounts_router
from algobots.api.accounts.router import router as accounts_router
from algobots.api.approvals.router import router as approvals_router
from algobots.api.database import get_session_factory
from algobots.api.deployments.router import router as deployments_router
from algobots.api.memberships.router import me_router as tenancy_me_router
from algobots.api.memberships.router import router as memberships_router
from algobots.api.middleware import AccessLogMiddleware, AuditMiddleware
from algobots.api.risk.router import router as risk_router
from algobots.api.routers.auth import router as auth_router
from algobots.api.routers.auth import users_router
from algobots.api.routers.resources import router as resources_router
from algobots.demo import router as demo
from algobots.demo.router import router as demo_router
from algobots.knowledge.ingest.router import register as register_knowledge_router
from algobots.marketdata.routes import instruments_router
from algobots.marketdata.routes import marketdata_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    demo.start_workers()
    try:
        yield
    finally:
        demo.stop_workers()


app = FastAPI(
    lifespan=lifespan,
    title="AlgoBots API",
    version="0.4.0",
    description="Control plane for the AlgoBots multi-account trading platform.",
)

# Middleware: last added runs outermost. AuditMiddleware (outer) records the
# X-Request-Id that AccessLogMiddleware (inner) stamps on every response.
app.add_middleware(AccessLogMiddleware)
app.add_middleware(AuditMiddleware)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(resources_router)
app.include_router(accounts_router)
app.include_router(broker_accounts_router)
app.include_router(deployments_router)
app.include_router(approvals_router)
app.include_router(risk_router)
app.include_router(demo_router)
app.include_router(tenancy_me_router)
app.include_router(memberships_router)
# A05 instrument & market-data read-only routers (ALG-3101): proposal through
# the api owner per the A03/A04 mount precedent (see the A05 scope guard).
app.include_router(instruments_router)
app.include_router(marketdata_router)

# A14 knowledge ingestion (ALG-3110): register() hook keeps the ingest core
# stdlib-only; store root via ALGOBOTS_KNOWLEDGE_STORE (else var/knowledge-ingest).
register_knowledge_router(app)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe used by docker-compose and monitoring."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz(response: Response) -> dict[str, str]:
    """Readiness probe: 503 until the database answers."""
    session = get_session_factory()()
    try:
        session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — any DB failure means not ready
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}
    finally:
        session.close()
    return {"status": "ready"}
