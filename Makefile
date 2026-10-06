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
