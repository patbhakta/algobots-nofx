# Packet verification/demo targets (resource: make-targets, integration owner A01).
# Packets propose their verify-Axx/demo-Axx targets; the owner integrates them.

PYTHON ?= python
A01_RESULTS := artifacts/A01/test-results
A03_RESULTS := artifacts/A03/test-results

.PHONY: verify-A01 demo-A01 verify-A03 demo-A03

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

# A03 (proposed by ALG-3099 for the make-targets owner). PostgreSQL cases in
# tests/packets/A03/test_pg_rls.py run only when ALGOBOTS_A03_PG_ADMIN_URL
# names a role that can create databases and roles; otherwise they skip as
# BLOCKED (-rs prints the reason). tests/api re-runs the S0.2 control-plane
# suite the auth contract must keep green.
verify-A03:
	mkdir -p $(A03_RESULTS)
	$(PYTHON) -m pytest tests/packets/A03 tests/api -q -rs -p no:cacheprovider \
		--junitxml=$(A03_RESULTS)/junit.xml
	sed -i -E 's/ (timestamp|hostname|time)="[^"]*"//g' $(A03_RESULTS)/junit.xml

demo-A03:
	$(PYTHON) tests/packets/A03/demo.py
