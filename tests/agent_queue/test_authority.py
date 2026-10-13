"""TaskAuthority semantics (A02): claims, epochs, leases, budgets, locks.

Single-process tests with an injected clock; the cross-process races live
in tests/packets/A02 (acceptance). Statuses start all BACKLOG because the
graph file is the specification, never the state.
"""

from __future__ import annotations

import json

import pytest
from tools.agent_queue.authority import (
    ACTIVE,
    BACKLOG,
    BLOCKED,
    DONE,
    WAITING_INTEGRATION,
    ClaimDenied,
    InvalidTransition,
    StaleAttemptError,
    TaskAuthority,
)
from tools.agent_queue.contracts import BlockedRecord
from tools.agent_queue.graph import TaskGraph

TTL = 100.0


def make_authority(tmp_path, tasks, now=1000.0):
    clock = {"t": now}
    graph = TaskGraph.from_mapping({"tasks": tasks})
    authority = TaskAuthority(tmp_path / "state.json", graph, lease_ttl_s=TTL,
                              clock=lambda: clock["t"])
    return authority, clock


def run_to_done(authority, task_id, owner, commit="abc1234", now=None):
    claim = authority.claim(task_id, owner, now=now)
    authority.complete(task_id, owner, claim.epoch, "passed", now=now)
    return authority.integrate(
        task_id, owner, claim.epoch, commit=commit, review_commit=commit, now=now
    )


class TestClaim:
    def test_initial_state_all_backlog(self, tmp_path):
        authority, _ = make_authority(tmp_path, [{"id": "A"}, {"id": "B", "deps": ["A"]}])
        snap = authority.snapshot()
        assert all(row["status"] == BACKLOG for row in snap["tasks"].values())
        assert all(row["epoch"] == 0 for row in snap["tasks"].values())

    def test_dependency_not_done_denies_claim(self, tmp_path):
        authority, _ = make_authority(tmp_path, [{"id": "A"}, {"id": "B", "deps": ["A"]}])
        with pytest.raises(ClaimDenied, match="dependencies not DONE: A"):
            authority.claim("B", "owner-1")

    def test_claim_grants_lease_epoch_and_worktree(self, tmp_path):
        authority, _ = make_authority(tmp_path, [{"id": "A02"}])
        claim = authority.claim("A02", "tl")
        assert (claim.epoch, claim.owner) == (1, "tl")
        assert claim.lease_expires_at == 1000.0 + TTL
        assert claim.worktree == ".wt-a02"
        assert authority.status("A02")["status"] == ACTIVE

    def test_second_claim_while_lease_live_is_denied(self, tmp_path):
        authority, _ = make_authority(tmp_path, [{"id": "A02"}])
        authority.claim("A02", "owner-1")
        with pytest.raises(ClaimDenied, match="active lease held by owner-1"):
            authority.claim("A02", "owner-2")

    def test_expired_lease_is_reclaimable_and_bumps_epoch(self, tmp_path):
        authority, clock = make_authority(tmp_path, [{"id": "A02"}])
        first = authority.claim("A02", "owner-1")
        clock["t"] += TTL + 1
        second = authority.claim("A02", "owner-2")
        assert second.epoch == first.epoch + 1
        assert second.owner == "owner-2"


class TestHeartbeat:
    def test_heartbeat_extends_lease(self, tmp_path):
        authority, clock = make_authority(tmp_path, [{"id": "A02"}])
        claim = authority.claim("A02", "owner-1")
        clock["t"] += 60
        renewed = authority.heartbeat("A02", "owner-1", claim.epoch)
        assert renewed.lease_expires_at == clock["t"] + TTL

    def test_heartbeat_with_wrong_epoch_is_stale(self, tmp_path):
        authority, _ = make_authority(tmp_path, [{"id": "A02"}])
        authority.claim("A02", "owner-1")
        with pytest.raises(StaleAttemptError, match="superseded"):
            authority.heartbeat("A02", "owner-1", epoch=99)


