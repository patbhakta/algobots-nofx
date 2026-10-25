"""Paper deployment supervisor, run explicitly in the pinned rc6 node image.

One PostgreSQL session owns the advisory lock and reads deployment intent.
There is deliberately no automatic reconnect: a failed read stops all children
before releasing ownership. The API process never launches this supervisor.
"""

from __future__ import annotations

import logging
import signal
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import and_, select, text
from sqlalchemy.orm import Session

from algobots.api.database import get_engine
from algobots.api.deployments.models import Deployment, FleetBreaker
from algobots.api.deployments.runtime import DeploymentRuntime
from algobots.api.models import Account

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
                    return list(
                        session.execute(
                            select(Deployment, Account, FleetBreaker)
                            .join(Account, Account.id == Deployment.account_id)
                            .outerjoin(
                                FleetBreaker,
                                and_(
                                    FleetBreaker.tenant_id == Account.tenant_id,
                                    FleetBreaker.user_id == Deployment.user_id,
                                ),
                            )
                        ).all()
                    )

            yield read
        finally:
            if not connection.invalidated:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})


def supervise(
    runtime: DeploymentRuntime,
    lease: Callable,
    wait: Callable[[], bool],
) -> None:
    """Close children inside ownership, including on query/reconciliation failure."""
    with lease() as read:
        try:
            while True:
                runtime.reconcile(read())
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
    try:
        supervise(
            DeploymentRuntime(),
            lambda: database_lease(engine),
            lambda: stopped.wait(1),
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
