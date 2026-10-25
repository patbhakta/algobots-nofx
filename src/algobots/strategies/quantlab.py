"""Bounded file-channel dispatch; quantlab independently verifies snapshot hashes.

The queue is on the existing private quantlab shared volume. Requests contain
data only; no supplied code, paths, commands, or provider queries are executed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4


def dispatch(root: Path, artifact: dict, snapshot_id: str, digest: str) -> dict:
    root.mkdir(parents=True, exist_ok=True, mode=0o2770)
    root.chmod(0o2770)
    identity = uuid4().hex
    request = root / f"{identity}.request.json"
    result = root / f"{identity}.result.json"
    temporary = root / f"{identity}.tmp"
    temporary.write_text(
        json.dumps(dict(artifact=artifact, snapshot_id=snapshot_id, sha256=digest))
    )
    temporary.chmod(0o664)
    temporary.rename(request)
    deadline = time.monotonic() + 90
    try:
        while time.monotonic() < deadline:
            if result.exists():
                response = json.loads(result.read_text())
                if "error" in response:
                    raise ValueError(response["error"])
                if response["sha256"] != digest or response["snapshot_id"] != snapshot_id:
                    raise ValueError("quantlab snapshot identity mismatch")
                return response["result"]
            time.sleep(0.1)
        raise ValueError("quantlab backtest timed out; no result saved")
    finally:
        request.unlink(missing_ok=True)
        result.unlink(missing_ok=True)


def execute(request: Path):
    from algobots.strategies.ohlc import run
    from algobots.warehouse import Warehouse

    payload = json.loads(request.read_text())
    manifest, table = Warehouse(Path("/home/quantlab/openbb_store")).load(payload["snapshot_id"])
    if manifest["sha256"] != payload["sha256"]:
        raise ValueError("quantlab snapshot content hash differs from API")
    result = run(payload["artifact"], manifest, table.to_pylist())
    return dict(snapshot_id=manifest["snapshot_id"], sha256=manifest["sha256"], result=result)


def serve(root: Path):
    root.mkdir(parents=True, exist_ok=True, mode=0o770)
    while True:
        for request in sorted(root.glob("*.request.json")):
            result = request.with_name(request.name.replace(".request.json", ".result.json"))
            if result.exists():
                continue
            temporary = result.with_suffix(".tmp")
            try:
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "algobots.strategies.quantlab",
                        str(request),
                        str(temporary),
                    ],
                    capture_output=True,
                    timeout=75,
                    check=False,
                )
                if completed.returncode or not temporary.exists():
                    temporary.write_text(json.dumps({"error": "quantlab OHLC replay failed"}))
                if request.exists():
                    # SSHFS maps UID-1000 creations to root:1000; chmod is
                    # forbidden even for their creator. umask 0002 sets 0664.
                    temporary.rename(result)
            except subprocess.TimeoutExpired:
                if request.exists():
                    temporary.write_text(json.dumps({"error": "quantlab engine timeout"}))
                    temporary.rename(result)
            finally:
                temporary.unlink(missing_ok=True)
        time.sleep(0.1)


if __name__ == "__main__":
    os.umask(0o002)
    if len(sys.argv) == 3:
        try:
            response = execute(Path(sys.argv[1]))
        except Exception as exc:
            response = {"error": str(exc)}
        Path(sys.argv[2]).write_text(json.dumps(response))
    else:
        serve(Path("/home/quantlab/notebooks/.backtests"))
