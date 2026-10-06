# A09 proposed make targets (resource: make-targets, integration owner A01).
# The owner copies everything below the marker into the Makefile verbatim;
# tests/packets/A09/test_a09_scope.py checks that the two stay identical.
# --- begin targets ---
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
