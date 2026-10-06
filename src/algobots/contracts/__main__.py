"""``python -m algobots.contracts [--write-lock]`` — check (or regenerate) the schema lock."""

import sys

from algobots.contracts import registry

if sys.argv[1:] == ["--write-lock"]:
    registry.write_lock()
problems = registry.verify_lock(registry.load_lock())
print("\n".join(problems) or f"schema lock in sync ({len(registry.registered())} contracts)")
sys.exit(1 if problems else 0)
