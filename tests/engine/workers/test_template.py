"""ALG-3281 template paper runner: attributable orders, frozen params, restart, flip."""

import json
import sys
import time
from decimal import Decimal

import pytest

from algobots.demo import bars as BARS
from algobots.demo import blotter as B
from algobots.demo import studio as S
from algobots.engine.workers import template as T
from algobots.engine.workers.supervisor import Supervisor

T0 = 1_790_000_000.0  # deploy time
SIX_H = T0 + 6 * 3600
D = Decimal


def _deploy(sd, h, account, amount="300", now=T0):
    _, (dep,), _ = S.deploy(sd, h, [account], mode="equal", amount=D(amount), actor="t", now=now)
    return dep


def _run(dep, sd, *steps, killed=False):
    r = T.TemplateRunner(dep, sd)
    r.reconcile()
    return r, [o for now in steps for o in r.step(now, killed)]


@pytest.fixture
def three(tmp_path):
    """trend v2 on eq-a, trend v3 on eq-b, range/RSI v2 on eq-a: three parameter sets."""
    sd = str(tmp_path)
    tv2 = S.edit(sd, "trend", {"cadence": "1m", "fast": 3, "slow": 8}, actor="t", now=T0)
    tv3 = S.edit(sd, "trend", {"cadence": "5m", "fast": 5, "slow": 13}, actor="t", now=T0)
    rv2 = S.edit(
        sd, "range_rsi", {"cadence": "5m", "period": 6, "lower": 35, "upper": 65}, actor="t"
    )
    deps = [
        _deploy(sd, tv2.hash, "eq-a"),
        _deploy(sd, tv3.hash, "eq-b"),
        _deploy(sd, rv2.hash, "eq-a"),
    ]
    return sd, deps


def test_three_instances_produce_orders_attributed_to_their_deployment(three):
    sd, deps = three
    for dep in deps:
        _, orders = _run(dep, sd, SIX_H)
        assert orders, f"{dep.id} placed no orders"
        assert {o["deployment"] for o in orders} == {dep.id}
        assert {o["artifact"] for o in orders} == {dep.hash[:12]}
        assert {o["account"] for o in orders} == {dep.account}
        assert all(o["ts"] > dep.created_ts for o in orders)  # no backfilled history
        sym = dep.params["symbol"]
        for o in orders:  # fills at the synthetic bar close of the bar that signalled
            assert o["price"] == str(BARS.close(sym, dep.params["cadence"], o["n"]))
    assert len({d.hash for d in deps}) == 3

    # Orders pane source: filterable by account, every line keeps its attribution.
    tpl = T.load_orders(sd)
    eq_a = B.orders(_empty_ledger(), "eq-a", None, None, tpl)
    assert {o["deployment"] for o in eq_a} == {deps[0].id, deps[2].id}
    eq_b = B.orders(_empty_ledger(), "eq-b", None, None, tpl)
    assert {o["deployment"] for o in eq_b} == {deps[1].id}
    assert B.orders(_empty_ledger(), "eq-c", None, None, tpl) == []

    # Accounts: per-account equity/orders roll up from the same log.
    summ = T.summary(S.load(sd), tpl, SIX_H)
    assert summ["eq-a"]["orders"] == len(eq_a) and summ["eq-b"]["orders"] == len(eq_b)
    assert summ["eq-a"]["allocated"] == D("600")


def _empty_ledger():
    from algobots.demo import ledger as L

    return L.build([])


def test_editing_the_template_mid_run_does_not_change_a_running_deployment(tmp_path):
    sd, ref_sd = str(tmp_path / "a"), str(tmp_path / "ref")
    params = {"cadence": "1m", "fast": 3, "slow": 8}
    v = S.edit(sd, "trend", params, actor="t", now=T0)
    dep = _deploy(sd, v.hash, "eq-a")
    S.edit(ref_sd, "trend", params, actor="t", now=T0)
    ref = _deploy(ref_sd, v.hash, "eq-a")
    mid = T0 + 3 * 3600

    runner, before = _run(dep, sd, mid)
    edited = S.edit(sd, "trend", {"cadence": "1m", "fast": 2, "slow": 30}, actor="t", now=mid)
    assert edited.version == v.version + 1 and edited.hash != v.hash
    after = runner.step(SIX_H)
    # ...and a worker restarted after the edit reloads the same frozen deployment.
    (reloaded,) = [d for d in S.load(sd).deployments if d.id == dep.id]
    assert reloaded.params == {**params, "symbol": "SPY"} and reloaded.hash == v.hash
    _, restarted = _run(reloaded, sd, SIX_H + 3600)

    _, expected = _run(ref, ref_sd, SIX_H + 3600)  # never edited
    got = before + after + restarted
    assert [(o["n"], o["side"], o["qty"], o["price"]) for o in got] == [
        (o["n"], o["side"], o["qty"], o["price"]) for o in expected
    ]
    assert {o["artifact"] for o in got} == {v.short}


def test_tampered_frozen_params_refuse_to_run(three):
    sd, deps = three
    doc = json.loads((S._path(sd)).read_text())
    doc["deployments"][0]["params"]["fast"] = 4
    S._path(sd).write_text(json.dumps(doc))
    (bad,) = [d for d in S.load(sd).deployments if d.id == deps[0].id]
    with pytest.raises(T.Tampered):
        T.TemplateRunner(bad, sd)


