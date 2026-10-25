"""The supervisor must stop every child before releasing singleton ownership."""

from contextlib import contextmanager

import pytest

from algobots.node.deployment_supervisor import supervise


class Runtime:
    def __init__(self):
        self.events = []

    def reconcile(self, rows):
        self.events.append(("rows", rows))

    def close(self):
        self.events.append(("close",))


def test_shutdown_precedes_lease_release():
    runtime = Runtime()

    @contextmanager
    def lease():
        yield lambda: ["frozen"]
        runtime.events.append(("release",))

    supervise(runtime, lease, lambda: True)
    assert runtime.events == [("rows", ["frozen"]), ("close",), ("release",)]


def test_database_failure_stops_children_before_release():
    runtime = Runtime()

    @contextmanager
    def lease():
        def read():
            raise ConnectionError("database lost")

        try:
            yield read
        finally:
            runtime.events.append(("release",))

    with pytest.raises(ConnectionError):
        supervise(runtime, lease, lambda: False)
    assert runtime.events == [("close",), ("release",)]


def test_failed_lease_never_launches():
    runtime = Runtime()

    @contextmanager
    def lease():
        raise RuntimeError("already owned")
        yield

    with pytest.raises(RuntimeError, match="already owned"):
        supervise(runtime, lease, lambda: False)
    assert runtime.events == []


def test_sqlite_cannot_claim_production_ownership():
    from sqlalchemy import create_engine

    from algobots.node.deployment_supervisor import database_lease

    with pytest.raises(RuntimeError, match="PostgreSQL"):
        with database_lease(create_engine("sqlite://")):
            pytest.fail("sqlite acquired a production singleton")
