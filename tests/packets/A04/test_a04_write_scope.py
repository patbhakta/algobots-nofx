"""The A04 branch only touches paths A04 may write (ALG-3100).

Compares `git diff --name-only <merge-base with origin/main>..HEAD` with
`packets.A04.write_scope` in `docs/repository-map.json`, plus the shared
resources A04 may touch. `db-migrations` is owned by the A03 integration
owner — the same agent executing A04 — so the migrations tree is allowed but
pre-existing migrations 0001-0009 are frozen. `Makefile` is allowed only as
the proposal to the make-targets owner. Skips when git or `origin/main` isn't
available, and passes trivially once the branch is merged (empty diff).

A04's frozen write scope describes what the *A04 branch* may touch, so the
guard only runs on an A04 branch. On any other branch — a ROADMAP-v3 sprint
branch, say — every path it adds is "outside A04", which says nothing about
A04 discipline (ALG-3373).
"""

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PACKET = "A04"
PROPOSED_TO_OWNER = {
    "Makefile",
    "docs/repository-map.json",
    # A03-owned surfaces A04 mounted into (router mount, ORM registration,
    # control-plane expectations); identical write-scope entries in two
    # packets are forbidden, so these stay proposals through the A03 owner.
    "src/algobots/api/main.py",
    "src/algobots/api/models.py",
    "tests/api/test_control_plane.py",
}
FROZEN_MIGRATIONS = tuple(
    f"src/algobots/api/migrations/versions/{n:04d}_"
    for n in range(1, 10)  # 0001-0009 predate A04; only 0010+ may be added
)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def _changed_files() -> list[str]:
    try:
        base = _git("merge-base", "origin/main", "HEAD")
        return [p for p in _git("diff", "--name-only", f"{base}..HEAD").splitlines() if p]
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git or origin/main unavailable")


def _branch_under_test() -> str:
    """The branch the diff belongs to: the PR source in CI, else the checkout."""
    for var in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME"):
        ref = os.environ.get(var, "").strip()
        if ref:
            return ref
    try:
        return _git("rev-parse", "--abbrev-ref", "HEAD")
    except (OSError, subprocess.CalledProcessError):
        return ""


def _is_packet_branch(branch: str) -> bool:
    """`feat/alg-3100-a04-accounts-secrets` is A04's; `alg-3373-p15-e2e-gate` is not."""
    return PACKET.lower() in re.split(r"[^a-z0-9]+", branch.lower())


def _allowed_prefixes() -> list[str]:
    repo_map = json.loads((ROOT / "docs" / "repository-map.json").read_text())
    packet = repo_map["packets"]["A04"]
    prefixes = [entry["path"] for entry in packet["write_scope"] if entry["repo"] == "algobots"]
    for name in packet["shared_resources"]:
        resource = repo_map["shared_resources"][name]
        assert resource["integration_owner"] in ("A03", "A04"), name
        prefixes += [p["path"] for p in resource["paths"] if p["repo"] == "algobots"]
    return prefixes


def _is_allowed(path: str, prefixes: list[str]) -> bool:
    if path in PROPOSED_TO_OWNER:
        return True
    if path.startswith(FROZEN_MIGRATIONS):
        return False
    return any(path == p or path.startswith(p.rstrip("/") + "/") for p in prefixes)


def test_branch_changes_stay_inside_a04_write_scope():
    branch = _branch_under_test()
    if not _is_packet_branch(branch):
        pytest.skip(f"{branch!r} is not an {PACKET} branch; its write scope does not apply")
    prefixes = _allowed_prefixes()
    changed = _changed_files()
    if not changed:
        pytest.skip("branch already merged (empty diff)")
    violations = sorted(p for p in changed if not _is_allowed(p, prefixes))
    assert not violations, f"out-of-scope paths touched: {violations}"


def test_packet_branch_detection():
    assert _is_packet_branch("feat/alg-3100-a04-accounts-secrets")
    assert _is_packet_branch("backup-A04-int")
    assert not _is_packet_branch("alg-3373-p15-e2e-gate")
    assert not _is_packet_branch("feat/alg-3099-a03-tenant-auth")
    assert not _is_packet_branch("main")
    assert not _is_packet_branch("")


def test_scope_check_rejects_foreign_and_frozen_paths():
    prefixes = _allowed_prefixes()
    assert _is_allowed("src/algobots/secrets/service.py", prefixes)
    assert _is_allowed("src/algobots/api/accounts/onboarding.py", prefixes)
    assert _is_allowed("src/algobots/api/migrations/versions/0010_a04.py", prefixes)
    assert not _is_allowed("src/algobots/engine/anything.py", prefixes)
    assert not _is_allowed("src/algobots/api/migrations/versions/0008_x.py", prefixes)
