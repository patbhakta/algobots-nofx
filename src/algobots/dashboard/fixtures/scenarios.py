"""Deterministic synthetic fixtures for the A09 storyboard (good/loss/empty/stale/unknown).

Every fixture is synthetic paper/demo data: it carries `synthetic: true` and the
`DEMO DATA` label, uses `demo-` account ids on the SIMULATED broker, and holds
amounts as decimal strings with an explicit currency. A metric that cannot be
computed is `None` with a reason; it is never a manufactured zero or infinity.
No fixture contacts a broker, feed or memory service.
"""

from copy import deepcopy
from decimal import Decimal

STATES = ("good", "loss", "empty", "stale", "unknown")
DEMO_LABEL = "DEMO DATA"
AS_OF = "2026-10-06T14:30:00Z"
PERIOD = "2026-09-01/2026-10-06"


def _m(amount: str | None, currency: str = "USD") -> dict | None:
    return None if amount is None else {"amount": amount, "currency": currency}


def _stat(value: str | None, reason: str | None = None) -> dict:
    return {"value": value, "unavailable_reason": reason}


def _bars(n: int, start: str = "566.00") -> list[list[str]]:
    """Deterministic OHLC bars from a fixed integer recurrence (no RNG state, no clock)."""
    bars, close, x = [], Decimal(start), 3105
    for _ in range(n):
        x = (x * 1103515245 + 12345) % 2**31
        o = close
        close = o + Decimal((x % 41) - 18) / 10
        hi = max(o, close) + Decimal(x % 7) / 10
        lo = min(o, close) - Decimal((x >> 3) % 7) / 10
        bars.append([str(o), str(hi), str(lo), str(close)])
    return bars


def _accounts() -> list[dict]:
    return [
        {
            "id": "demo-acct-001",
            "label": "Family Growth (demo)",
            "broker": "SIMULATED",
            "environment": "PAPER",
            "currency": "USD",
        },
        {
            "id": "demo-acct-002",
            "label": "EUR Income (demo)",
            "broker": "SIMULATED",
            "environment": "PAPER",
            "currency": "EUR",
        },
        {
            "id": "demo-acct-003",
            "label": "Live mirror (demo, not authorized)",
            "broker": "SIMULATED",
            "environment": "LIVE",
            "currency": "USD",
        },
    ]


