# Facilitator model proxy

The workshop uses upstream CLIProxyAPI v8.1.3 (checksum-verified release), running as the dedicated `aica-model-proxy.service` on `pantheon-ops`. The machine also hosts other services.

Endpoint: `https://aica-llm.pantheon-ops.boxd.sh/v1`

- The [environment template](../.env.example) selects `gpt-6-luna` for ADK and the Scenario default, and `gpt-6.2-sol` for the judge. Native scenario clients use their own sign-in and [model pins](../scenarios/conftest.py).
- Give participants the shared workshop API key privately. On first setup, they enter it at the prompt. Previously issued pair and facilitator keys also work.
- OAuth remains in the remote service's private auth directory. No OAuth token is distributed to participants or included in the repository.
- The management API and control panel are disabled. Unauthenticated model requests must return 401.
- The machine has auto-suspend and auto-hibernate disabled. No dependency on a laptop tunnel.

## Operations

```sh
boxd machine exec pantheon-ops -- 'sudo systemctl status aica-model-proxy --no-pager'
boxd machine exec pantheon-ops -- 'sudo systemctl restart aica-model-proxy'
boxd machine exec pantheon-ops -- 'sudo journalctl -u aica-model-proxy --since "10 min ago" --no-pager'
```

`install-proxy.sh` installs the pinned upstream binary and systemd service after the private auth/config files have been copied. It contains no credentials. The running configuration is `/home/boxd/aica-model-proxy/config.yaml`; access keys are under `access.api-keys`. Remove an individual key there to revoke a pair. Do not print the configuration or auth files into shared logs.

After the workshop, stop/disable only `aica-model-proxy.service` and remove the named `aica-llm` port proxy to close access; do not stop the shared machine. Long-term use requires its own provider setup. Subscription quota, provider availability, and OAuth renewal remain runtime dependencies; rehearse again before doors open. There is no claim that one concurrent probe guarantees a 90-minute session.

## Prepare a workshop laptop

Run `make pull` ahead of time to download and build the images. During the workshop, `make setup` creates or reuses the local account and project and verifies the model, CRM tool, and trace. If setup stops, inspect `.lab/setup.log`. The CRM desk uses a local browser identity. Keep the services on the workshop laptop.

For a prepared Python host, copy `.env.example` to `.env` if you don’t have a local configuration yet. Configure a real model and a reachable LangWatch endpoint and project key in `.env` (see [the template](../.env.example)). With the Docker CRM and chat stopped, run:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
make crm HOST=1             # terminal 1
make web HOST=1             # terminal 2
make preflight HOST=1       # terminal 3
make scenarios kickoff HOST=1
```

To switch providers, set `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `AGENT_MODEL`, `SCENARIO_MODEL`, and `JUDGE_MODEL` in the local `.env`. For a model-free infrastructure check, run `make test`. The policy-hook test substitutes a test rule. The console tests exercise the configured rule. Use `make check-policy` and `make check-kickoff` to assess the participant’s implementation.
