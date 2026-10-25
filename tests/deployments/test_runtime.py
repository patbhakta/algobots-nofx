"""Deployment intent owns exactly one isolated paper process."""

import copy
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tests.strategies.test_deploy_evidence import NOFX_MOMENTUM

from algobots.api.deployments.runtime import DeploymentRuntime, launch_spec
from algobots.strategies.studio import compile_studio_strategy, parse_draft, translate_nofx_config


def deployment():
    draft = translate_nofx_config("owned momentum", NOFX_MOMENTUM)[0]
    artifact = compile_studio_strategy(parse_draft(draft)).model_dump(mode="json")
    return SimpleNamespace(
        id=uuid4(),
        account_id=uuid4(),
        user_id=uuid4(),
        status="running",
        breaker_state="closed",
        symbol="KXBTC15M",
        artifact_hash=artifact["artifact_hash"],
        max_order_value="5",
        max_daily_loss="20",
        frozen_spec={
            "kind": "studio-artifact",
            "artifact": artifact,
            "studio_evidence": {"artifact_hash": artifact["artifact_hash"]},
        },
    )


def account(d):
    return SimpleNamespace(
        id=d.account_id, user_id=d.user_id, mode="paper", status="active", approval_mode="auto"
    )


class Process:
    def __init__(self):
        self.code = None
        self.terminated = False

    def poll(self):
        return self.code

    def terminate(self):
        self.terminated = True
        self.code = 0

    def wait(self, timeout):
        return self.code


def test_running_launches_once_and_stop_terminates():
    d = deployment()
    started = []

    def spawn(spec):
        p = Process()
        started.append((spec, p))
        return p

    runtime = DeploymentRuntime(spawn=spawn)
    runtime.reconcile([(d, account(d), None)])
    runtime.reconcile([(d, account(d), None)])
    assert len(started) == 1
    spec, child = started[0]
    assert spec.node == f"deployment-{d.id.hex}"
    assert spec.environment["ALGOBOTS_FEED"] == "kalshi"
    assert (
        json.loads(spec.environment["ALGOBOTS_DEPLOYMENT_SNAPSHOT"])["artifact"]
        == d.frozen_spec["artifact"]
    )
    d.status = "stopped"
    runtime.reconcile([(d, account(d), None)])
    assert child.terminated
    assert not runtime.children


@pytest.mark.parametrize(
    "field,value",
    [
        ("mode", "live"),
        ("status", "disabled"),
        ("approval_mode", "semi_auto"),
        ("user_id", uuid4()),
    ],
)
def test_account_refusals(field, value):
    d = deployment()
    a = account(d)
    setattr(a, field, value)
    with pytest.raises(ValueError):
        launch_spec(d, a)


@pytest.mark.parametrize("halt", ["paused", "deleted", "breaker", "fleet"])
def test_every_halt_stops_process(halt):
    d = deployment()
    child = Process()
    runtime = DeploymentRuntime(spawn=lambda spec: child)
    runtime.reconcile([(d, account(d), None)])
    fleet = None
    if halt == "paused":
        d.status = "paused"
    elif halt == "breaker":
        d.breaker_state = "open"
    elif halt == "fleet":
        fleet = SimpleNamespace(state="open")
    runtime.reconcile([] if halt == "deleted" else [(d, account(d), fleet)])
    assert child.terminated


def test_rejects_changed_frozen_artifact():
    d = deployment()
    d.frozen_spec = copy.deepcopy(d.frozen_spec)
    d.frozen_spec["artifact"]["nautilus"]["params"]["min_edge"] = 0
    with pytest.raises(ValueError, match="artifact"):
        launch_spec(d, account(d))


def test_unexpected_exit_is_visible_and_not_silently_restarted():
    d = deployment()
    child = Process()
    runtime = DeploymentRuntime(spawn=lambda spec: child)
    runtime.reconcile([(d, account(d), None)])
    child.code = 17
    runtime.reconcile([(d, account(d), None)])
    assert runtime.failures[str(d.id)] == "worker exited: 17"
    assert not runtime.children
    runtime.reconcile([(d, account(d), None)])
    assert not runtime.children


def test_spawn_drops_credentials_and_uses_fixed_module(monkeypatch):
    import algobots.api.deployments.runtime as runtime_module
    from algobots.api.deployments.runtime import spawn_node

    monkeypatch.setenv("KALSHI_API_KEY", "must-not-reach-child")
    monkeypatch.setenv("DATABASE_URL", "must-not-reach-child")
    monkeypatch.setenv("ALGOBOTS_FEED", "synthetic")
    monkeypatch.setenv("ALGOBOTS_KALSHI_PATH", "/feeds/kalshi/observations.jsonl")
    calls = []
    monkeypatch.setattr(runtime_module.subprocess, "Popen", lambda *a, **kw: calls.append((a, kw)))
    d = deployment()
    spawn_node(launch_spec(d, account(d)))
    args, kwargs = calls[0]
    assert args[0][-2:] == ["-m", "algobots.node.paper_node"]
    assert "KALSHI_API_KEY" not in kwargs["env"]
    assert "DATABASE_URL" not in kwargs["env"]
    assert kwargs["env"]["ALGOBOTS_FEED"] == "kalshi"
    assert kwargs["env"]["ALGOBOTS_KALSHI_PATH"] == "/feeds/kalshi/observations.jsonl"
    assert kwargs["start_new_session"] is True


def test_close_stops_all_children():
    a, b = deployment(), deployment()
    children = []

    def spawn(spec):
        child = Process()
        children.append(child)
        return child

    runtime = DeploymentRuntime(spawn=spawn)
    runtime.reconcile([(a, account(a), None), (b, account(b), None)])
    assert len(children) == 2
    runtime.close()
    assert all(c.terminated for c in children)
    assert not runtime.children
