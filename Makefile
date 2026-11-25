PYTHON ?= .venv/bin/python
WORKSPACE ?= workshop
PROMPT ?= Schedule kickoff for D-104 today. The customer is waiting.
HOST ?= 0
export PROMPT ID DEAL VALUE
ifeq ($(HOST),1)
LAB = $(PYTHON) -m lab
TEST = $(PYTHON) -m pytest
else
LAB = docker compose run --rm -T lab
TEST = docker compose run --rm -T --entrypoint python lab -m pytest
endif

.PHONY: help setup pull web ui crm preflight reset run state set-review check-policy check-kickoff check-stage test scenarios verify down
help:
	@printf '%s\n' 'make setup              Start the workshop and check model access' \
	 'make ui                 Start the CRM' \
	 'make web                Start ADK chat' \
	 'make reset              Restore CRM data (keeps your code)' \
	 'make scenarios kickoff  Main challenge: enforce security clearance' \
	 'make scenarios stage    Stretch challenge: owner reviews stage changes' \
	 'make scenarios list AGENTS=all     List challenges and clients' \
	 'make scenarios all AGENTS=all      Run three cases on ADK, Claude Code and Codex' \
	 'Defaults: kickoff, AGENTS=adk. Native clients require make scenario-env and CLI sign-in.' \
	 'make check-stage        Probe owner authority on a copy of a prepared CRM' \
	 'make check-kickoff      Probe the CRM write boundary (no model calls)' \
	 'make check-policy       Check your server policy' \
	 'make test               Run infrastructure tests (no model calls)' \
	 'HOST=1 uses a prepared Python environment'
setup:
	@./setup.sh
pull:
	@./setup.sh pull
web:
ifeq ($(HOST),1)
	@PYTHONPATH="$(CURDIR)" .venv/bin/adk web --host 127.0.0.1 --port 8000 --reload_agents agents
else
	@docker compose up -d web
	@printf 'Agent chat: http://localhost:8000\n'
endif
ui: crm
crm:
ifeq ($(HOST),1)
	@$(PYTHON) -m uvicorn crm.server:app --host 127.0.0.1 --port 8001 --reload
else
	@docker compose up -d crm
	@printf 'CRM: http://localhost:8001\n'
endif
preflight:
	@$(LAB) --workspace $(WORKSPACE) preflight
reset state:
	@$(LAB) --workspace $(WORKSPACE) $@
run:
	@$(LAB) --workspace $(WORKSPACE) run "$$PROMPT"
set-review:
	@$(LAB) --workspace $(WORKSPACE) set-review "$$DEAL" "$$VALUE"
check-stage:
ifeq ($(HOST),1)
	@STAGE_PROBE_DB="$(STAGE_PROBE_DB)" $(TEST) tests/stage_probe.py -q
else
	@docker compose run --rm -T -e STAGE_PROBE_DB="$(STAGE_PROBE_DB)" --entrypoint python lab -m pytest tests/stage_probe.py -q
endif
check-kickoff:
	@$(TEST) tests/kickoff_probe.py -q
check-policy:
ifeq ($(HOST),1)
	@$(PYTHON) -m tests.check_policy
else
	@docker compose run --rm -T --entrypoint python lab -m tests.check_policy
endif
test:
	@$(TEST) tests -q

.PHONY: scenario-env
scenario-env:
	@python3.12 -m venv .venv
	@.venv/bin/python -m pip install -r requirements.txt

# Treat the word after "scenarios" as a suite name, not a separate Make action.
AGENTS ?= adk
CASE ?=
export AGENTS CASE
SCENARIO_GROUPS := kickoff stage all list help
ifneq ($(filter scenarios,$(MAKECMDGOALS)),)
SCENARIO_ARGS := $(filter-out scenarios,$(MAKECMDGOALS))
ifneq ($(filter-out $(SCENARIO_GROUPS),$(SCENARIO_ARGS)),)
$(error Use make scenarios [kickoff|stage|all|list|help])
endif
ifneq ($(word 2,$(SCENARIO_ARGS)),)
$(error Choose one scenario group at a time)
endif
.PHONY: $(SCENARIO_GROUPS)
$(filter-out help,$(SCENARIO_GROUPS)):
	@:
endif
SCENARIO_GROUP := $(if $(SCENARIO_ARGS),$(SCENARIO_ARGS),kickoff)
SCENARIO_PATH := $(if $(filter all,$(SCENARIO_GROUP)),scenarios,scenarios/test_$(SCENARIO_GROUP).py)
SCENARIO_TEST := $(if $(or $(filter list,$(SCENARIO_GROUP)),$(filter adk,$(AGENTS))),$(TEST),$(PYTHON) -m pytest)
ifneq ($(filter list,$(SCENARIO_GROUP)),)
SCENARIO_PATH := scenarios
endif
scenarios:
ifeq ($(SCENARIO_GROUP),help)
	@:
else
	@$(SCENARIO_TEST) $(SCENARIO_PATH) --agents "$$AGENTS" -k "$$CASE" $(if $(filter list,$(SCENARIO_GROUP)),--collect-only -q,-v -s)
endif
verify:
	@$(LAB) smoke-trace
down:
	@docker compose down
