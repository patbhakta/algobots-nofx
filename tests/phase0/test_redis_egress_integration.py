"""P0.3 done-when test: order/position events must be readable from Redis.

`test_phase0.py` only asserts the shape of `MessageBusConfig`. That cannot
catch an egress regression, so this test runs the real sandbox node against a
throwaway Redis container and reads the streams back, mirroring the
`redis-cli XREAD` acceptance check in the issue.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
NODE_SCRIPT = ROOT / "scripts" / "phase0_redis_egress.py"

pytestmark = pytest.mark.skipif(
    shutil.which("docker") is None,
    reason="P0.3 egress evidence requires docker to run a throwaway Redis",
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def redis_container():
    """Throwaway Redis; yields a `redis-cli` runner bound to the container."""
    name = f"alg3350-test-{uuid.uuid4().hex[:8]}"
    port = _free_port()
    subprocess.run(
        [
            "docker", "run", "-d", "--rm", "--name", name,
            "-p", f"127.0.0.1:{port}:6379",
            "redis:7-alpine", "redis-server", "--appendonly", "no",
        ],
        check=True,
        capture_output=True,
        timeout=180,
    )
    try:
        def cli(*args: str) -> str:
            result = subprocess.run(
                ["docker", "exec", name, "redis-cli", *args],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.stdout

        # redis-server is up as soon as PING answers.
        for _ in range(30):
            if cli("ping").strip() == "PONG":
                break
        else:
            pytest.fail("Redis container never answered PING")

        yield cli, port
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=120)


def _payloads(cli, key: str) -> list[dict]:
    """Parse the JSON payload field out of every entry on a stream."""
    raw = cli("XREAD", "COUNT", "100", "STREAMS", key, "0")
    payloads = []
    lines = raw.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "payload" and index + 1 < len(lines):
            payloads.append(json.loads(lines[index + 1]))
    return payloads


def test_order_and_position_events_reach_redis_streams(redis_container):
    cli, port = redis_container

    subprocess.run(
        [sys.executable, str(NODE_SCRIPT)],
        check=True,
        capture_output=True,
        timeout=600,
        cwd=ROOT,
        env={
            "PATH": "/usr/bin:/bin",
            "REDIS_HOST": "127.0.0.1",
            "REDIS_PORT": str(port),
            "PYTHONPATH": str(ROOT / "src"),
        },
    )

    keys = cli("KEYS", "*").split()
    prefix = "trader-ALGOBOTS-001:algobots:"

    order_keys = [k for k in keys if k.startswith(f"{prefix}events.order.")]
    position_keys = [k for k in keys if k.startswith(f"{prefix}events.position.")]
    assert order_keys, f"no order stream published; got {keys}"
    assert position_keys, f"no position stream published; got {keys}"

    order_types = {p["type"] for p in _payloads(cli, order_keys[0])}
    assert {"OrderInitialized", "OrderSubmitted", "OrderFilled"} <= order_types

    position_types = {p["type"] for p in _payloads(cli, position_keys[0])}
    assert {"PositionOpened", "PositionClosed"} <= position_types


def test_quote_ticks_are_filtered_out_of_egress(redis_container):
    """`types_filter=[QuoteTick]` must keep quote data off the streams."""
    cli, port = redis_container

    subprocess.run(
        [sys.executable, str(NODE_SCRIPT)],
        check=True,
        capture_output=True,
        timeout=600,
        cwd=ROOT,
        env={
            "PATH": "/usr/bin:/bin",
            "REDIS_HOST": "127.0.0.1",
            "REDIS_PORT": str(port),
            "PYTHONPATH": str(ROOT / "src"),
        },
    )

    keys = cli("KEYS", "*").split()
    # Quotes drove the strategy, so order events prove the node really ran.
    assert any("events.order." in k for k in keys), f"node published nothing; got {keys}"
    assert not [k for k in keys if "data.quotes" in k], f"quote ticks leaked: {keys}"
