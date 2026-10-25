"""Run on the paper Docker host: denial egress and delivered-command restart recovery.

Uses the gateway container's configured session internally; prints no credentials.
Stops only the sandbox node, and always starts it again. No live venue route.
"""

from __future__ import annotations

import json
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
    base = "http://100.82.57.72:8210/v1"
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

    denied = f"alg3409-denied-{run}"
    submit(denied, "100")
    for _ in range(100):
        order = request("/orders/" + denied)
        if order.get("status") == "rejected":
            break
        time.sleep(0.1)
    assert order["status"] == "rejected", order
    print(json.dumps({"denied": order}), flush=True)

    # Wait for a fresh beat before the brief, intentional paper-node outage.
    time.sleep(5)
    restart = f"alg3409-restart-{run}"
    stream = "algobots:cmd:nautilus-paper"
    try:
        docker("stop", "-t", "1", "nautilus-node")
        submit(restart, "1000")
        claimed = docker(
            "exec",
            "algobots-redis-1",
            "redis-cli",
            "--raw",
            "XREADGROUP",
            "GROUP",
            "algobots-node",
            "NAUTILUS-PAPER",
            "COUNT",
            "1",
            "STREAMS",
            stream,
            ">",
        )
        assert restart in claimed, claimed
        pending = docker(
            "exec", "algobots-redis-1", "redis-cli", "--raw", "XPENDING", stream, "algobots-node"
        )
        assert int(pending.splitlines()[0]) >= 1, pending
        print(json.dumps({"restart_key": restart, "pending_before_restart": pending}), flush=True)
    finally:
        docker("start", "nautilus-node")
    for _ in range(100):
        logs = subprocess.check_output(
            ["docker", "logs", "nautilus-node"], stderr=subprocess.STDOUT, text=True
        )
        fills = [line for line in logs.splitlines() if restart in line and "OrderFilled(" in line]
        if fills:
            break
        time.sleep(0.2)
    assert fills, "recovered command did not fill"
    pending = docker(
        "exec", "algobots-redis-1", "redis-cli", "--raw", "XPENDING", stream, "algobots-node"
    )
    for _ in range(50):
        if int(pending.splitlines()[0]) == 0:
            break
        time.sleep(0.1)
        pending = docker(
            "exec", "algobots-redis-1", "redis-cli", "--raw", "XPENDING", stream, "algobots-node"
        )
    assert int(pending.splitlines()[0]) == 0, pending
    print(
        json.dumps(
            {
                "restart_key": restart,
                "venue_fill": fills[-1],
                "pending_after_execution": pending,
                "gateway_order": request("/orders/" + restart),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