class TestCompleteAndIntegrate:
    def test_happy_path_to_done_makes_dependent_claimable(self, tmp_path):
        authority, _ = make_authority(tmp_path, [{"id": "A"}, {"id": "B", "deps": ["A"]}])
        receipt = run_to_done(authority, "A", "owner-1")
        assert receipt.result == "integrated"
        assert authority.status("A")["status"] == DONE
        assert authority.status("A")["integrated_commit"] == "abc1234"
        claim = authority.claim("B", "owner-2")  # no ClaimDenied
        assert claim.epoch == 1

    def test_complete_passed_waits_for_integration(self, tmp_path):
        authority, _ = make_authority(tmp_path, [{"id": "A"}, {"id": "B", "deps": ["A"]}])
        claim = authority.claim("A", "owner-1")
        authority.complete("A", "owner-1", claim.epoch, "passed")
        assert authority.status("A")["status"] == WAITING_INTEGRATION
        with pytest.raises(ClaimDenied, match="awaits integration"):
            authority.claim("A", "owner-2")
        with pytest.raises(ClaimDenied, match="dependencies not DONE: A"):
            authority.claim("B", "owner-2")

    def test_duplicate_passing_receipt_is_rejected(self, tmp_path):
        authority, _ = make_authority(tmp_path, [{"id": "A"}])
        claim = authority.claim("A", "owner-1")
        authority.complete("A", "owner-1", claim.epoch, "passed")
        with pytest.raises(InvalidTransition, match="already published"):
            authority.complete("A", "owner-1", claim.epoch, "passed")

    def test_integrate_requires_exact_commit_review(self, tmp_path):
        authority, _ = make_authority(tmp_path, [{"id": "A"}])
        claim = authority.claim("A", "owner-1")
        authority.complete("A", "owner-1", claim.epoch, "passed")
        with pytest.raises(InvalidTransition, match="exact-commit review required"):
            authority.integrate(
                "A", "owner-1", claim.epoch, commit="abc1234", review_commit="def5678"
            )

    def test_integrate_without_passing_receipt_is_invalid(self, tmp_path):
        authority, _ = make_authority(tmp_path, [{"id": "A"}])
        claim = authority.claim("A", "owner-1")
        with pytest.raises(InvalidTransition, match="passing receipt first"):
            authority.integrate(
                "A", "owner-1", claim.epoch, commit="abc1234", review_commit="abc1234"
            )

    def test_done_task_cannot_be_claimed(self, tmp_path):
        authority, _ = make_authority(tmp_path, [{"id": "A"}])
        run_to_done(authority, "A", "owner-1")
        with pytest.raises(ClaimDenied, match="task is DONE"):
            authority.claim("A", "owner-2")


class TestStaleAttempts:
    def test_expired_attempt_cannot_complete(self, tmp_path):
        authority, clock = make_authority(tmp_path, [{"id": "A"}])
        claim = authority.claim("A", "owner-1")
        clock["t"] += TTL + 1
        with pytest.raises(StaleAttemptError, match="lease expired"):
            authority.complete("A", "owner-1", claim.epoch, "passed")

    def test_expired_attempt_cannot_integrate_after_passing(self, tmp_path):
        authority, clock = make_authority(tmp_path, [{"id": "A"}])
        claim = authority.claim("A", "owner-1")
        authority.complete("A", "owner-1", claim.epoch, "passed")
        clock["t"] += TTL + 1
        with pytest.raises(StaleAttemptError, match="lease expired"):
            authority.integrate(
                "A", "owner-1", claim.epoch, commit="abc1234", review_commit="abc1234"
            )

    def test_revoked_attempt_cannot_publish_after_reclaim(self, tmp_path):
        authority, clock = make_authority(tmp_path, [{"id": "A"}])
        first = authority.claim("A", "owner-1")
        authority.complete("A", "owner-1", first.epoch, "passed")
        clock["t"] += TTL + 1
        authority.claim("A", "owner-2")  # revokes epoch 1
        with pytest.raises(StaleAttemptError, match="superseded"):
            authority.integrate(
                "A", "owner-1", first.epoch, commit="abc1234", review_commit="abc1234"
            )
        with pytest.raises(StaleAttemptError, match="superseded"):
            authority.complete("A", "owner-1", first.epoch, "passed")