def _base() -> dict:
    return {
        "synthetic": True,
        "label": DEMO_LABEL,
        "workspace": "Bhakta Family Office (demo)",
        "as_of": AS_OF,
        "period": PERIOD,
        "accounts": _accounts(),
        "account_id": "demo-acct-001",
        "feed": {"status": "connected", "age_s": 2, "reconciliation": "matched", "recon_age_s": 40},
        "pending_approvals": 1,
        "portfolio": {
            "equity": _m("125430.18"),
            "net_pnl": _m("4210.55"),
            "net_pnl_pct": "3.47",
            "deposits": _m("10000.00"),
            "withdrawals": _m("0.00"),
            "available_cash": _m("38112.40"),
            "reserved_cash": _m("2500.00"),
            "exposure_pct": "69.6",
            "open_positions": 3,
            "drawdown_pct": "-2.10",
            "fees": _m("38.20"),
        },
        "secondary_balance": {"account_id": "demo-acct-002", "equity": _m("48210.00", "EUR")},
        "stats": {
            "sample": 84,
            "costs_included": True,
            "win_rate_pct": _stat("57.1"),
            "profit_factor": _stat("1.42"),
            "trades": _stat("84"),
            "sharpe": _stat("1.12"),
            "avg_win": _stat("212.40"),
            "avg_loss": _stat("-148.90"),
        },
        "allocation": [
            {
                "strategy": "Momentum ETF rotation v3",
                "capital": _m("60000.00"),
                "weight_pct": "47.8",
            },
            {
                "strategy": "Mean reversion large-cap v1",
                "capital": _m("30000.00"),
                "weight_pct": "23.9",
            },
            {"strategy": "Unallocated cash", "capital": _m("35430.18"), "weight_pct": "28.3"},
        ],
        "positions": [
            {
                "symbol": "SPY",
                "venue": "ARCX",
                "qty": "40",
                "cost": _m("21450.00"),
                "value": _m("22880.40"),
                "pnl": _m("1430.40"),
            },
            {
                "symbol": "QQQ",
                "venue": "XNAS",
                "qty": "25",
                "cost": _m("11950.00"),
                "value": _m("12610.25"),
                "pnl": _m("660.25"),
            },
            {
                "symbol": "XLE",
                "venue": "ARCX",
                "qty": "60",
                "cost": _m("5520.00"),
                "value": _m("5302.80"),
                "pnl": _m("-217.20"),
            },
        ],
        "orders": [
            {
                "id": "demo-ord-1041",
                "symbol": "SPY",
                "side": "BUY",
                "qty": "10",
                "filled": "10",
                "limit": _m("571.90"),
                "status": "FILLED",
            },
            {
                "id": "demo-ord-1042",
                "symbol": "QQQ",
                "side": "BUY",
                "qty": "10",
                "filled": "4",
                "limit": _m("504.10"),
                "status": "PARTIALLY_FILLED",
            },
            {
                "id": "demo-ord-1043",
                "symbol": "TSLA",
                "side": "BUY",
                "qty": "15",
                "filled": "0",
                "limit": _m("251.00"),
                "status": "REJECTED",
                "reason": "risk: single-name cap 5%",
            },
        ],
        "exceptions": [
            {"kind": "partial_fill", "text": "demo-ord-1042 filled 4 of 10; remainder working"},
        ],
        "depth": {
            "entitled": True,
            "symbol": "SPY",
            "venue": "ARCX",
            "bids": [["572.10", "300"], ["572.09", "520"], ["572.08", "410"], ["572.07", "880"]],
            "asks": [["572.12", "260"], ["572.13", "450"], ["572.14", "700"], ["572.15", "390"]],
        },
        "cost_distribution": [
            {"bucket": "560-565", "qty": "8"},
            {"bucket": "565-570", "qty": "14"},
            {"bucket": "570-575", "qty": "18"},
        ],
        "signals": [
            {
                "strategy": "Momentum v3",
                "symbol": "SPY",
                "state": "LONG",
                "version": "3.2.0",
                "eligible": True,
                "evaluated": "14:29Z",
            },
            {
                "strategy": "Momentum v3",
                "symbol": "QQQ",
                "state": "LONG",
                "version": "3.2.0",
                "eligible": True,
                "evaluated": "14:29Z",
            },
            {
                "strategy": "Mean rev v1",
                "symbol": "XLE",
                "state": "ABSTAIN",
                "version": "1.0.4",
                "eligible": True,
                "evaluated": "14:25Z",
            },
            {
                "strategy": "Mean rev v1",
                "symbol": "TSLA",
                "state": "BLOCKED",
                "version": "1.0.4",
                "eligible": False,
                "evaluated": "14:25Z",
            },
        ],
        "candles": {
            "symbol": "SPY",
            "venue": "ARCX",
            "timeframe": "15m",
            "timezone": "America/New_York",
            "warmup_complete": True,
            "gap": False,
            "bars": _bars(32),
        },
        "topology": [
            {
                "trace": "tr-7781",
                "symbol": "SPY",
                "path": ["market", "signal", "risk", "order", "position"],
                "outcome": "APPROVED",
                "reason": "momentum rank 1; within 20% sleeve cap",
            },
            {
                "trace": "tr-7782",
                "symbol": "XLE",
                "path": ["market", "signal"],
                "outcome": "ABSTAIN",
                "reason": "z-score -0.4 inside entry band; hold",
            },
            {
                "trace": "tr-7783",
                "symbol": "TSLA",
                "path": ["market", "signal", "risk"],
                "outcome": "REJECTED",
                "reason": "single-name cap 5% would be exceeded",
            },
            {
                "trace": "tr-7784",
                "symbol": "QQQ",
                "path": ["market", "signal", "risk"],
                "outcome": "AWAITING_APPROVAL",
                "reason": "order above 10k notional needs approval",
            },
        ],
        "studio": {
            "templates": [
                "Momentum ETF rotation",
                "Mean reversion large-cap",
                "Covered call income",
            ],
            "selected": "Momentum ETF rotation",
            "version": "3.2.0",
            "draft_version": "3.3.0-draft",
            "universe": "SPY, QQQ, IWM, XLE, XLK",
            "warmup": "200 trading days",
            "capital": _m("60000.00"),
            "params": [
                {"name": "lookback", "value": "126", "unit": "trading days", "error": None},
                {"name": "top_n", "value": "2", "unit": "instruments", "error": None},
                {"name": "sleeve_cap", "value": "20", "unit": "% of account equity", "error": None},
                {"name": "stop_loss", "value": "8", "unit": "% below entry", "error": None},
            ],
            "results": {
                "kind": "backtest",
                "period": "2019-01-02/2026-09-30",
                "cagr_pct": "9.8",
                "max_dd_pct": "-14.2",
                "trades": "312",
                "costs": "5 bps + $0 commission",
                "benchmark": "SPY total return 12.1%",
            },
            "pipeline": {
                "draft": "done",
                "validate": "done",
                "backtest": "done",
                "paper_deploy": "ready",
                "live_review": "not_authorized",
            },
        },
        "invite": {
            "code_hint": "demo-…-7Q2K",
            "single_use": True,
            "status": "accepted",
            "inviter": "Pat (operator, demo)",
            "account_id": "demo-acct-001",
            "role": "viewer",
            "trade_permission": False,
            "mfa": "enrolled",
            "paper_setup": "complete",
            "capabilities": [
                {"name": "View portfolio", "status": "ready"},
                {"name": "Approve orders", "status": "not_granted"},
                {"name": "Live trading", "status": "not_authorized"},
            ],
        },
    }


