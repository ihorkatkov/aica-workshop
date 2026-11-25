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

.PHONY: help setup pull web ui crm preflight reset run state set-review check-policy test scenarios verify down
help:
	@printf '%s\n' 'make setup              Start the workshop and check model access' \
	 'make ui                 Start the CRM' \
	 'make web                Start ADK chat' \
	 'make reset              Restore CRM data (keeps your code)' \
	 'make scenarios review   Test review handling' \
	 'make scenarios identity Test company/site clarification' \
	 'make scenarios retry    Test repeated requests' \
	 'make scenarios batch    Test all 30 deals' \
	 'make scenarios all      Run all scenarios' \
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
check-policy:
ifeq ($(HOST),1)
	@$(PYTHON) -m tests.check_policy
else
	@docker compose run --rm -T --entrypoint python lab -m tests.check_policy
endif
test:
	@$(TEST) tests -q

# Treat the word after "scenarios" as a suite name, not a separate Make action.
SCENARIO_GROUPS := review identity retry batch all
ifneq ($(filter scenarios,$(MAKECMDGOALS)),)
SCENARIO_ARGS := $(filter-out scenarios,$(MAKECMDGOALS))
ifneq ($(filter-out $(SCENARIO_GROUPS),$(SCENARIO_ARGS)),)
$(error Use make scenarios [review|identity|retry|batch|all])
endif
ifneq ($(word 2,$(SCENARIO_ARGS)),)
$(error Choose one scenario group at a time)
endif
.PHONY: $(SCENARIO_GROUPS)
$(SCENARIO_GROUPS):
	@:
endif
SCENARIO_GROUP := $(if $(SCENARIO_ARGS),$(SCENARIO_ARGS),review)
SCENARIO_PATH := $(if $(filter all,$(SCENARIO_GROUP)),scenarios,scenarios/test_$(SCENARIO_GROUP).py)
scenarios:
	@$(TEST) $(SCENARIO_PATH) -v -s
verify:
	@$(LAB) smoke-trace
down:
	@docker compose down