class TestBudgetsAndBlocking:
    def test_budget_exhaustion_checkpoints_blocked_no_loop(self, tmp_path):
        authority, _ = make_authority(tmp_path, [{"id": "T", "budget_attempts": 3}])
        claim = authority.claim("T", "owner")
        authority.complete("T", "owner", claim.epoch, "failed", note="flake")
        claim = authority.claim("T", "owner")
        authority.complete("T", "owner", claim.epoch, "passed")
        authority.integration_failed("T", "owner", claim.epoch, note="conflict")
        claim = authority.claim("T", "owner")
        authority.complete("T", "owner", claim.epoch, "failed", note="flake again")
        with pytest.raises(ClaimDenied, match="blocked: budget exhausted: 3/3"):
            authority.claim("T", "owner")
        with pytest.raises(ClaimDenied, match="blocked: budget exhausted"):
            authority.claim("T", "owner")  # idempotent denial, no retry loop
        blocked = authority.blocked_record("T")
        assert isinstance(blocked, BlockedRecord)
        assert blocked.attempts == 3 and blocked.reason.startswith("budget exhausted")

    def test_reclaim_loop_also_terminates_in_blocked(self, tmp_path):
        authority, clock = make_authority(tmp_path, [{"id": "C", "budget_attempts": 2}])
        for _ in range(2):  # crash pattern: claim, let lease lapse, reclaim
            authority.claim("C", "owner")
            clock["t"] += TTL + 1
        with pytest.raises(ClaimDenied, match="blocked: budget exhausted: 2/2"):
            authority.claim("C", "owner")

    def test_claim_path_budget_block_is_durable(self, tmp_path):
        """ALG-3322 F1: the denial must leave a persisted BLOCKED checkpoint."""
        authority, clock = make_authority(tmp_path, [{"id": "C", "budget_attempts": 2}])
        for _ in range(2):
            authority.claim("C", "owner")
            clock["t"] += TTL + 1
        with pytest.raises(ClaimDenied, match="blocked: budget exhausted"):
            authority.claim("C", "owner")
        raw = json.loads((tmp_path / "state.json").read_text())
        assert raw["tasks"]["C"]["status"] == BLOCKED
        assert raw["tasks"]["C"]["blocked"]["reason"].startswith("budget exhausted")
        assert authority.blocked_record("C") is not None
        assert authority.status("C")["status"] == BLOCKED

    def test_blocked_checkpoint_releases_resources(self, tmp_path):
        """ALG-3322 F2: a budget-blocked task cannot strand its resource."""
        authority, clock = make_authority(
            tmp_path,
            [{"id": "X", "budget_attempts": 1, "resources": ["task-authority"]},
             {"id": "Y", "resources": ["task-authority"]}],
        )
        authority.claim("X", "owner-1")
        clock["t"] += TTL + 1
        with pytest.raises(ClaimDenied, match="blocked: budget exhausted: 1/1"):
            authority.claim("X", "owner-1")
        claim = authority.claim("Y", "owner-2")  # resource was released
        assert claim.epoch == 1

    def test_dead_holder_does_not_strand_a_resource(self, tmp_path):
        """ALG-3322 F2: an expired-lease holder is provably stale, so its
        resource lock is dropped when another task needs the resource."""
        authority, clock = make_authority(
            tmp_path,
            [{"id": "X", "budget_attempts": 5, "resources": ["task-authority"]},
             {"id": "Y", "resources": ["task-authority"]}],
        )
        authority.claim("X", "owner-1")
        clock["t"] += TTL + 1
        claim = authority.claim("Y", "owner-2")  # X's lease lapsed: lock released
        assert claim.epoch == 1
        # a live holder is still exclusive
        with pytest.raises(ClaimDenied, match="resource task-authority held by Y"):
            authority.claim("X", "owner-3")

    def test_same_failure_repair_cap_blocks(self, tmp_path):
        authority, _ = make_authority(tmp_path, [{"id": "S", "budget_attempts": 10}])
        for _ in range(3):
            claim = authority.claim("S", "owner")
            authority.complete("S", "owner", claim.epoch, "failed", note="same bug")
        with pytest.raises(ClaimDenied, match="same-failure repair cap"):
            authority.claim("S", "owner")

    def test_different_failure_kinds_reset_the_streak(self, tmp_path):
        authority, _ = make_authority(tmp_path, [{"id": "S", "budget_attempts": 10}])
        claim = authority.claim("S", "owner")
        authority.complete("S", "owner", claim.epoch, "failed", note="tests")
        claim = authority.claim("S", "owner")
        authority.complete("S", "owner", claim.epoch, "passed")
        authority.integration_failed("S", "owner", claim.epoch, note="merge conflict")
        assert authority.status("S")["status"] == BACKLOG  # streak reset, still eligible

    def test_blocked_state_is_durable_and_inspectable(self, tmp_path):
        authority, _ = make_authority(tmp_path, [{"id": "T", "budget_attempts": 1}])
        claim = authority.claim("T", "owner")
        authority.complete("T", "owner", claim.epoch, "failed")
        raw = json.loads((tmp_path / "state.json").read_text())
        assert raw["tasks"]["T"]["status"] == BLOCKED
        assert raw["tasks"]["T"]["blocked"]["reason"].startswith("budget exhausted")
        assert authority.status("T")["status"] == BLOCKED