def _loss(f: dict) -> None:
    p = f["portfolio"]
    p.update(
        equity=_m("88712.04"),
        net_pnl=_m("-7340.61"),
        net_pnl_pct="-7.64",
        deposits=_m("15000.00"),
        withdrawals=_m("2000.00"),
        available_cash=_m("20480.00"),
        exposure_pct="76.9",
        drawdown_pct="-11.85",
    )
    f["stats"].update(
        win_rate_pct=_stat("41.2"),
        profit_factor=_stat("0.71"),
        sharpe=_stat("-0.64"),
        avg_win=_stat("165.10"),
        avg_loss=_stat("-231.75"),
        trades=_stat("51"),
    )
    f["stats"]["sample"] = 51
    for pos, pnl, value in zip(
        f["positions"],
        ("-1820.40", "-940.75", "-612.30"),
        ("19629.60", "11009.25", "4907.70"),
        strict=True,
    ):
        pos["pnl"], pos["value"] = _m(pnl), _m(value)
    f["exceptions"].append(
        {"kind": "drawdown", "text": "Account drawdown -11.85% exceeds 10% alert"}
    )
    f["topology"][0].update(
        outcome="REJECTED",
        path=["market", "signal", "risk"],
        reason="drawdown breaker: new entries paused",
    )
    f["studio"]["results"].update(cagr_pct="-3.1", max_dd_pct="-27.5")
    f["studio"]["params"][2]["error"] = "Must be 1-25 % of account equity; got 40"
    f["studio"]["params"][2]["value"] = "40"
    f["studio"]["pipeline"].update(validate="failed", backtest="blocked", paper_deploy="blocked")
    f["invite"]["status"] = "accepted"


