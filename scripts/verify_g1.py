#!/usr/bin/env python3
"""Run GATE G1 and print the measurement. ``make verify-g1``.

ROADMAP-v3 rule 1: a sprint's "Done when" has to run in CI *or* as a repository
script. G1 does both, and this is the second — the same stack
(``tests/e2e/stack.py``), the same assertions (``pytest``), so the number this
prints on ``.243`` is comparable with the number CI prints on a runner.

It is a thin wrapper on purpose. A script that re-implemented the measurement
could drift from the gate CI enforces, and then "it passes locally" would stop
meaning anything.

    POSTGRES_PASSWORD=... docker compose up -d postgres redis   # Phase 0
    ALGOBOTS_GATEWAY_TEST_PG_URL=postgresql+psycopg://algobots:...@127.0.0.1:5432/algobots \\
    ALGOBOTS_TEST_REDIS_URL=redis://127.0.0.1:6379/0 \\
      python scripts/verify_g1.py

Exits non-zero if the gate fails *or* if it was skipped: a gate that did not
run has not passed, and this script's exit code is the only thing a deployment
check reads.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = REPO_ROOT / "artifacts" / "ALG-3373" / "g1-latency.json"

REQUIRED = ("ALGOBOTS_GATEWAY_TEST_PG_URL", "ALGOBOTS_TEST_REDIS_URL")


def main() -> int:
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        # Named, never echoed: the Postgres URL carries a password (rule 3).
        print(f"GATE G1 needs {', '.join(missing)} — see compose.yaml", file=sys.stderr)
        return 2

    EVIDENCE.unlink(missing_ok=True)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/e2e",
            "-v",
            "--no-header",
            # Report why anything was skipped: pytest exits 0 on a skip, so the
            # reason is the only thing that explains the measurement check
            # below failing.
            "-rs",
            "-W",
            "ignore::DeprecationWarning",
        ],
        cwd=REPO_ROOT,
        check=False,
    )
    if completed.returncode != 0:
        return completed.returncode

    if not EVIDENCE.exists():
        # pytest exits 0 when every test skipped, so this is what turns "no
        # Postgres, no Redis, nothing ran" into a failure. A gate that did not
        # run has not passed.
        print("GATE G1 reported success but wrote no measurement — it did not run", file=sys.stderr)
        return 3

    measurement = json.loads(EVIDENCE.read_text())
    print(
        f"GATE G1 PASS — fill visible in {measurement['measured_s']:.3f}s "
        f"(budget {measurement['budget_s']}s)\n"
        f"  evidence: {EVIDENCE.relative_to(REPO_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
