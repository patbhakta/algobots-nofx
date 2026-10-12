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

A12_RESULTS := artifacts/A12/test-results

.PHONY: verify-A12

# A12-2 packet closure (ALG-3303): the always-on packet tests (no `workers`
# extra, no node/playwright — screenshots stay with `make demo-g1`), then
# acceptance.json. AC1/AC2 re-check the recorded five-capability evidence;
# AC3-AC5 are DESCOPED to A14/A17/A18 per Pat's Oct 6 functional-terminal
# ruling, so this stays CI-runnable (same install as the plain `pytest` CI).
verify-A12:
	mkdir -p $(A12_RESULTS)
	PYTHONPATH=$(CURDIR)/src $(PYTHON) -m pytest tests/packets/A12 -q -p no:cacheprovider -rs \
		--junitxml=$(A12_RESULTS)/junit.xml
	sed -i -E 's/ (timestamp|hostname|time)="[^"]*"//g' $(A12_RESULTS)/junit.xml
	PYTHONPATH=$(CURDIR)/src $(PYTHON) tests/packets/A12/acceptance.py $(A12_RESULTS)/junit.xml

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

A08_RESULTS := artifacts/A08/test-results

.PHONY: verify-A08 demo-A08

# Account risk + reservation suites + packet checks, then acceptance.json
# (AC1-AC5 as PASS / FAIL / PENDING with evidence paths). No optional extras:
# the concurrency races run on the real Alembic-migrated SQLite store.
verify-A08:
	mkdir -p $(A08_RESULTS)
	PYTHONPATH=$(CURDIR)/src $(PYTHON) -m pytest tests/risk tests/packets/A08 -q -p no:cacheprovider -rs \
		--junitxml=$(A08_RESULTS)/junit.xml
	sed -i -E 's/ (timestamp|hostname|time)="[^"]*"//g' $(A08_RESULTS)/junit.xml
	PYTHONPATH=$(CURDIR)/src $(PYTHON) tests/packets/A08/acceptance.py $(A08_RESULTS)/junit.xml

# Demo evidence: race two strategies for shared funds + entry pause without
# removing stops, into artifacts/A08/demo-run.json (the packet's required demo).
demo-A08:
	PYTHONPATH=$(CURDIR)/src $(PYTHON) tests/packets/A08/demo.py

A11_RESULTS := artifacts/A11/test-results

.PHONY: verify-A11

# A11 evidence packet (ALG-3283): the four A11 lanes — studio
# (tests/demo/test_studio.py), runner (tests/engine/workers/test_template.py),
# campaign (tests/demo/test_campaigns.py), breaker
# (tests/strategies/test_deployments_api.py +
# tests/api/test_fleet_breaker_tenancy.py since the A03 merge, ALG-3310) —
# then acceptance.json (AC1-AC6 as PASS / FAIL / BLOCKED with reasons).
verify-A11:
	mkdir -p $(A11_RESULTS)
	PYTHONPATH=$(CURDIR)/src $(PYTHON) -m pytest tests/demo/test_studio.py tests/demo/test_campaigns.py \
		tests/engine/workers/test_template.py tests/strategies/test_deployments_api.py \
		tests/api/test_fleet_breaker_tenancy.py \
		-q -p no:cacheprovider -rs \
		--junitxml=$(A11_RESULTS)/junit.xml
	sed -i -E 's/ (timestamp|hostname|time)="[^"]*"//g' $(A11_RESULTS)/junit.xml
	PYTHONPATH=$(CURDIR)/src $(PYTHON) tests/packets/A11/acceptance.py $(A11_RESULTS)/junit.xml

A02_RESULTS := artifacts/A02/test-results

.PHONY: verify-A02 demo-A02

# A02 atomic task queue (ALG-3098; make-targets proposal via A02). Unit
# suite (tests/agent_queue) + packet acceptance AC1-AC4 (real cross-process
# claim races), then acceptance.json (cases as PASS / FAIL / PENDING with
# evidence paths). Needs the project environment (repo .venv / editable
# install): tests/conftest.py imports app deps; PYTHONPATH additionally
# pins this checkout's root for tools.agent_queue (ALG-3322 F5).
verify-A02:
	mkdir -p $(A02_RESULTS)
	PYTHONPATH=$(CURDIR) $(PYTHON) -m pytest tests/agent_queue tests/packets/A02 -q -p no:cacheprovider -rs \
		--junitxml=$(A02_RESULTS)/junit.xml
	sed -i -E 's/ (timestamp|hostname|time)="[^"]*"//g' $(A02_RESULTS)/junit.xml
	PYTHONPATH=$(CURDIR) $(PYTHON) tests/packets/A02/acceptance.py $(A02_RESULTS)/junit.xml

