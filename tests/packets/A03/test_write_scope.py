"""The A03 branch only touches paths A03 may write (ALG-3184 finding 1).

Compares `git diff --name-only <merge-base with origin/main>..HEAD` with
`packets.A03.write_scope` in `docs/repository-map.json`, plus the shared
resources A03 owns. Existing migrations (0001-0004) stay untouched even though
A03 owns `db-migrations`, and `Makefile` is allowed only as the proposal to the
make-targets owner. Skips when git or `origin/main` isn't available, and
passes trivially once the branch is merged (empty diff).
"""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PROPOSED_TO_OWNER = {"Makefile"}
FROZEN_MIGRATIONS = (
    "src/algobots/api/migrations/versions/0001_",
    "src/algobots/api/migrations/versions/0002_",
    "src/algobots/api/migrations/versions/0003_",
    "src/algobots/api/migrations/versions/0004_",
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


def _allowed_prefixes() -> list[str]:
    repo_map = json.loads((ROOT / "docs" / "repository-map.json").read_text())
    packet = repo_map["packets"]["A03"]
    prefixes = [entry["path"] for entry in packet["write_scope"] if entry["repo"] == "algobots"]
    for name in packet["shared_resources"]:
        resource = repo_map["shared_resources"][name]
        assert resource["integration_owner"] == "A03", name
        prefixes += [p["path"] for p in resource["paths"] if p["repo"] == "algobots"]
    return prefixes


def _allowed(path: str, prefixes: list[str]) -> bool:
    if path in PROPOSED_TO_OWNER:
        return True
    if path.startswith(FROZEN_MIGRATIONS):
        return False
    return any(path == p or (p.endswith("/") and path.startswith(p)) for p in prefixes)


def test_branch_changes_stay_inside_a03_write_scope():
    prefixes = _allowed_prefixes()
    outside = [p for p in _changed_files() if not _allowed(p, prefixes)]
    assert outside == [], f"files outside A03 write scope: {outside}"


def test_scope_check_rejects_foreign_and_frozen_paths():
    prefixes = _allowed_prefixes()
    assert _allowed("src/algobots/api/memberships/service.py", prefixes)
    assert _allowed("src/algobots/api/migrations/versions/0008_tenant_memberships.py", prefixes)
    assert not _allowed("src/algobots/api/accounts/service.py", prefixes)
    assert not _allowed("src/algobots/api/approvals/router.py", prefixes)
    assert not _allowed(
        "src/algobots/api/migrations/versions/0004_approvals_action_ledger.py", prefixes
    )
