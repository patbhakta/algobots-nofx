# Packet verification/demo targets (resource: make-targets, integration owner A01).
# Packets propose their verify-Axx/demo-Axx targets; the owner integrates them.

PYTHON ?= python
A01_RESULTS := artifacts/A01/test-results

.PHONY: verify-A01 demo-A01

verify-A01:
	mkdir -p $(A01_RESULTS)
	$(PYTHON) -m algobots.contracts
	$(PYTHON) -m pytest tests/contracts tests/packets/A01 -q -p no:cacheprovider \
		--junitxml=$(A01_RESULTS)/junit.xml

demo-A01:
	$(PYTHON) tests/packets/A01/demo.py
