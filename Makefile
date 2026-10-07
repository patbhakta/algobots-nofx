# Packet verification/demo targets (resource: make-targets, integration owner A01).
# Packets propose their verify-Axx/demo-Axx targets; the owner integrates them.

PYTHON ?= python
A01_RESULTS := artifacts/A01/test-results

.PHONY: verify-A01 demo-A01

# --check-transition compares the live registry with the schema lock at the
# merge base with origin/main (override: SCHEMA_BASE=<ref>). The junit report is
# stripped of run-specific attributes so an unchanged result leaves the tree clean.
verify-A01:
	mkdir -p $(A01_RESULTS)
	$(PYTHON) -m algobots.contracts --check-transition $(SCHEMA_BASE)
	$(PYTHON) -m pytest tests/contracts tests/packets/A01 -q -p no:cacheprovider \
		--junitxml=$(A01_RESULTS)/junit.xml
	sed -i -E 's/ (timestamp|hostname|time)="[^"]*"//g' $(A01_RESULTS)/junit.xml

demo-A01:
	$(PYTHON) tests/packets/A01/demo.py

A09_RESULTS := artifacts/A09/test-results

.PHONY: build-A09 verify-A09 demo-A09 screenshots-A09

# Rebuilds tokens, fixtures and the storyboard (deterministic: an unchanged tree
# stays clean), then runs the packet tests. Headless-browser tests skip, and
# say so, when no Chrome/Chromium is available (set A09_CHROME).
build-A09:
	$(PYTHON) -m algobots.dashboard.design build artifacts/A09

verify-A09: build-A09
	mkdir -p $(A09_RESULTS)
	$(PYTHON) -m pytest tests/packets/A09 -q -p no:cacheprovider -rs \
		--junitxml=$(A09_RESULTS)/junit.xml
	sed -i -E 's/ (timestamp|hostname|time)="[^"]*"//g' $(A09_RESULTS)/junit.xml

demo-A09: build-A09
	$(PYTHON) tests/packets/A09/demo.py

screenshots-A09: build-A09
	$(PYTHON) tests/packets/A09/capture.py

A10_RESULTS := artifacts/A10/test-results

.PHONY: verify-A10

# Functional-terminal /demo (ALG-3261). PYTHONPATH pins this checkout's src so a
# worktree sharing another checkout's editable venv tests its own code. The
# browser journey (tests/packets/A10) skips, and says so, without node,
# playwright-core (A10_NODE_PATH) or a Playwright Chromium.
verify-A10:
	mkdir -p $(A10_RESULTS)
	PYTHONPATH=$(CURDIR)/src $(PYTHON) -m pytest tests/demo tests/packets/A10 -q -p no:cacheprovider -rs \
		--junitxml=$(A10_RESULTS)/junit.xml
	sed -i -E 's/ (timestamp|hostname|time)="[^"]*"//g' $(A10_RESULTS)/junit.xml

A06_RESULTS := artifacts/A06/test-results

.PHONY: verify-A06

# Worker supervisor/lease/paper tests + packet checks, then acceptance.json
# (AC1-AC5 as PASS / FAIL / PENDING with evidence paths). test_paper needs the
# `workers` extra (nautilus_trader); without it AC1/AC3 stay PENDING, never PASS.
verify-A06:
	mkdir -p $(A06_RESULTS)
	PYTHONPATH=$(CURDIR)/src $(PYTHON) -m pytest tests/engine/workers tests/packets/A06 -q -p no:cacheprovider -rs \
		--junitxml=$(A06_RESULTS)/junit.xml
	sed -i -E 's/ (timestamp|hostname|time)="[^"]*"//g' $(A06_RESULTS)/junit.xml
	PYTHONPATH=$(CURDIR)/src $(PYTHON) tests/packets/A06/acceptance.py $(A06_RESULTS)/junit.xml
