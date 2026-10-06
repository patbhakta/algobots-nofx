"""``python -m algobots.contracts [--write-lock] [--check-transition [REF]]``.

Checks (or regenerates) the schema lock. ``--check-transition`` also compares
the live registry with the lock committed at ``REF`` (default: the merge base
with ``origin/main``) and fails on any in-place fingerprint rewrite or a
removed version that a queued packet pins.
"""

import sys

from algobots.contracts import registry

args = sys.argv[1:]
if "--write-lock" in args:
    registry.write_lock()
problems = registry.verify_lock(registry.load_lock())
print("\n".join(problems) or f"schema lock in sync ({len(registry.registered())} contracts)")
if problems:
    sys.exit(1)

if "--check-transition" in args:
    rest = args[args.index("--check-transition") + 1 :]
    ref = rest[0] if rest and not rest[0].startswith("--") else registry.transition_base()
    try:
        old = registry.load_lock_at(ref)
    except registry.SchemaRevisionError as exc:
        print(exc)
        sys.exit(1)
    if old is None:
        print(f"no schema lock at {ref[:12]}: first introduction, nothing to extend")
    else:
        try:
            registry.check_lock_transition(old, registry.current_lock(), registry.load_pins())
        except registry.SchemaRevisionError as exc:
            print(f"schema lock transition from {ref[:12]} rejected: {exc}")
            sys.exit(1)
        print(f"schema lock transition from {ref[:12]} ok")
