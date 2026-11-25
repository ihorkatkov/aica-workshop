# How do you stop an AI agent from breaking production?

AICA Summit paired lab. **Agents propose. Systems validate. Humans promote.** The agent coordinates a pilot in a synthetic CRM. The deal is urgent, but its security review is still open. Every command operates on fictional data. No real emails, calendars, CRM integrations or deployments.

## Local LangWatch (one setup per pair)

Prerequisites: Docker with Compose v2, a shell with curl and OpenSSL (macOS/Linux or WSL), and the workshop files. A paid API key is not needed to run the exercise in replay. Before the session, check Docker starts and pre-pull images with `./setup.sh pull`.

1. Run `./setup.sh` and open <http://localhost:5560>. This starts self-hosted LangWatch, its worker and backing services in this Compose project. Only the UI port is published, on loopback.
2. On a fresh install, choose **Create an account**. The standalone installation does not send email; use a synthetic local address and choose a password. Review the terms prompt yourself, then create a local organization and a project called **AICA workshop**. Copy that project's trace-ingestion key into `LANGWATCH_API_KEY` in the generated `.env` file. No LangWatch Cloud account. On a pre-warmed machine these steps can be done ahead of time per pair. Never commit the key files or expose the local dashboard publicly.
3. Run `./verify-stack.sh`. This sends a read-only `get_deal` trace without a model call, then checks that the tool span can be read back by trace ID. In LangWatch, open **Traces** and inspect the new `smoke-trace-…` span tree. HTTP acceptance alone is not the finish line.
4. Separately, to verify a live model, set your own `OPENAI_API_KEY` in `.env` and run `docker compose run --rm lab smoke-model`. Use a billed OpenAI API project key, not a ChatGPT login. The default model is configurable. An organizer-hosted Chat Completions gateway can be used through `OPENAI_BASE_URL` (include its `/v1` path) and its issued token. Other providers are not promised. Keep personal keys off shared workstations; bring one working setup per pair.

In a POSIX shell, define this shortcut for the exercise:

```sh
lab() { docker compose run --rm -T lab "$@"; }
```

**No Docker or no Wi-Fi?** If you already have Python 3.10+, use `lab() { python3 -m lab "$@"; }` and run the replay below. The trace is on disk and `lab trace ID` displays its spans. This fallback does not pretend to be LangWatch. If the provider alone is down, keep Docker/LangWatch and just use replay. A pre-warmed workshop VM can use the same files and a private forwarded UI port; none is bundled.

## The exercise

1. **Red baseline.** `lab reset`, then `lab unsafe`. The agent reports that it checked the prerequisites. In the trace, find `write_deal`; then run `lab state` and prove that `stage` changed even though `security_review` is open. Reset again. The red baseline defaults to deterministic replay so everyone sees the same failure.
2. **Remove direct writes and add a guardrail.** Open `lab/agent.py`: compare the broken tool list with the safe one, which can only propose. Run `lab safe` before editing and notice it can still propose the wrong action, although nothing changes yet. Edit only `lab/policy.py` to reject kickoff when review is not cleared. Return an error code, reason, and `allowed: ["request_review_update"]` as illustrated by the TODO. On your host, `python3 -m tests.check_policy` is red until your rule is right; in Docker use `docker compose run --rm --entrypoint python lab -m tests.check_policy`. Use the trace to see that the first proposal is rejected and the second is queued. `lab --solution safe` runs the reference policy if you get stuck; use the same `--solution` prefix for its promotion.
3. **Prove the boundary.** Copy the pending proposal ID to replace `ID` in these commands. Try `lab promote ID` before approval: it must return `NOT_APPROVED`. Inspect the exact proposal with `lab inspect ID`, explicitly approve it with `lab approve ID`, and check state is still unchanged. Now `lab promote ID` applies exactly one review request. Run it again: no second write. Compare the trace with `lab state`.
4. **Stretch: stale approval.** Run `lab set-review cleared`, then `lab safe` in replay and approve the kickoff proposal. Run `lab set-review open` before promotion. Promotion must report `STALE_STATE`, and the stage must remain `pilot_requested`. A fresh proposal needs fresh approval. Reset before repeating.
5. **Live model option.** After the deterministic baseline, run `lab safe --mode live` if the provider check passed. A real model might choose the allowed action immediately; that is fine. Compare its trace to replay. The validator, not model behavior, protects the mutation.

The model is not a shell process: it receives a small tool schema and cannot invoke the human CLI commands. This lab shows the tool/commit boundary using one SQLite file. A real deployment additionally separates service identities, enforces human authorization outside the model process, and keeps durable audit records. The local instance is for workshop data, not production.

## Facilitation

**75 minutes + up to 15 Q&A.** 20 setup and live trace; 15 diagnose; 30 pairs build, repeat and stretch; 10 debrief. If the original 60-minute slot is needed, use 15/10/25/10. Keep the exercise shared; end by asking which action in each person's work should sit behind this control.

Before distributing: on a clean supported laptop, time `./setup.sh` after pre-pull, verify a dashboard login and fresh tool span, then run a real API-key check. Rehearse any Boxd fallback from a guest browser. Bring the local trace replay if available networking fails.

## Tests and shutdown

```sh
python3 -m unittest discover -s tests -v     # no provider or LangWatch account
./verify-stack.sh                            # real LangWatch canary, after local project setup
python3 -m tests.rehearse_stack               # full Docker + LangWatch replay, no model key
LIVE_MODEL=1 ./verify-stack.sh               # additionally checks a live provider (billable)
docker compose down                          # preserve LangWatch data
```

`lab reset` resets the fake CRM without deleting traces. Use `docker compose down -v` only if you also want to erase this Compose project's LangWatch data. Sources: [LangWatch Docker reference](https://github.com/langwatch/langwatch/blob/main/infra/compose.yml), [OTLP endpoint](https://langwatch.ai/blog/instrumenting-your-openclaw-agent-with-opentelemetry), [trace readback](https://langwatch.ai/scenario/advanced/remote-traces/).
