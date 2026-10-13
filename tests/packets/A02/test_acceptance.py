"""A02 acceptance cases 1-4 (ALG-3098), run as real processes where it matters.

AC1 races claimants as separate OS processes (and threads) against one
state file; AC2/AC4 drive the CLI with real clock time so lease expiry is
genuine; AC3 proves a failed integration keeps dependents ineligible
although the branch receipt said "passed". The fixture graph is
deterministic and reproducible: tests/packets/A02/fixtures/task-graph.json.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from tools.agent_queue.authority import ClaimDenied, TaskAuthority
from tools.agent_queue.graph import TaskGraph

ROOT = Path(__file__).resolve().parents[3]
GRAPH = Path(__file__).resolve().parent / "fixtures" / "task-graph.json"
TTL = 0.4  # real seconds; short so expiry tests are quick but not flaky


@pytest.fixture()
def state(tmp_path):
    return tmp_path / "state.json"


def cli(state: Path, *args: str, ttl: float = TTL) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "tools.agent_queue", "--graph", str(GRAPH),
         "--state", str(state), "--lease-ttl", str(ttl), *args],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )


def payload(result: subprocess.CompletedProcess) -> dict:
    return json.loads(result.stdout.strip().splitlines()[-1])


# -- AC1: two concurrent claimants produce exactly one active claim --------


def test_ac1_concurrent_processes_produce_exactly_one_active_claim(state):
    procs = [
        subprocess.Popen(
            [sys.executable, "-m", "tools.agent_queue", "--graph", str(GRAPH),
             "--state", str(state), "--lease-ttl", str(TTL),
             "claim", "ROOT", f"owner-{i}"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for i in range(6)
    ]
    outputs = [(p.wait(timeout=60), p.communicate()[0]) for p in procs]
    codes = [code for code, _ in outputs]
    assert codes.count(0) == 1, f"expected exactly one winner, got exits {codes}"
    assert codes.count(2) == len(codes) - 1, f"losers must exit denied(2): {codes}"
    for _, out in outputs:
        assert json.loads(out.strip().splitlines()[-1])["event"] == "claim"
    snap = json.loads(cli(state, "status").stdout)
    root = snap["tasks"]["ROOT"]
    assert root["status"] == "ACTIVE"
    assert root["epoch"] == 1
    assert root["owner"].startswith("owner-")


def test_ac1_concurrent_threads_produce_exactly_one_active_claim(state, tmp_path):
    graph = TaskGraph.load(GRAPH)
    claims: list = []
    errors: list = []
    barrier = threading.Barrier(8)

    def contender(i: int) -> None:
        authority = TaskAuthority(state, graph, lease_ttl_s=TTL)
        barrier.wait()
        try:
            claims.append(authority.claim("ROOT", f"owner-{i}"))
        except ClaimDenied as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=contender, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert len(claims) == 1, f"{len(claims)} claims won; denial errors: {errors}"
    assert len(errors) == 7
    snap = TaskAuthority(state, graph).snapshot()
    assert snap["tasks"]["ROOT"]["status"] == "ACTIVE"
    assert snap["tasks"]["ROOT"]["epoch"] == 1


# -- AC2: expired/revoked attempt cannot merge or publish ------------------


def test_ac2_expired_attempt_cannot_complete(state):
    assert cli(state, "claim", "ROOT", "owner-1").returncode == 0
    time.sleep(TTL + 0.2)
    denied = cli(state, "complete", "ROOT", "owner-1", "1", "passed")
    assert denied.returncode == 3, denied.stdout  # StaleAttemptError
    assert "expired" in payload(denied)["reason"]
    denied2 = cli(state, "integrate", "ROOT", "owner-1", "1",
                  "--commit", "f4c1e2a", "--review-commit", "f4c1e2a")
    assert denied2.returncode == 3, denied2.stdout


def test_ac2_revoked_attempt_cannot_publish_after_reclaim(state):
    assert cli(state, "claim", "ROOT", "owner-1").returncode == 0
    time.sleep(TTL + 0.2)
    reclaimed = cli(state, "claim", "ROOT", "owner-2")
    assert reclaimed.returncode == 0
    assert payload(reclaimed)["epoch"] == 2
    for args in (
        ("complete", "ROOT", "owner-1", "1", "passed"),
        ("integrate", "ROOT", "owner-1", "1", "--commit", "f4c1e2a",
         "--review-commit", "f4c1e2a"),
    ):
        stale = cli(state, *args)
        assert stale.returncode == 3, stale.stdout
        assert "superseded" in payload(stale)["reason"]


# -- AC3: failed integration leaves dependents ineligible ------------------


def test_ac3_failed_integration_leaves_dependents_ineligible(state, tmp_path):
    graph = TaskGraph.load(GRAPH)
    authority = TaskAuthority(state, graph, lease_ttl_s=60)
    claim = authority.claim("ROOT", "tl")
    authority.complete("ROOT", "tl", claim.epoch, "passed", note="branch green")
    authority.integration_failed("ROOT", "tl", claim.epoch, note="merge broke CI")

    root = authority.status("ROOT")
    assert root["status"] != "DONE"  # branch tests passed, integration did not
    assert any(r["result"] == "passed" for r in root["receipts"])
    with pytest.raises(ClaimDenied, match="dependencies not DONE: ROOT"):
        authority.claim("A", "owner-2")  # A never becomes eligible, own branch irrelevant
    denied = cli(state, "claim", "A", "owner-2", ttl=60)
    assert denied.returncode == 2
    assert "dependencies not DONE" in payload(denied)["reason"]


# -- AC4: budget exhaustion checkpoints without an infinite retry loop ----


def test_ac4_budget_exhaustion_checkpoints_without_retry_loop(state, tmp_path):
    graph = TaskGraph.load(GRAPH)
    authority = TaskAuthority(state, graph, lease_ttl_s=60)

    def worker_loop() -> int:
        rounds = 0
        while True:
            rounds += 1
            try:
                claim = authority.claim("TIGHT", "worker")
            except ClaimDenied as exc:
                assert "blocked" in exc.reason, exc.reason
                return rounds  # blocked: the loop cannot restart
            authority.complete("TIGHT", "worker", claim.epoch, "failed",
                               note="same defect")
            if authority.status("TIGHT")["status"] == "BLOCKED":
                return rounds

    rounds = worker_loop()
    assert rounds == 2  # budget_attempts=2, then the authority checkpointed it
    blocked = authority.blocked_record("TIGHT")
    assert blocked is not None
    assert blocked.reason.startswith("same-failure repair cap") or \
        blocked.reason.startswith("budget exhausted")
    assert blocked.attempts == 2
    # repeated claims are idempotent denials: no loop can restart by asking again
    for _ in range(3):
        denied = cli(state, "claim", "TIGHT", "worker", ttl=60)
        assert denied.returncode == 2
        assert "blocked" in payload(denied)["reason"]
    # ...and the in-process loop exits immediately on the same denial
    assert worker_loop() == 1
