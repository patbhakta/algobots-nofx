"""Minimal service entrypoint for the S0.1 scaffold.

S0.2 (control-plane skeleton) replaces this with tenancy, auth, and audit routes.
Kept intentionally small: enough app for container healthchecks and CI smoke tests.
"""

from fastapi import FastAPI

app = FastAPI(title="AlgoBots API", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe used by docker-compose and monitoring."""
    return {"status": "ok"}
