"""AlgoBots control-plane API — S0.2 skeleton.

FastAPI app with JWT auth, invite-code registration, tenant-scoped CRUD,
Alembic-managed schema, and audit + access-log middleware on every mutation.
Run migrations before serving: `alembic upgrade head`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from algobots.api.accounts.router import router as accounts_router
from algobots.api.approvals.router import router as approvals_router
from algobots.api.deployments.router import router as deployments_router
from algobots.api.middleware import AccessLogMiddleware, AuditMiddleware
from algobots.api.routers.auth import router as auth_router
from algobots.api.routers.auth import users_router
from algobots.api.routers.resources import router as resources_router
from algobots.demo import router as demo
from algobots.demo.router import router as demo_router


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
app.include_router(deployments_router)
app.include_router(approvals_router)
app.include_router(demo_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe used by docker-compose and monitoring."""
    return {"status": "ok"}
