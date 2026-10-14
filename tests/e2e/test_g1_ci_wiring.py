"""GATE G1 runs in CI on every merge — asserted, not assumed.

ALG-3373 does not say "measure this once"; it says *this test runs in CI on
every merge*. That makes the workflow part of the deliverable, and it makes one
failure mode worse than the gate going red: the gate quietly going **grey**.
``tests/e2e`` skips without services, and a skipped test is a green test, so
deleting a service container from the workflow would turn the Phase 1 gate off
while CI kept reporting success — and Phase 2 and the P6.2 signal service both
start on the strength of that success.

These assertions run with no services at all, which is the point: they are the
part of the gate that cannot itself be skipped.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
GATE_JOB = "gate-g1"

#: The two variables ``tests/e2e/conftest.py`` skips on. If the job stops
#: setting either, the gate stops running.
REQUIRED_ENV = ("ALGOBOTS_GATEWAY_TEST_PG_URL", "ALGOBOTS_TEST_REDIS_URL")


def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def gate_job() -> dict:
    jobs = workflow()["jobs"]
    assert GATE_JOB in jobs, f"{WORKFLOW.name} has no {GATE_JOB!r} job — GATE G1 would not run"
    return jobs[GATE_JOB]


def test_ci_runs_the_gate_on_pull_requests_and_on_main():
    """Both triggers: the gate is a merge gate, not a nightly."""
    triggers = workflow()[True]  # YAML 1.1 reads the `on:` key as a boolean
    assert "pull_request" in triggers
    assert "main" in triggers["push"]["branches"]


def test_the_gate_job_starts_the_postgres_and_redis_the_gate_needs():
    """Phase 0's two services. Without them every e2e test skips."""
    services = gate_job()["services"]
    assert "postgres" in services, "no Postgres service — the projection would have nowhere to live"
    assert "redis" in services, "no Redis service — neither leg of the order path would exist"
    assert services["postgres"]["image"].startswith("postgres:")
    assert services["redis"]["image"].startswith("redis:")


def test_the_gate_job_points_the_tests_at_those_services():
    env = gate_job()["env"]
    for name in REQUIRED_ENV:
        assert name in env, f"{name} is unset, so tests/e2e would skip and CI would stay green"
    assert "127.0.0.1" in env["ALGOBOTS_GATEWAY_TEST_PG_URL"]
    assert env["ALGOBOTS_TEST_REDIS_URL"].startswith("redis://")


def test_the_gate_job_installs_the_postgres_driver():
    """``psycopg`` is in the ``postgres`` extra, not ``dev``."""
    installs = [
        step["run"] for step in gate_job()["steps"] if "pip install" in str(step.get("run", ""))
    ]
    assert installs, "the gate job installs nothing"
    assert any("postgres" in line for line in installs), installs


def test_the_gate_job_runs_the_same_script_a_human_runs():
    """``scripts/verify_g1.py``, which fails on a skip as well as on a failure."""
    runs = [str(step.get("run", "")) for step in gate_job()["steps"]]
    assert any("scripts/verify_g1.py" in line for line in runs), runs


def test_the_measurement_is_kept_as_a_build_artifact():
    """ALG-3373 closes on a measured latency, so CI has to retain one."""
    uploads = [
        step for step in gate_job()["steps"] if "upload-artifact" in str(step.get("uses", ""))
    ]
    assert uploads, "the gate's measurement is never uploaded"
    assert any("g1-latency.json" in str(step["with"]["path"]) for step in uploads), uploads
