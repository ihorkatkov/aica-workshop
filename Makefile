LAB = docker compose run --rm -T lab
POLICY = $(if $(filter 1,$(SOLUTION)),--solution)
MODE ?= replay
export ID VALUE MODE

.PHONY: help setup pull verify reset unsafe safe state trace inspect approve promote set-review check-policy test down

help:
	@printf '%s\n' 'make setup                 Start the workshop and print dashboard credentials' \
	  'make reset                 Restore the starting deal' \
	  'make unsafe                Run the broken agent' \
	  'make safe                  Run the agent with your policy' \
	  'make safe SOLUTION=1       Run with the reference policy' \
	  'make state                 Show the current deal' \
	  'make trace ID=...          Show the spans from a run' \
	  'make inspect ID=...        Read a proposal' \
	  'make approve ID=...        Approve a proposal' \
	  'make promote ID=...        Apply an approved proposal' \
	  'make set-review VALUE=open|cleared' \
	  'make check-policy          Check your guardrail' \
	  'make verify                Send and read back a trace' \
	  'make test                  Run the automated tests' \
	  'make pull                  Prepare the images ahead of time' \
	  'make down                  Stop the workshop and keep its data'

setup:
	@./setup.sh

pull:
	@./setup.sh pull

verify:
	@./verify-stack.sh

reset state:
	@$(LAB) $@

unsafe safe:
	@$(LAB) $(POLICY) $@ --mode "$$MODE"

trace inspect approve promote:
	@test -n "$$ID" || { echo 'Usage: make $@ ID=...'; exit 2; }
	@$(LAB) $(POLICY) $@ "$$ID"

set-review:
	@$(LAB) set-review "$${VALUE:?Use make set-review VALUE=open or VALUE=cleared}"

check-policy:
	@docker compose run --rm -T --entrypoint python lab -m tests.check_policy

test:
	@docker compose run --rm -T --entrypoint python lab -m unittest discover -s tests -v

down:
	@docker compose down
