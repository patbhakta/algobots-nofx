"""ALG-3403 evidence: fills, PnL and data timestamps for one Nautilus paper run.

Reads the paper node's egress, the Redis ``trader-<TRADER_ID>:algobots:*`` streams the
rc6 node publishes (order_filled, position, account, portfolio, heartbeat, data.*).
Read-only: XRANGE only, never writes to Redis or orders. Stdlib RESP client so the
marimo image needs no extra packages.
"""

import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")

with app.setup:
    import json
    import os
    import socket
    from datetime import UTC, datetime
    from decimal import Decimal
    from urllib.parse import urlparse

    EVIDENCE_MARKER = "ALG-3403 evidence"


@app.function
def resp_command(url: str, *args: str, timeout: float = 5.0):
    """Send one Redis command over RESP2 and return the decoded reply."""
    u = urlparse(url)
    with socket.create_connection((u.hostname, u.port or 6379), timeout=timeout) as s:
        f = s.makefile("rb")
        out = [f"*{len(args)}\r\n".encode()]
        for a in args:
            b = a.encode()
            out.append(b"$%d\r\n%s\r\n" % (len(b), b))
        s.sendall(b"".join(out))

        def read():
            line = f.readline().rstrip(b"\r\n")
            kind, rest = line[:1], line[1:]
            if kind == b"+":
                return rest.decode()
            if kind == b"-":
                raise RuntimeError(rest.decode())
            if kind == b":":
                return int(rest)
            if kind == b"$":
                n = int(rest)
                if n < 0:
                    return None
                data = f.read(n + 2)[:-2]
                return data.decode()
            if kind == b"*":
                n = int(rest)
                return None if n < 0 else [read() for _ in range(n)]
            raise RuntimeError(f"bad RESP reply: {line!r}")

        return read()


@app.function
def scan_streams(url: str, pattern: str) -> list[str]:
    keys, cursor = set(), "0"
    while True:
        cursor, batch = resp_command(url, "SCAN", cursor, "MATCH", pattern, "COUNT", "1000")
        keys.update(batch)
        if cursor == "0":
            return sorted(keys)


@app.function
def read_stream(url: str, key: str) -> list[dict]:
    """XRANGE a trader stream into rows of {stream_id, topic, type, payload}."""
    rows = []
    for stream_id, fields in resp_command(url, "XRANGE", key, "-", "+"):
        f = dict(zip(fields[::2], fields[1::2], strict=True))
        rows.append(
            {
                "stream_id": stream_id,
                "topic": f.get("topic", ""),
                "type": f.get("type", ""),
                "payload": json.loads(f["payload"]) if f.get("payload") else {},
            }
        )
    return rows


@app.function
def unwrap(payload: dict) -> dict:
    """Nautilus serialises enums as {"Variant": {...}}; return the inner event."""
    if len(payload) == 1:
        (inner,) = payload.values()
        if isinstance(inner, dict):
            return inner
    return payload


@app.function
def ns_to_iso(ts) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(int(ts) / 1e9, UTC).isoformat(timespec="milliseconds")


@app.function
def stream_id_iso(stream_id: str) -> str:
    return datetime.fromtimestamp(int(stream_id.split("-")[0]) / 1e3, UTC).isoformat(
        timespec="milliseconds"
    )


@app.function
def money(value) -> Decimal:
    """'0.00 USD' -> Decimal('0.00'); numbers pass through."""
    if value is None:
        return Decimal(0)
    return Decimal(str(value).split()[0])


@app.function
def fills_table(events: list[dict]) -> list[dict]:
    rows = []
    for e in events:
        p = unwrap(e["payload"])
        if p.get("type") != "OrderFilled":
            continue
        rows.append(
            {
                "ts_event": ns_to_iso(p.get("ts_event")),
                "published": stream_id_iso(e["stream_id"]),
                "instrument": p.get("instrument_id"),
                "side": p.get("order_side"),
                "qty": Decimal(p.get("last_qty", "0")),
                "px": Decimal(p.get("last_px", "0")),
                "commission": p.get("commission"),
                "client_order_id": p.get("client_order_id"),
                "trade_id": p.get("trade_id"),
                "position_id": p.get("position_id"),
                "strategy": p.get("strategy_id"),
            }
        )
    return sorted(rows, key=lambda r: r["ts_event"])


@app.function
def pnl_from_fills(fills: list[dict]) -> list[dict]:
    """Average-cost PnL per instrument, marked at the last fill price.

    Realized PnL books on quantity that reduces the open position; unrealized marks the
    remainder at the most recent fill (the node publishes no quotes to Redis).
    """
    book: dict[str, dict] = {}
    for f in fills:
        b = book.setdefault(
            f["instrument"],
            {
                "qty": Decimal(0),
                "avg": Decimal(0),
                "realized": Decimal(0),
                "commission": Decimal(0),
            },
        )
        signed = f["qty"] if f["side"] == "BUY" else -f["qty"]
        b["commission"] += money(f["commission"])
        if b["qty"] == 0 or (b["qty"] > 0) == (signed > 0):
            total = b["qty"] + signed
            b["avg"] = (b["avg"] * abs(b["qty"]) + f["px"] * abs(signed)) / abs(total)
            b["qty"] = total
        else:
            closing = min(abs(signed), abs(b["qty"]))
            direction = 1 if b["qty"] > 0 else -1
            b["realized"] += (f["px"] - b["avg"]) * closing * direction
            remainder = abs(signed) - closing
            b["qty"] += signed
            if remainder:
                b["avg"] = f["px"]
            elif b["qty"] == 0:
                b["avg"] = Decimal(0)
        b["mark"] = f["px"]
    return [
        {
            "instrument": inst,
            "net_qty": b["qty"],
            "avg_px": b["avg"],
            "mark_px": b["mark"],
            "realized": b["realized"],
            "unrealized": (b["mark"] - b["avg"]) * b["qty"],
            "commission": b["commission"],
            "net_pnl": b["realized"] + (b["mark"] - b["avg"]) * b["qty"] - b["commission"],
        }
        for inst, b in sorted(book.items())
    ]