class TestCancelAndResources:
    def test_cancel_releases_the_task(self, tmp_path):
        authority, _ = make_authority(tmp_path, [{"id": "A"}])
        claim = authority.claim("A", "owner-1")
        authority.cancel("A", reason="descoped")
        with pytest.raises(ClaimDenied, match="task is CANCELLED"):
            authority.claim("A", "owner-2")
        with pytest.raises(StaleAttemptError):
            authority.complete("A", "owner-1", claim.epoch, "passed")

    def test_done_task_cannot_be_cancelled(self, tmp_path):
        authority, _ = make_authority(tmp_path, [{"id": "A"}])
        run_to_done(authority, "A", "owner-1")
        with pytest.raises(InvalidTransition, match="already DONE"):
            authority.cancel("A")

    def test_exclusive_resource_serializes_active_claims(self, tmp_path):
        authority, _ = make_authority(
            tmp_path,
            [{"id": "X", "resources": ["task-authority"]},
             {"id": "Y", "resources": ["task-authority"]}],
        )
        authority.claim("X", "owner-1")
        with pytest.raises(ClaimDenied, match="resource task-authority held by X"):
            authority.claim("Y", "owner-2")

    def test_resource_released_on_terminal_states(self, tmp_path):
        authority, _ = make_authority(
            tmp_path,
            [{"id": "X", "resources": ["task-authority"]},
             {"id": "Y", "resources": ["task-authority"]}],
        )
        run_to_done(authority, "X", "owner-1")
        claim = authority.claim("Y", "owner-2")
        assert claim.epoch == 1
        authority.complete("Y", "owner-2", claim.epoch, "passed")
        authority.integration_failed("Y", "owner-2", claim.epoch, note="rejected")
        claim2 = authority.claim("Y", "owner-3")  # resource free again after Y failure
        assert claim2.epoch == 2

    def test_state_from_a_different_graph_is_rejected(self, tmp_path):
        authority, _ = make_authority(tmp_path, [{"id": "A"}])
        other = TaskGraph.from_mapping({"tasks": [{"id": "A"}, {"id": "B"}]})
        with pytest.raises(ValueError, match="different task graph"):
            TaskAuthority(tmp_path / "state.json", other)
