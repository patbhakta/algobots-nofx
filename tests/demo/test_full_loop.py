"""Judgement rules of the full-loop verifier (ALG-3403), without the .243 stack."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "full_loop", Path(__file__).with_name("full_loop.py")
)
FL = importlib.util.module_from_spec(_spec)
sys.modules["full_loop"] = FL
_spec.loader.exec_module(FL)


def _worker(**kw):
    return {"state": "ready", "orders_filled": 0, "intervals": 0, **kw}


def _status(facts):
    return {h.key: h.status for h in FL.judge(facts)}


def test_unreachable_stack_is_all_missing():
    assert set(_status(FL.Facts()).values()) == {FL.MISSING}


def test_243_as_of_oct_22_is_stubbed_where_something_answers():
    facts = FL.Facts(
        api_paths=["/demo/api/strategies", "/demo/api/v1/{account}/orders/place", "/healthz"],
        gateway_health=404,
        redis_cmd_streams=[],
        api_nautilus="1.231.0",
        marimo_nautilus="2.0.0rc6",
        workers={"workers": [_worker(orders_filled=2), _worker()]},
        studio_versions=3,
        feed_path="/feeds/kalshi/observations.jsonl",
        feed_age_s=None,
        marimo_http=303,
        evidence_notebooks=[],
    )
    assert _status(facts) == {
        "studio": FL.STUBBED,
        "gateway": FL.STUBBED,
        "nautilus": FL.STUBBED,
        "datafeed": FL.MISSING,
        "marimo": FL.STUBBED,
    }


def test_every_hop_wired_passes():
    facts = FL.Facts(
        api_paths=["/api/studio/strategies"],
        gateway_health=200,
        redis_cmd_streams=["algobots:cmd:node-laya"],
        node_nautilus=FL.NAUTILUS_PIN,
        node_fills=1,
        workers={"workers": [_worker(orders_filled=1, intervals=4)]},
        feed_age_s=60.0,
        marimo_http=200,
        evidence_notebooks=["/nb/demo_evidence.py"],
    )
    assert set(_status(facts).values()) == {FL.WIRED}


def test_wrong_nautilus_or_stale_feed_is_not_wired():
    base = dict(workers={"workers": [_worker(orders_filled=1, intervals=4)]})
    assert _status(FL.Facts(api_nautilus="1.231.0", **base))["nautilus"] == FL.STUBBED
    stale = FL.Facts(feed_age_s=FL.FEED_MAX_AGE_S + 1, **base)
    assert _status(stale)["datafeed"] == FL.STUBBED


def test_the_rc6_node_with_fills_is_wired_whatever_the_api_image_runs():
    """ALG-3405: the hop is the node container, not the API's 1.x workers."""
    node = dict(api_nautilus="1.231.0", node_nautilus=FL.NAUTILUS_PIN)
    assert _status(FL.Facts(node_fills=2, **node))["nautilus"] == FL.WIRED
    assert _status(FL.Facts(node_fills=0, **node))["nautilus"] == FL.STUBBED
    wrong = FL.Facts(node_nautilus="1.231.0", node_fills=2)
    assert _status(wrong)["nautilus"] == FL.MISSING
