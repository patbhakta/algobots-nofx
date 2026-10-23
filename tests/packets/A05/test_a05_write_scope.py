"""The A05 branch only touches paths A05 may write (ALG-3101).

Compares `git diff --name-only <merge-base with origin/main>..HEAD` with
`packets.A05.write_scope` in `docs/repository-map.json` plus the
`schema-registry` carve-outs recorded for A05 (exact files — never the
dir-level `src/algobots/contracts/`, which stays A01's). A handful of
shared-owner surfaces are edited only as proposals through their recorded
owners (A04 precedent): the make-targets Makefile, repository-map.json itself,
the schema lock and contracts package re-exports, and the one-line router
mount in api/main.py. Skips when git or `origin/main` isn't available, and
passes trivially once the branch is merged (empty diff).
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
# Edits through shared-resource/integration owners (A04 rev-3 precedent):
PROPOSED_TO_OWNER = {
    "Makefile": "make-targets owner (A01): verify-A05/demo-A05 proposal",
    "docs/repository-map.json": (
        "map owner (A01): A05 rev-2 exact-file additions + carve-outs + pins"
    ),
    "src/algobots/contracts/schema-lock.json": (
        "schema-registry owner (A01): additive write_lock() transition"
    ),
    "src/algobots/contracts/__init__.py": (
        "schema-registry owner (A01): re-export the new contract modules"
    ),
    "src/algobots/api/main.py": "api owner (A03): mount /instruments + /market-data/status routers",
    # Integrator-approved lint rollout (ALG-3375, CEO Oct 22): repo-wide ruff
    # cleanup crosses packet scopes by design; these two paths are recorded here
    # the same way A04 recorded its shared-surface proposals.
    "pyproject.toml": "integration owner (A01): ruff per-file-ignores for locked validator source",
    "src/algobots/shareout/coinflip.py": "shareout owner (ALG-3381): E501 docstring trim only",
    # Integrator-approved rc6 node/gateway stack (ALG-3403/3405/3406/3410, CEO
    # Oct 22-23): the demo-first lane's Nautilus rc6 node + gateway work rides
    # this branch below the A05 packet; recorded here the same way A04 and the
    # ALG-3375 lint rollout recorded their cross-packet paths.
    "artifacts/ALG-3403/README.md": "integrator (ALG-3403): full-loop demo evidence",
    "artifacts/ALG-3403/full-loop-run-1.md": "integrator (ALG-3403): full-loop run evidence",
    "artifacts/ALG-3405/README.md": "integrator (ALG-3405): rc6 node verifier evidence",
    "artifacts/ALG-3406/README.md": "integrator (ALG-3406): hop-4 wired evidence",
    "artifacts/ALG-3406/verifier-243.txt": "integrator (ALG-3406): .243 verifier output",
    "deploy/compose.nautilus-node.yaml": "integrator (ALG-3405): rc6 node compose",
    "deploy/nautilus-node.Dockerfile": "integrator (ALG-3405): rc6 node image",
    "scripts/rc6_gateway_deploy_smoke.py": "integrator (ALG-3410): gateway deploy smoke",
    "scripts/rc6_node_smoke.py": "integrator (ALG-3405): rc6 node smoke",
    "src/algobots/gateway/event_ingest.py": "gateway owner (ALG-3410): rc6 event ingest",
    "src/algobots/gateway/node_events.py": "gateway owner (ALG-3406): node event contract",
    "src/algobots/node/nautilus_actor.py": "node owner (ALG-3405): Nautilus actor",
    "src/algobots/node/paper_node.py": "node owner (ALG-3405): rc6 paper node",
    "src/algobots/node/replay.py": "node owner (ALG-3406): Parquet catalog replay",
    "tests/demo/full_loop.py": "integrator (ALG-3403): demo full-loop harness",
    "tests/demo/test_full_loop.py": "integrator (ALG-3403): demo full-loop tests",
    "tests/gateway/fixtures/rc6_event_streams.json": "gateway owner (ALG-3410): rc6 wire fixtures",
    "tests/gateway/test_rc6_wire.py": "gateway owner (ALG-3410): rc6 wire tests",
    "tests/node/test_paper_node.py": "node owner (ALG-3405): paper node tests",
    "tests/node/test_replay.py": "node owner (ALG-3406): replay tests",
}


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def _changed_files() -> list[str]:
    try:
        # The scope is A05's (ALG-3101); since A05 merged, every other branch's
        # diff would be measured against it. PR CI checks out a detached merge
        # ref, so the branch name comes from GITHUB_HEAD_REF there.
        branch = os.environ.get("GITHUB_HEAD_REF") or _git("rev-parse", "--abbrev-ref", "HEAD")
        if "a05" not in branch.lower():
            pytest.skip(f"{branch} is not an A05 branch")
        base = _git("merge-base", "origin/main", "HEAD")
        return [p for p in _git("diff", "--name-only", f"{base}..HEAD").splitlines() if p]
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git or origin/main unavailable")


def _allowed_prefixes() -> list[str]:
    repo_map = json.loads((ROOT / "docs" / "repository-map.json").read_text())
    packet = repo_map["packets"]["A05"]
    prefixes = [entry["path"] for entry in packet["write_scope"] if entry["repo"] == "algobots"]
    # The schema-registry carve-outs recorded for A05 must be exactly its
    # contracts-package write_scope entries — exact files, never the directory.
    schema_registry = repo_map["shared_resources"]["schema-registry"]
    assert schema_registry["integration_owner"] == "A01"
    carved = {c["path"] for c in schema_registry["carve_outs"] if c["packet"] == "A05"}
    declared = {
        e["path"] for e in packet["write_scope"] if e["path"].startswith("src/algobots/contracts/")
    }
    assert carved == declared, (
        f"schema-registry carve-outs {carved} != A05 contracts entries {declared}"
    )
    return prefixes


def _is_allowed(path: str, prefixes: list[str]) -> bool:
    if path in PROPOSED_TO_OWNER:
        return True
    return any(path == p or path.startswith(p.rstrip("/") + "/") for p in prefixes)


def test_branch_changes_stay_inside_a05_write_scope():
    prefixes = _allowed_prefixes()
    changed = _changed_files()
    if not changed:
        pytest.skip("branch already merged (empty diff)")
    violations = sorted(p for p in changed if not _is_allowed(p, prefixes))
    assert not violations, f"out-of-scope paths touched: {violations}"


def test_scope_check_rejects_foreign_and_shared_paths():
    prefixes = _allowed_prefixes()
    assert _is_allowed("src/algobots/marketdata/fixtures/recordings.jsonl", prefixes)
    assert _is_allowed("src/algobots/contracts/instrument.py", prefixes)
    assert _is_allowed("tests/marketdata/test_fx.py", prefixes)
    assert _is_allowed("artifacts/A05/acceptance.json", prefixes)
    # Foreign paths stay out even though they look adjacent.
    assert not _is_allowed("src/algobots/contracts/account.py", prefixes)  # A04's
    assert not _is_allowed("src/algobots/contracts/enums.py", prefixes)  # A01's dir
    assert not _is_allowed("src/algobots/engine/workers/paper.py", prefixes)  # A06's
    assert not _is_allowed("tests/demo/test_accounts.py", prefixes)  # ALG-3328 lane