# Demo evidence: 38-packet queue walkthrough + budget-exhaustion failure
# path, into artifacts/A02/demo-run.json + compatibility-report.json.
demo-A02:
	PYTHONPATH=$(CURDIR) $(PYTHON) tests/packets/A02/demo.py

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

A14_RESULTS := artifacts/A14/test-results

.PHONY: verify-A14 demo-A14

# A14 production Obsidian ingestion (ALG-3320; make-targets proposal via
# A14-3). Full ingest lane: unit suite (tests/knowledge/ingest) + packet
# acceptance AC1-AC5 (end-to-end cases + scope guard), then acceptance.json
# (cases as PASS / FAIL / BLOCKED with evidence paths). Fully offline:
# synthetic fixtures only, deterministic local embedder, zero API spend.
verify-A14:
	mkdir -p $(A14_RESULTS)
	PYTHONPATH=$(CURDIR)/src $(PYTHON) -m pytest tests/knowledge/ingest tests/packets/A14 -q -p no:cacheprovider -rs \
		--junitxml=$(A14_RESULTS)/junit.xml
	sed -i -E 's/ (timestamp|hostname|time)="[^"]*"//g' $(A14_RESULTS)/junit.xml
	PYTHONPATH=$(CURDIR)/src $(PYTHON) tests/packets/A14/acceptance.py $(A14_RESULTS)/junit.xml

# Demo evidence: one synthetic vault through import -> edit -> rename ->
# delete with lineage and processing cost, into artifacts/A14/demo-output.txt.
demo-A14:
	PYTHONPATH=$(CURDIR)/src $(PYTHON) tests/packets/A14/demo.py

# A04 (proposed by ALG-3100 for the make-targets owner). The contracts
# transition check guards the two new registrations (BrokerAdapterCapabilities,
# SecretResolver) against the lock at the merge base with origin/main.
# PostgreSQL RLS cases in tests/packets/A04/test_pg_rls.py run only when
# ALGOBOTS_A04_PG_ADMIN_URL names a role that can create databases and roles;
# otherwise they skip as BLOCKED (-rs prints the reason). tests/api re-runs
# the account-registry suite the auth contract must keep green.
A04_RESULTS := artifacts/A04/test-results

.PHONY: verify-A04 demo-A04

verify-A04:
	mkdir -p $(A04_RESULTS)
	PYTHONPATH=$(CURDIR)/src $(PYTHON) -m algobots.contracts --check-transition $(SCHEMA_BASE)
	PYTHONPATH=$(CURDIR)/src $(PYTHON) -m pytest tests/api/test_accounts.py tests/packets/A04 \
		-q -rs -p no:cacheprovider --junitxml=$(A04_RESULTS)/junit.xml
	sed -i -E 's/ (timestamp|hostname|time)="[^"]*"//g' $(A04_RESULTS)/junit.xml

demo-A04:
	PYTHONPATH=$(CURDIR)/src $(PYTHON) tests/packets/A04/demo.py

# A05 (proposed by ALG-3101 for the make-targets owner). The contracts
# transition check guards the three new registrations (Instrument,
# MarketSnapshot, FeatureSnapshot) against the lock at the merge base with
# origin/main; the market-data lane proves acceptance cases 1-4 on recorded
# fixtures; acceptance.py then writes artifacts/A05/acceptance.json.
# External-environment cases stay BLOCKED, never claimed.
A05_RESULTS := artifacts/A05/test-results

.PHONY: verify-A05 demo-A05

verify-A05:
	mkdir -p $(A05_RESULTS)
	PYTHONPATH=$(CURDIR)/src $(PYTHON) -m algobots.contracts --check-transition $(SCHEMA_BASE)
	PYTHONPATH=$(CURDIR)/src $(PYTHON) -m pytest tests/marketdata tests/packets/A05 tests/contracts \
		-q -rs -p no:cacheprovider --junitxml=$(A05_RESULTS)/junit.xml
	sed -i -E 's/ (timestamp|hostname|time)="[^"]*"//g' $(A05_RESULTS)/junit.xml
	PYTHONPATH=$(CURDIR)/src $(PYTHON) tests/packets/A05/acceptance.py $(A05_RESULTS)/junit.xml

demo-A05:
	PYTHONPATH=$(CURDIR)/src $(PYTHON) tests/packets/A05/demo.py
