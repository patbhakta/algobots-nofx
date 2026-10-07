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

.PHONY: demo-g1

# G1 five-capability walkthrough (ALG-3257, A12-1): boots the app with one
# paper worker per demo account (needs the `workers` extra — run it as
# `uv run --extra workers make demo-g1`), drives multi-account / multi-strategy
# / isolation / risk denial / kill+freeze over HTTP, then replays the A06
# engine fixture for kill->restart->reconcile with measurements. Screenshots
# need node + playwright-core (A10_NODE_PATH) + a Playwright Chromium.
# Evidence lands in artifacts/A12/; the gate call is docs/gates/G1/decision.md.
demo-g1:
	$(PYTHON) tests/packets/A12/demo.py

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

A07_RESULTS := artifacts/A07/test-results

.PHONY: verify-A07 demo-A07

# Intent-ledger unit/acceptance suites + packet checks, then acceptance.json
# (AC1-AC5 as PASS / FAIL / PENDING with evidence paths). No optional extras:
# the broker fault emulator is a plain test double, so a case can never be
# PASS without its tests actually running here.
verify-A07:
	mkdir -p $(A07_RESULTS)
	PYTHONPATH=$(CURDIR)/src $(PYTHON) -m pytest tests/execution/ledger tests/packets/A07 -q -p no:cacheprovider -rs \
		--junitxml=$(A07_RESULTS)/junit.xml
	sed -i -E 's/ (timestamp|hostname|time)="[^"]*"//g' $(A07_RESULTS)/junit.xml
	PYTHONPATH=$(CURDIR)/src $(PYTHON) tests/packets/A07/acceptance.py $(A07_RESULTS)/junit.xml

# Demo evidence: duplicate-request replay + accepted-but-timeout trace into
# artifacts/A07/demo-run.json (the packet's required demo).
demo-A07:
	PYTHONPATH=$(CURDIR)/src $(PYTHON) tests/packets/A07/demo.py
