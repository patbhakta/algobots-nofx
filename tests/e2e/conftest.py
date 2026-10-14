"""The sandbox stack GATE G1 runs against: real Postgres, real Redis.

G1 is the one test in this repository that may not use a double for the
transport. Its claim is a *latency* — a fill is visible in NoFX within two
seconds — and a claim about latency measured over in-memory fakes measures
nothing: the fakes have none of the costs (a round trip, a blocking read, a
commit) that the budget is actually spent on.

So both services are real, and the test skips rather than pretends when they
are absent:

    ALGOBOTS_GATEWAY_TEST_PG_URL=postgresql+psycopg://user:pw@host:5432/db \\
    ALGOBOTS_TEST_REDIS_URL=redis://127.0.0.1:6379/0 \\
      pytest tests/e2e

``compose.yaml`` (Phase 0) is where both come from; ``.github/workflows/ci.yml``
starts them as service containers so the gate runs on every merge, and
``tests/e2e/test_g1_ci_wiring.py`` fails if that wiring is ever removed — a
skipped gate and a passing gate must not look the same to CI.

Everything is namespaced per run (a Postgres schema, a node name that becomes
both Redis stream prefixes), so the gate can be pointed at a shared instance
without touching another run's rows or another node's commands.
"""

from __future__ import annotations

import os
import uuid

import pytest
import sqlalchemy as sa

from algobots.gateway.store import METADATA

PG_URL = os.environ.get("ALGOBOTS_GATEWAY_TEST_PG_URL", "")
REDIS_URL = os.environ.get("ALGOBOTS_TEST_REDIS_URL", "")

PG_REASON = "GATE G1 needs Postgres: set ALGOBOTS_GATEWAY_TEST_PG_URL (see compose.yaml)"
REDIS_REASON = "GATE G1 needs Redis: set ALGOBOTS_TEST_REDIS_URL (see compose.yaml)"


@pytest.fixture
def run_id() -> str:
    """One namespace for this run, in Postgres and in both Redis streams."""
    return uuid.uuid4().hex[:8]


@pytest.fixture
def pg_engine(run_id):  # noqa: ANN001, ANN201
    """A migrated, empty projection in its own schema, dropped afterwards."""
    if not PG_URL:
        pytest.skip(PG_REASON)

    schema = f"g1_{run_id}"
    admin = sa.create_engine(PG_URL)
    with admin.begin() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    engine = sa.create_engine(
        PG_URL, connect_args={"options": f"-csearch_path={schema}"}, pool_pre_ping=True
    )
    METADATA.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def redis_client(run_id):  # noqa: ANN001, ANN201
    """A real Redis client, with this run's streams removed afterwards.

    ``decode_responses=False`` deliberately: the bytes a real client returns
    are what ``command_stream.decode`` and ``event_ingest.decode`` have to
    tolerate, and a decoding client would hide a bug that only appears in the
    deploy.
    """
    if not REDIS_URL:
        pytest.skip(REDIS_REASON)
    redis = pytest.importorskip("redis", reason="pip install -e '.[dev]'")

    client = redis.Redis.from_url(REDIS_URL, decode_responses=False)
    client.ping()  # fail here, loudly, rather than inside the measurement
    try:
        yield client
    finally:
        for pattern in (f"algobots:cmd:*{run_id}*", f"trader-*{run_id.upper()}*"):
            keys = list(client.scan_iter(match=pattern))
            if keys:
                client.delete(*keys)
        client.close()