@app.function
def latest_by_stream(streams: dict[str, list[dict]], marker: str) -> list[dict]:
    """Latest payload of every stream whose key contains ``marker``."""
    rows = []
    for key, events in sorted(streams.items()):
        if marker in key and events:
            rows.append({"stream": key, **unwrap(events[-1]["payload"])})
    return rows


@app.function
def timestamp_table(streams: dict[str, list[dict]]) -> list[dict]:
    """First/last event per stream: event time vs. when Redis received it."""
    rows = []
    for key, events in sorted(streams.items()):
        if not events:
            continue
        first, last = unwrap(events[0]["payload"]), unwrap(events[-1]["payload"])
        last_event = (
            ns_to_iso(last.get("ts_event"))
            if isinstance(last.get("ts_event"), int)
            else last.get("ts_event", "")
        )
        rows.append(
            {
                "stream": key.split(":", 2)[-1],
                "events": len(events),
                "first_published": stream_id_iso(events[0]["stream_id"]),
                "last_published": stream_id_iso(events[-1]["stream_id"]),
                "first_ts_event": ns_to_iso(first.get("ts_event"))
                if isinstance(first.get("ts_event"), int)
                else first.get("ts_event", ""),
                "last_ts_event": last_event,
            }
        )
    return rows


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    mo.md(f"""
    # Paper run evidence ({EVIDENCE_MARKER})

    Fills, PnL and data timestamps for one Nautilus paper run, read from the node's
    Redis egress (`trader-<TRADER_ID>:algobots:*` streams). Read-only.
    """)
    return


@app.cell
def _(mo):
    redis_url = mo.ui.text(
        value=os.environ.get("ALGOBOTS_REDIS_URL", "redis://algobots-redis-1:6379"),
        label="Redis URL",
        full_width=True,
    )
    redis_url  # noqa: B018 - marimo displays the last expression
    return (redis_url,)


@app.cell
def _(mo, redis_url):
    try:
        traders = sorted({k.split(":", 1)[0] for k in scan_streams(redis_url.value, "trader-*")})
        scan_error = None
    except (OSError, RuntimeError) as exc:
        traders, scan_error = [], f"{type(exc).__name__}: {exc}"
    mo.stop(
        not traders,
        mo.callout(
            mo.md(f"No `trader-*` streams at `{redis_url.value}`. {scan_error or ''}"), kind="warn"
        ),
    )
    run = mo.ui.dropdown(options=traders, value=traders[0], label="Paper run (trader id)")
    run  # noqa: B018 - marimo displays the last expression
    return (run,)


@app.cell
def _(redis_url, run):
    keys = scan_streams(redis_url.value, f"{run.value}:*")
    streams = {k: read_stream(redis_url.value, k) for k in keys}
    return (streams,)


@app.cell
def _(mo, streams):
    fills = fills_table([e for k, ev in streams.items() if ".order_filled." in k for e in ev])
    mo.vstack([mo.md(f"## Fills ({len(fills)})"), mo.ui.table(fills, selection=None)])
    return (fills,)


@app.cell
def _(fills, mo, streams):
    pnl = pnl_from_fills(fills)
    positions = latest_by_stream(streams, ":events.position.")
    accounts = latest_by_stream(streams, ":events.account.")
    portfolio = latest_by_stream(streams, ":events.portfolio.")
    mo.vstack(
        [
            mo.md("## PnL\nComputed from fills (average cost, marked at last fill)."),
            mo.ui.table(pnl, selection=None),
            mo.md("Node-reported positions (latest event per stream)"),
            mo.ui.table(
                [
                    {
                        k: p.get(k)
                        for k in (
                            "position_id",
                            "side",
                            "signed_qty",
                            "avg_px_open",
                            "realized_pnl",
                            "ts_event",
                        )
                    }
                    | {"ts_event": ns_to_iso(p.get("ts_event"))}
                    for p in positions
                ],
                selection=None,
            ),
            mo.md("Account balances (latest AccountState / PortfolioSnapshot)"),
            mo.ui.table(
                [
                    {
                        "stream": a["stream"].split(":", 2)[-1],
                        "balances": "; ".join(
                            f"{b['total']} (free {b['free']})" for b in a.get("balances", [])
                        ),
                        "equity": ", ".join(a.get("total_equity", []) or []),
                        "ts_event": ns_to_iso(a.get("ts_event")),
                    }
                    for a in accounts + portfolio
                ],
                selection=None,
            ),
        ]
    )
    return


@app.cell
def _(mo, streams):
    stamps = timestamp_table(streams)
    heartbeats = [
        unwrap(e["payload"]) for k, ev in streams.items() if ".heartbeat." in k for e in ev
    ]
    last_hb = heartbeats[-1] if heartbeats else {}
    mo.vstack(
        [
            mo.md(
                "## Data timestamps\n"
                f"Last heartbeat: `{last_hb.get('ts_event', 'none')}` "
                f"(node `{last_hb.get('node', '?')}`, "
                f"reconciled `{last_hb.get('reconciled', '?')}`)."
            ),
            mo.ui.table(stamps, selection=None),
        ]
    )
    return


if __name__ == "__main__":
    app.run()
