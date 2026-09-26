"""AlgoBots control-plane API — S0.2 skeleton.

FastAPI app with JWT auth, invite-code registration, tenant-scoped CRUD,
Alembic-managed schema, and audit + access-log middleware on every mutation.
Run migrations before serving: `alembic upgrade head`.
"""

from fastapi import FastAPI

from algobots.api.middleware import AccessLogMiddleware, AuditMiddleware
from algobots.api.routers.auth import router as auth_router
from algobots.api.routers.auth import users_router
from algobots.api.routers.resources import router as resources_router

app = FastAPI(
    title="AlgoBots API",
    version="0.2.0",
    description="Control plane for the AlgoBots multi-account trading platform.",
)

# Middleware: last added runs outermost. AuditMiddleware (outer) records the
# X-Request-Id that AccessLogMiddleware (inner) stamps on every response.
app.add_middleware(AccessLogMiddleware)
app.add_middleware(AuditMiddleware)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(resources_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe used by docker-compose and monitoring."""
    return {"status": "ok"}
