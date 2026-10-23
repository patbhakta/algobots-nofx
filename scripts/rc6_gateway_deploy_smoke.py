"""Verify deployed gateway rc6 fills, denials and persistence on the paper host.

Uses the existing gateway session internally without printing credentials.
Restarts only the gateway; does not change the node or feed.
Requires GATEWAY_BASE_URL and GATEWAY_PREDEPLOY_INSPECT environment variables.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
import uuid


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True).strip()


def main() -> None:
    config = json.loads(docker("inspect", "algobots-gateway-1"))[0]
    env = dict(item.split("=", 1) for item in config["Config"]["Env"])
    token, caller = next(iter(json.loads(env["ALGOBOTS_GATEWAY_SESSIONS"]).items()))
    node = next(
        n for n in json.loads(env["ALGOBOTS_GATEWAY_NODES"]) if n["node"] == "nautilus-paper"
    )
    assert node.get("mode", "PAPER") == "PAPER"
    account = node["account_id"]
    assert account in caller["accounts"]
    base = os.environ["GATEWAY_BASE_URL"].rstrip("/")
    run = uuid.uuid4().hex[:10]

    def request(path: str, body: dict | None = None, key: str = "") -> dict:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if key:
            headers["Idempotency-Key"] = key
        req = urllib.request.Request(
            base + path, headers=headers, data=json.dumps(body).encode() if body else None
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.load(response)

    def submit(key: str, qty: str) -> dict:
        return request(
            "/orders",
            {
                "account_id": account,
                "symbol": "EUR/USD.SIM",
                "side": "buy",
                "qty": qty,
                "order_type": "market",
                "time_in_force": "gtc",
            },
            key,
        )

    results = {}
    for label, qty, expected in (("filled", "1000", "filled"), ("denied", "100", "rejected")):
        key = f"alg3410-{label}-{run}"
        submit(key, qty)
        for _ in range(150):
            order = request("/orders/" + key)
            if order.get("status") == expected:
                break
            time.sleep(0.2)
        assert order["status"] == expected, order
        results[label] = order
    results["pending"] = docker(
        "exec", "algobots-redis-1", "redis-cli", "--raw", "XPENDING",
        "algobots:cmd:nautilus-paper", "algobots-node",
    )
    results["redis_events"] = docker(
        "exec", "algobots-redis-1", "redis-cli", "--raw", "XREVRANGE",
        "trader-NAUTILUS-PAPER:algobots:events.order.CommandNode-000",
        "+", "-", "COUNT", "12",
    )
    docker("restart", "algobots-gateway-1")
    for _ in range(100):
        try:
            persisted = {
                label: request("/orders/" + order["client_order_id"])
                for label, order in results.items()
                if label in ("filled", "denied")
            }
            break
        except Exception:
            time.sleep(0.2)
    assert persisted["filled"]["status"] == "filled", persisted
    assert persisted["denied"]["status"] == "rejected", persisted
    results["after_gateway_restart"] = persisted
    before = json.load(open(os.environ["GATEWAY_PREDEPLOY_INSPECT"]))[0]
    after = json.loads(docker("inspect", "algobots-gateway-1"))[0]
    oldenv = dict(e.split("=", 1) for e in before["Config"]["Env"])
    newenv = dict(e.split("=", 1) for e in after["Config"]["Env"])
    checks = {
        k: oldenv.get(k) == newenv.get(k)
        for k in (
            "DATABASE_URL", "REDIS_URL",
            "ALGOBOTS_GATEWAY_SESSIONS", "ALGOBOTS_GATEWAY_NODES",
        )
    }
    assert all(checks.values()), checks
    results["configuration_preserved"] = checks
    print(json.dumps(results), flush=True)

if __name__ == "__main__":
    main()