def test_restart_reconciles_from_the_log_without_duplicates(three):
    sd, deps = three
    dep = deps[0]
    _, first = _run(dep, sd, T0 + 3 * 3600)
    T._cursor_path(sd, dep.id).unlink()  # crash after the log append, before the cursor
    r, again = _run(dep, sd, T0 + 3 * 3600)
    assert again == [] and r.book.filled == len(first)
    _, later = _run(dep, sd, SIX_H)
    log = T.read_log(T.orders_path(sd, dep.id))
    assert len(log) == len({o["id"] for o in log}) == len(first) + len(later)


def test_kill_switch_blocks_entries_but_not_exits(three):
    sd, deps = three
    _, orders = _run(deps[0], sd, SIX_H, killed=True)
    buys = [o for o in orders if o["side"] == "BUY"]
    assert buys and all(o["status"] == "blocked" and o["qty"] == "0" for o in buys)
    assert not [o for o in orders if o["side"] == "SELL"]  # never got in, nothing to exit
    assert all("kill switch" in o["reason"] for o in buys)


def test_etf_allocation_buys_targets_then_rebalances_on_drift(tmp_path):
    sd = str(tmp_path)
    v = S.edit(
        sd,
        "etf_alloc",
        {
            "weights": {"SPY": 0.6, "AGG": 0.3, "GLD": 0.1},
            "rebalance": "weekly",
            "drift_band": 0.001,
        },
        actor="t",
    )
    dep = _deploy(sd, v.hash, "eq-c", "400")
    r, orders = _run(dep, sd, T0 + 15 * 86400)
    initial = [o for o in orders if o["reason"] == "initial allocation"]
    assert {o["instrument"] for o in initial} == {"SPY", "AGG", "GLD"}
    assert all(o["side"] == "BUY" for o in initial)
    rebal = [o for o in orders if "weekly rebalance" in o["reason"]]
    assert rebal and {o["deployment"] for o in rebal} == {dep.id}
    assert r.book.cash >= 0


def test_supervisor_flips_pending_to_running_only_after_heartbeat(tmp_path, monkeypatch):
    from algobots.api.config import get_settings
    from algobots.demo import router as R

    monkeypatch.setenv("ALGOBOTS_DEMO_STATE_DIR", str(tmp_path))
    get_settings.cache_clear()
    sd = str(tmp_path)
    v = S.edit(sd, "trend", {"cadence": "1m", "fast": 3, "slow": 8}, actor="t")
    dep = _deploy(sd, v.hash, "eq-a", now=time.time())
    sup = Supervisor(
        [], tmp_path, poll=0.5, command=[sys.executable, "-m", "algobots.engine.workers.template"]
    )
    monkeypatch.setattr(R, "TEMPLATES", sup)
    try:
        R.sync_templates()
        assert _state(sd, dep.id) == "pending"  # spawned, not yet heartbeating ready
        deadline = time.time() + 30
        while time.time() < deadline and _state(sd, dep.id) != "running":
            R.sync_templates()
            time.sleep(0.2)
        assert _state(sd, dep.id) == "running"
        assert sup.status(dep.id).state == "ready"
        hb = json.loads((tmp_path / "workers" / f"{dep.id}.json").read_text())
        assert hb["artifact"] == v.short and hb["paper_account"] == "eq-a"
    finally:
        sup.stop()
        get_settings.cache_clear()


def _state(sd, dep_id):
    return next(d.state for d in S.load(sd).deployments if d.id == dep_id)


def test_demo_page_and_api_show_template_orders_per_account(three, monkeypatch):
    from fastapi.testclient import TestClient

    from algobots.api.config import get_settings
    from algobots.api.main import app

    sd, deps = three
    for dep in deps:
        _run(dep, sd, time.time())  # trade every closed bar up to now
    monkeypatch.setenv("ALGOBOTS_DEMO_STATE_DIR", sd)
    monkeypatch.setenv("ALGOBOTS_DEMO_FEED_PATH", f"{sd}/none.jsonl")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        api = client.get("/demo/api/orders", params={"account": "eq-b", "limit": 5000}).json()
        assert api["orders"] and {o["deployment"] for o in api["orders"]} == {deps[1].id}
        assert {o["artifact"] for o in api["orders"]} == {deps[1].hash[:12]}
        page = client.get("/demo?account=eq-a")
        assert page.status_code == 200
        assert f'data-deployment="{deps[0].id}"' in page.text
        assert f'data-deployment="{deps[2].id}"' in page.text
        assert deps[1].id not in page.text  # eq-b context never leaks into eq-a
        assert "Pat · Equities paper A" in page.text and BARS.SOURCE in page.text
        assert client.get("/demo?account=eq-z").status_code == 404
        home = client.get("/demo?view=orders").text  # aggregate view: every deployment's orders
        assert all(f'data-deployment="{d.id}"' in home for d in deps)
        assert 'data-account="eq-b"' in home
    finally:
        get_settings.cache_clear()