def _empty(f: dict) -> None:
    f["accounts"] = [f["accounts"][0] | {"label": "New account (demo)"}]
    f["pending_approvals"] = 0
    f["portfolio"] = {
        "equity": _m("0.00"),
        "net_pnl": None,
        "net_pnl_pct": None,
        "deposits": _m("0.00"),
        "withdrawals": _m("0.00"),
        "available_cash": _m("0.00"),
        "reserved_cash": _m("0.00"),
        "exposure_pct": None,
        "open_positions": 0,
        "drawdown_pct": None,
        "fees": _m("0.00"),
    }
    f["secondary_balance"] = None
    reason = "no closed trades in period"
    f["stats"] = {"sample": 0, "costs_included": True} | {
        k: _stat(None, reason)
        for k in ("win_rate_pct", "profit_factor", "trades", "sharpe", "avg_win", "avg_loss")
    }
    f["allocation"], f["positions"], f["orders"], f["exceptions"] = [], [], [], []
    f["cost_distribution"], f["signals"], f["topology"] = [], [], []
    f["candles"]["bars"] = []
    f["candles"]["warmup_complete"] = False
    f["studio"]["pipeline"] = {
        "draft": "todo",
        "validate": "todo",
        "backtest": "todo",
        "paper_deploy": "todo",
        "live_review": "not_authorized",
    }
    f["studio"]["results"] = None
    f["invite"].update(status="pending", mfa="optional", paper_setup="pending")
    f["invite"]["capabilities"][0]["status"] = "pending"


def _stale(f: dict) -> None:
    f["feed"] = {
        "status": "disconnected",
        "age_s": 431,
        "reconciliation": "stale",
        "recon_age_s": 1260,
    }
    f["exceptions"].insert(
        0, {"kind": "stale", "text": "Market data feed lost 7m 11s ago; actions paused"}
    )
    f["depth"]["stale"] = True
    f["candles"]["gap"] = True
    f["invite"].update(status="expired", paper_setup="pending", mfa="optional")


def _unknown(f: dict) -> None:
    f["feed"] = {
        "status": "connected",
        "age_s": 3,
        "reconciliation": "reconciling",
        "recon_age_s": 95,
    }
    p = f["portfolio"]
    p["equity"], p["net_pnl"], p["net_pnl_pct"], p["drawdown_pct"] = None, None, None, None
    p["valuation_unavailable_reason"] = "position valuations pending reconciliation"
    f["stats"]["sharpe"] = _stat(None, "sample of 9 trades below 30-trade minimum")
    f["stats"]["profit_factor"] = _stat(None, "sample of 9 trades below 30-trade minimum")
    f["stats"]["sample"] = 9
    f["stats"]["trades"] = _stat("9")
    f["orders"][1].update(
        status="UNKNOWN", filled=None, reason="broker acknowledgement not received; reconciling"
    )
    f["exceptions"] = [
        {"kind": "unknown", "text": "demo-ord-1042 status UNKNOWN; reconciling with broker"}
    ]
    f["depth"] = {
        "entitled": False,
        "symbol": "SPY",
        "venue": "ARCX",
        "reason": "no L2 depth entitlement for this account",
    }
    f["topology"][3].update(
        outcome="RECONCILING",
        path=["market", "signal", "risk", "order"],
        reason="order sent; broker state unknown",
    )
    f["topology"].append(
        {
            "trace": "tr-7785",
            "symbol": "IWM",
            "path": ["market", "signal"],
            "outcome": "UNKNOWN",
            "reason": "evaluation result not recorded",
        }
    )
    f["invite"]["capabilities"][0]["status"] = "unknown"


_MUTATORS = {"good": None, "loss": _loss, "empty": _empty, "stale": _stale, "unknown": _unknown}


def fixture(state: str) -> dict:
    if state not in _MUTATORS:
        raise KeyError(f"unknown fixture state {state!r}; expected one of {STATES}")
    f = deepcopy(_base())
    f["state"] = state
    if _MUTATORS[state]:
        _MUTATORS[state](f)
    return f


def all_fixtures() -> dict[str, dict]:
    return {s: fixture(s) for s in STATES}
