# Facilitator model proxy

The workshop uses upstream CLIProxyAPI v8.1.3 (checksum-verified release), running as the dedicated `aica-model-proxy.service` on `pantheon-ops`. A new VM could not be created because the org's 10-machine quota was full. Existing services were not replaced.

Endpoint: `https://aica-llm.pantheon-ops.boxd.sh/v1`

- Model: `gpt-6-luna`, consumed through standard ADK LiteLLM and Scenario.
- 11 pair-specific client keys plus a facilitator key. These are proxy keys, not provider credentials.
- Prepared private files: `.lab/participants/pair-01.env` through `pair-11.env`.
- Deliver one pair file privately; copy it to `.env` before `make setup`. No files have been sent to participants automatically.
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
