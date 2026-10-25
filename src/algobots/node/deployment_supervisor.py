"""Paper deployment supervisor, run explicitly in the pinned rc6 node image.

One PostgreSQL session owns the advisory lock and reads deployment intent.
There is deliberately no automatic reconnect: a failed read stops all children
before releasing ownership. The API process never launches this supervisor.
With ``ALGOBOTS_GATEWAY_URL`` and ``ALGOBOTS_GATEWAY_DISPATCH_TOKEN`` set, each
tick also admits the running deployments' frozen decisions through the gateway
(:mod:`algobots.node.deployment_dispatch`).
"""

from __future__ import annotations

import logging
import os
import signal
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from algobots.api.database import get_engine
from algobots.api.deployments.runtime import DeploymentRuntime, deployment_rows_statement
from algobots.node.deployment_dispatch import Dispatcher, gateway_poster
from algobots.node.kalshi import DEFAULT_PATH

log = logging.getLogger("algobots.deployment_supervisor")

# Stable process-independent advisory key; never Python's randomized hash().
LOCK_KEY = 34310001


@contextmanager
def database_lease(engine: Any) -> Iterator[Callable[[], list]]:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("deployment supervisor requires PostgreSQL singleton ownership")
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        owned = connection.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_KEY}
        ).scalar_one()
        if not owned:
            raise RuntimeError("deployment supervisor already owned")
        try:

            def read() -> list:
                # SQLAlchemy must not reconnect under an old advisory-lock claim.
                if connection.invalidated:
                    raise RuntimeError("deployment supervisor lease connection lost")
                with Session(bind=connection, expire_on_commit=False) as session:
                    return list(session.execute(deployment_rows_statement()).all())

            yield read
        finally:
            if not connection.invalidated:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})


def supervise(
    runtime: DeploymentRuntime,
    lease: Callable,
    wait: Callable[[], bool],
    dispatch: Callable[[list, dict], Any] | None = None,
) -> None:
    """Close children inside ownership, including on query/reconciliation failure.

    ``dispatch`` sees the same fresh rows the reconcile just acted on, so it
    only decides for deployments whose node this process is running. A
    dispatch error is logged, not fatal: the gateway is the order authority.
    """
    with lease() as read:
        try:
            while True:
                rows = read()
                runtime.reconcile(rows)
                if dispatch is not None:
                    try:
                        dispatch(rows, runtime.children)
                    except Exception:
                        log.exception("deployment dispatch failed")
                if wait():
                    break
        finally:
            runtime.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    stopped = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopped.set())
    engine = get_engine()
    url = os.environ.get("ALGOBOTS_GATEWAY_URL", "")
    token = os.environ.get("ALGOBOTS_GATEWAY_DISPATCH_TOKEN", "")
    dispatch = (
        Dispatcher(
            gateway_poster(url, token),
            os.environ.get("ALGOBOTS_KALSHI_PATH", DEFAULT_PATH),
        )
        if url and token
        else None
    )
    log.info("deployment supervisor: dispatch %s", "on" if dispatch else "off")
    try:
        supervise(
            DeploymentRuntime(),
            lambda: database_lease(engine),
            lambda: stopped.wait(1),
            dispatch,
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
