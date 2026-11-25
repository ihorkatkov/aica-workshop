# How do you stop an AI agent from breaking production?

AICA Summit paired lab. **Agents propose. Systems validate. Humans promote.** The agent coordinates a pilot in a synthetic CRM. The deal is urgent, but its security review is still open. Every command operates on fictional data. No real emails, calendars, CRM integrations or deployments.

The [Google ADK](https://github.com/google/adk-python) runner executes each turn. Both agents read the deal with `get_deal`. The unsafe agent can also call `write_deal`; the safe agent can call `propose_action`. Only the participant CLI exposes approval and promotion. LangWatch records the ADK invocation, agent, model turns and tool calls using the [Google ADK instrumentor](https://langwatch.ai/docs/integration/python/integrations/google-ai).

## Start the workshop

With Docker running, open a terminal in this directory and run:

```sh
make setup
```

Setup builds the lab, starts LangWatch, creates the participant account and project, configures the trace key, and reads back a first trace. Open the **Dashboard** link printed at the end and sign in with the email and password shown beside it. Run `make setup` again to resume the same project and print its credentials. See `make help` for the exercise commands.

Each pair needs Make, Docker Compose v2, curl, OpenSSL, and a POSIX shell (macOS, Linux or WSL). The default replay needs no model account. Organizers can run `make pull` while online to prepare the images ahead of time.

### Host setup for ChatGPT or offline replay

Install Python 3.12 and prepare the virtual environment while online. From the workshop directory:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

### Live model with a ChatGPT subscription

On a participant’s own laptop, activate the workshop virtual environment and install the [Codex CLI](https://developers.openai.com/codex/cli/) (tested with 0.159.2). A ChatGPT plan with Codex access covers these calls under its usage limits. From the workshop directory, run:

```sh
codex login                              # choose Sign in with ChatGPT in the browser
codex login status                       # expect "Logged in using ChatGPT"
python3 -m lab smoke-model --mode chatgpt
python3 -m lab --solution safe --mode chatgpt
```

Run these commands on the host, including when Docker hosts LangWatch. Codex manages the login, so leave `OPENAI_API_KEY` empty for this route. With the local project key in `.env`, the host CLI also exports its trace to LangWatch. The safe run uses the reference policy. Drop `--solution` to try your edited policy. Inspect, approve and promote the returned proposal ID with the same host CLI. [Codex authentication](https://developers.openai.com/codex/auth/)

### Optional OpenAI API key

Set `OPENAI_API_KEY` in `.env` and run `docker compose run --rm lab smoke-model`. For a compatible gateway, also set `OPENAI_BASE_URL` including its `/v1` path, and `OPENAI_MODEL`. Run the live exercise with `make safe MODE=live`.

## The exercise

1. **Find the unsafe write.** Run `make reset`, `make unsafe`, then `make state`. Find `write_deal` in the dashboard trace. Compare the agent’s claim with the persisted stage and open security review. Run `make reset` again.
2. **Add the guardrail.** Compare the tools in `lab/agent.py`. Run `make safe` and inspect its pending proposal. Edit `lab/policy.py` to reject kickoff while the review is open and allow `request_review_update`. Run `make check-policy` until it passes, then `make safe` again. The trace should show a rejected kickoff followed by a pending review request. To use the reference rule, add `SOLUTION=1` to both `make safe` and `make promote`.
3. **Prove the approval boundary.** Copy the new proposal ID. Run the commands below, replacing `abc123` with that ID. Promotion before approval returns `NOT_APPROVED`. Approval alone leaves the deal unchanged. After both promotion attempts, `review_requests` should equal one.

   ```sh
   ID=abc123
   make promote ID="$ID"
   make inspect ID="$ID"
   make approve ID="$ID"
   make state
   make promote ID="$ID"
   make promote ID="$ID"
   make state
   ```

4. **Try a stale approval.** Run `make set-review VALUE=cleared`, then `make safe` and approve its kickoff proposal. Run `make set-review VALUE=open` and promote that ID. Check for `STALE_STATE` and confirm with `make state` that the stage remains `pilot_requested`.
5. **Compare a live decision.** Use the ChatGPT or API-key instructions above and compare the trace to replay. A real model may choose the review update immediately.

For a local trace, run `make trace ID=...` with a trace ID. For offline replay without Docker, activate the prepared Python environment and run `python -m lab` with the corresponding subcommand (for example, `python -m lab --solution safe`).

In API-key mode the model receives one tool schema. In ChatGPT mode the host asks Codex for a structured action in an empty temporary directory with shell tools disabled. Both adapters return an ADK function call. ADK executes the registered tool and feeds its result into the next turn. The replay adapter supplies deterministic decisions through that same path. This lab shows the tool/commit boundary using one SQLite file. A real deployment additionally separates service identities, enforces human authorization outside the model process, and keeps durable audit records. The local instance is for workshop data, not production.

## Facilitation

**75 minutes + up to 15 Q&A.** 20 setup and live trace; 15 diagnose; 30 pairs build, repeat and stretch; 10 debrief. If the original 60-minute slot is needed, use 15/10/25/10. Keep the exercise shared; end by asking which action in each person's work should sit behind this control.

Before distributing: on a clean supported laptop, time `make setup` after pre-pull, verify a dashboard login and fresh tool span, then run a real smoke check for the live model option your pair will use. Rehearse any Boxd fallback from a guest browser. Bring the local trace replay if available networking fails.

## Tests and shutdown

```sh
make test                       # automated tests inside the lab image
make verify                     # send and read back a fresh LangWatch trace
python3 -m tests.rehearse_stack  # full Docker + LangWatch replay
make down                       # stop the stack and preserve workshop data
```

`make reset` resets the fake CRM without deleting traces. Use `docker compose down -v` only if you also want to erase this Compose project's LangWatch data. Sources: [LangWatch Docker reference](https://github.com/langwatch/langwatch/blob/main/infra/compose.yml), [OTLP endpoint](https://langwatch.ai/blog/instrumenting-your-openclaw-agent-with-opentelemetry), [trace readback](https://langwatch.ai/scenario/advanced/remote-traces/).
