"""Full-loop demo verifier (ALG-3403): walk every hop on the .243 stack.

Run from any host on the tailnet::

    python tests/demo/full_loop.py                 # table, exit 0 only if every hop is wired
    python tests/demo/full_loop.py --json          # same facts as JSON

The five hops of the demo, each reported ``wired`` / ``stubbed`` / ``missing``:

1. ``studio``  — a Studio config is saved through the gateway's draft contract
   (``POST /api/studio/strategies``, docs/design/strategy-studio-nautilus-bridge.md).
2. ``gateway`` — the gateway is deployed, healthy, and has a node command stream
   (``algobots:cmd:<node>``) to dispatch to.
3. ``nautilus`` — the ``nautilus-node`` container runs Nautilus 2.0.0rc6
   (roadmap rule 5) in paper mode and its ``trader-*`` event streams carry fills
   (ALG-3405).
4. ``datafeed`` — market data reaches the node and is fresh: the rc6 node's
   ``algobots:feed:<node>`` stream, written per quote its strategy received
   (replay, ALG-3406; IBKR live, ALG-3357). Falls back to the worker feed file.
5. ``marimo`` — a marimo notebook on the stack renders that run's evidence
   (fills, PnL, data timestamps).

``stubbed`` means something answers but it is not the hop the demo needs (for
example the demo-only studio, or paper workers on Nautilus 1.x); the evidence
line says which. The script is read-only: it never saves, deploys or orders.

Container, Redis and file facts are read over ``ssh <host>``; HTTP facts are
fetched directly. Collection (``collect``) and judgement (``judge``) are
separate so ``test_full_loop.py`` can pin the judgement without the stack.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any

HOST = "100.82.57.72"
API = f"http://{HOST}:8000"
MARIMO = f"http://{HOST}:8202"
API_CONTAINER = "algobots-api-1"
MARIMO_CONTAINER = "nautilus-marimo"
REDIS_CONTAINER = "algobots-redis-1"
NODE_CONTAINER = "nautilus-node"  # deploy/compose.nautilus-node.yaml (ALG-3405)
#: rc6 republishes every OrderFilled on this per-type topic, so the sum of
#: these streams' lengths is the node's fill count.
FILL_STREAMS = "trader-*:algobots:events.order_filled.*"
NOTEBOOK_DIR = "/mnt/funnytree/algobots/notebooks"
NAUTILUS_PIN = "2.0.0rc6"
FEED_MAX_AGE_S = 15 * 60  # a replay or live feed older than this is not reaching the node
#: algobots.node.replay.FEED_PREFIX; the node signals about once a second while quotes arrive.
NODE_FEED_STREAMS = "algobots:feed:*"
NODE_FEED_MAX_AGE_S = 60
EVIDENCE_MARKER = "ALG-3403 evidence"  # the evidence notebook declares itself with this

WIRED, STUBBED, MISSING = "wired", "stubbed", "missing"


@dataclass
class Hop:
    key: str
    title: str
    status: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class Facts:
    """Everything observed on the stack; ``None`` means the probe could not answer."""

    api_paths: list[str] | None = None
    gateway_health: int | None = None
    redis_cmd_streams: list[str] | None = None
    redis_trader_streams: list[str] | None = None
    api_nautilus: str | None = None
    node_nautilus: str | None = None
    node_fills: int | None = None
    marimo_nautilus: str | None = None
    workers: dict[str, Any] | None = None
    studio_versions: int | None = None
    feed_path: str | None = None
    feed_age_s: float | None = None
    node_feed_stream: str | None = None
    node_feed_entries: int | None = None
    node_feed_last: dict[str, str] | None = None
    node_feed_age_s: float | None = None
    marimo_http: int | None = None
    evidence_notebooks: list[str] | None = None
    errors: list[str] = field(default_factory=list)


# --- collection ---------------------------------------------------------------------


def _http(url: str, timeout: float = 8.0) -> tuple[int | None, bytes]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - tailnet only
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, b""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def _status_only(url: str) -> int | None:
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(url, timeout=8.0) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def _ssh(host: str, cmd: str, timeout: float = 30.0) -> str | None:
    try:
        out = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _version_cmd(container: str) -> str:
    probe = "import nautilus_trader as n; print(n.__version__)"
    return f"docker exec {container} python -c {shlex.quote(probe)}"


def _node_feed(host: str, f: Facts) -> None:
    """Newest entry of the node's feed-signal stream, aged on Redis' own clock."""
    rc = f"docker exec {REDIS_CONTAINER} redis-cli"
    out = _ssh(
        host,
        f'echo "#TIME $({rc} TIME | tr "\\n" " ")"; '
        f"for k in $({rc} --scan --pattern {shlex.quote(NODE_FEED_STREAMS)}); "
        f'do echo "#STREAM $k $({rc} XLEN "$k")"; {rc} XREVRANGE "$k" + - COUNT 1; done',
    )
    if out is None:
        f.errors.append(f"ssh {host}: node feed probe failed")
        return
    now_s: float | None = None
    for block in out.split("#")[1:]:
        lines = block.strip().splitlines()
        head = lines[0].split()
        if head[0] == "TIME" and len(head) == 3:  # seconds, microseconds
            now_s = int(head[1]) + int(head[2]) / 1e6
        elif head[0] == "STREAM" and len(head) == 3 and len(lines) >= 2:
            entry_id, kv = lines[1], lines[2:]
            last = dict(zip(kv[::2], kv[1::2], strict=False))
            # Several nodes: judge the freshest.
            if f.node_feed_last is None or entry_id > f.node_feed_last.get("_id", ""):
                last["_id"] = entry_id
                f.node_feed_stream, f.node_feed_entries = head[1], int(head[2])
                f.node_feed_last = last
    if f.node_feed_last is not None and now_s is not None:
        f.node_feed_age_s = now_s - int(f.node_feed_last["_id"].split("-")[0]) / 1000


def collect(host: str = HOST, api: str = API, marimo: str = MARIMO) -> Facts:
    f = Facts()

    code, body = _http(f"{api}/openapi.json")
    if code == 200:
        f.api_paths = sorted(json.loads(body)["paths"])
    else:
        f.errors.append(f"{api}/openapi.json -> {code}")

    # The gateway contract serves /health (contracts/gateway.openapi.yaml); the
    # demo API only serves /healthz, so a 404 here means no gateway is deployed.
    f.gateway_health = _status_only(f"{api}/health")

    code, body = _http(f"{api}/demo/api/workers")
    if code == 200:
        f.workers = json.loads(body)
    code, body = _http(f"{api}/demo/api/strategies")
    if code == 200:
        f.studio_versions = len(json.loads(body).get("versions", []))
    f.marimo_http = _status_only(f"{marimo}/")

    redis = _ssh(host, f"docker exec {REDIS_CONTAINER} redis-cli --scan --count 1000")
    if redis is None:
        f.errors.append(f"ssh {host}: redis scan failed")
    else:
        keys = redis.split()
        f.redis_cmd_streams = [k for k in keys if k.startswith("algobots:cmd:")]
        f.redis_trader_streams = [k for k in keys if k.startswith("trader-")]

    f.api_nautilus = _ssh(host, _version_cmd(API_CONTAINER))
    f.node_nautilus = _ssh(host, _version_cmd(NODE_CONTAINER))
    fills = _ssh(
        host,
        f"for k in $(docker exec {REDIS_CONTAINER} redis-cli --scan --pattern "
        f"{shlex.quote(FILL_STREAMS)}); "
        f'do docker exec {REDIS_CONTAINER} redis-cli XLEN "$k"; done',
    )
    if fills is not None:
        f.node_fills = sum(int(n) for n in fills.split() if n.isdigit())
    f.marimo_nautilus = _ssh(host, _version_cmd(MARIMO_CONTAINER))

    _node_feed(host, f)

    f.feed_path = _ssh(host, f"docker exec {API_CONTAINER} printenv ALGOBOTS_DEMO_FEED_PATH")
    if f.feed_path:
        mtime = _ssh(host, f"docker exec {API_CONTAINER} stat -c %Y {shlex.quote(f.feed_path)}")
        f.feed_age_s = time.time() - float(mtime) if mtime else None

    found = _ssh(
        host,
        f"grep -l -r --include='*.py' {shlex.quote(EVIDENCE_MARKER)} {NOTEBOOK_DIR} || true",
    )
    f.evidence_notebooks = found.split() if found is not None else None
    return f


# --- judgement ----------------------------------------------------------------------


def _studio(f: Facts) -> Hop:
    h = Hop("studio", "Studio config saved for a strategy", MISSING)
    paths = f.api_paths or []
    if "/api/studio/strategies" in paths:
        h.status = WIRED
        h.evidence.append("gateway draft route /api/studio/strategies is served")
        return h
    h.evidence.append("no /api/studio/strategies (Studio->gateway draft contract, ALG-3352)")
    if "/demo/api/strategies" in paths:
        h.status = STUBBED
        h.evidence.append(
            f"demo-only studio serves {f.studio_versions} built-in template versions "
            "(/demo/studio); NoFX Studio does not save through the gateway"
        )
    return h


def _gateway(f: Facts) -> Hop:
    h = Hop("gateway", "Gateway accepts and dispatches", MISSING)
    h.evidence.append(f"GET /health -> {f.gateway_health} (gateway contract health route)")
    cmd = f.redis_cmd_streams
    h.evidence.append(
        "redis algobots:cmd:* streams: "
        + ("unknown (probe failed)" if cmd is None else str(len(cmd)))
    )
    if f.gateway_health == 200 and cmd:
        h.status = WIRED
    elif f.gateway_health == 200 or cmd:
        h.status = STUBBED
    elif f.api_paths and "/demo/api/v1/{account}/orders/place" in f.api_paths:
        h.status = STUBBED
        h.evidence.append(
            "orders go through the demo order API to worker inboxes, not the gateway "
            "(src/algobots/gateway is not deployed)"
        )
    return h


def _workers(f: Facts) -> list[dict[str, Any]]:
    return list((f.workers or {}).get("workers", []))


def _nautilus(f: Facts) -> Hop:
    h = Hop("nautilus", f"Nautilus {NAUTILUS_PIN} paper run fills orders", MISSING)
    h.evidence.append(
        f"{NODE_CONTAINER} nautilus_trader: {f.node_nautilus} (pin {NAUTILUS_PIN}); "
        f"fills on {FILL_STREAMS}: {f.node_fills}"
    )
    if f.node_nautilus == NAUTILUS_PIN and (f.node_fills or 0) > 0:
        h.status = WIRED
        return h
    ready = [w for w in _workers(f) if w.get("state") == "ready"]
    filled = sum(int(w.get("orders_filled") or 0) for w in ready)
    h.evidence.append(f"API nautilus_trader: {f.api_nautilus}")
    h.evidence.append(f"marimo nautilus_trader: {f.marimo_nautilus}")
    h.evidence.append(f"paper workers ready: {len(ready)}, orders filled: {filled}")
    if f.node_nautilus == NAUTILUS_PIN:
        h.status = STUBBED
        h.evidence.append("rc6 node is up but has no fills on its event streams yet")
        return h
    if not ready:
        return h
    if f.api_nautilus == NAUTILUS_PIN and filled > 0:
        h.status = WIRED
    else:
        h.status = STUBBED
        if f.api_nautilus != NAUTILUS_PIN:
            h.evidence.append("workers run on the API image's Nautilus, not the pinned rc6 node")
        if filled == 0:
            h.evidence.append("no fills recorded by any ready worker")
    return h


def _iso_ns(ns: str | None) -> str:
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(ns or "") / 1e9))
    except ValueError:
        return "?"


def _node_datafeed(f: Facts, h: Hop) -> Hop:
    last = f.node_feed_last or {}
    src = last.get("source", "")
    age = f.node_feed_age_s
    h.evidence.append(
        f"{f.node_feed_stream}: {f.node_feed_entries} signals, last "
        + ("age unknown" if age is None else f"{age:.0f}s ago")
    )
    h.evidence.append(
        f"source {src} {last.get('instrument', '')}; quotes received by the node: "
        f"{last.get('received')}; last bid/ask {last.get('bid')}/{last.get('ask')}"
    )
    h.evidence.append(
        f"recorded ts {_iso_ns(last.get('recorded_ts'))} (row {last.get('row')}, "
        f"lap {last.get('laps')}) -> node ts {_iso_ns(last.get('node_ts'))}"
    )
    if not src or src.startswith("synthetic"):
        h.status = STUBBED
        h.evidence.append("node prices are synthetic, not recorded or live market data")
    elif age is not None and age <= NODE_FEED_MAX_AGE_S:
        h.status = WIRED
    else:
        h.status = STUBBED
        h.evidence.append(f"node feed is stale (> {NODE_FEED_MAX_AGE_S}s)")
    return h


def _datafeed(f: Facts) -> Hop:
    h = Hop("datafeed", "Market data reaches the node", MISSING)
    if f.node_feed_last is not None:
        return _node_datafeed(f, h)
    intervals = sum(int(w.get("intervals") or 0) for w in _workers(f))
    h.evidence.append(f"feed path: {f.feed_path}")
    h.evidence.append(
        "feed age: " + ("absent" if f.feed_age_s is None else f"{f.feed_age_s / 60:.0f} min")
    )
    h.evidence.append(f"intervals processed by workers: {intervals}")
    if f.feed_age_s is None:
        return h
    if f.feed_age_s <= FEED_MAX_AGE_S and intervals > 0:
        h.status = WIRED
    else:
        h.status = STUBBED
        h.evidence.append("feed exists but is stale or unread (no replay running)")
    return h


def _marimo(f: Facts) -> Hop:
    h = Hop("marimo", "marimo renders evidence from the run", MISSING)
    h.evidence.append(f"marimo HTTP: {f.marimo_http}")
    nbs = f.evidence_notebooks
    h.evidence.append(
        f"notebooks marked '{EVIDENCE_MARKER}': "
        + ("unknown" if nbs is None else str(nbs or "none"))
    )
    if f.marimo_http is None:
        return h
    if nbs:
        h.status = WIRED
    else:
        h.status = STUBBED
        h.evidence.append(
            "marimo is up but no notebook reads the paper run's fills/PnL/data timestamps"
        )
    return h


def judge(f: Facts) -> list[Hop]:
    return [_studio(f), _gateway(f), _nautilus(f), _datafeed(f), _marimo(f)]


def render(hops: list[Hop]) -> str:
    lines = ["| # | Hop | Status | Evidence |", "| --- | --- | --- | --- |"]
    for i, h in enumerate(hops, 1):
        lines.append(f"| {i} | {h.title} | **{h.status}** | {'; '.join(h.evidence)} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--api", default=API)
    ap.add_argument("--marimo", default=MARIMO)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    facts = collect(a.host, a.api, a.marimo)
    hops = judge(facts)
    ok = all(h.status == WIRED for h in hops)
    if a.json:
        print(
            json.dumps(
                {"ok": ok, "hops": [asdict(h) for h in hops], "facts": asdict(facts)}, indent=2
            )
        )
    else:
        print(render(hops))
        for err in facts.errors:
            print(f"probe error: {err}", file=sys.stderr)
        print(
            f"\nfull loop: {'PASS' if ok else 'FAIL'} "
            f"({sum(h.status == WIRED for h in hops)}/{len(hops)} hops wired)"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
