# Workshop verification

Run `make test` in the workshop directory. The eight tests launch the participant CLI, check persisted CRM state and inspect the saved OpenTelemetry spans. Local HTTP doubles exercise Chat Completions correction feedback and LangWatch export failures. The separate `make check-policy` exercise intentionally fails with the starter policy.

## Verified on an Apple Silicon Mac

- Ran `make setup` against empty Compose volumes, repeated it, and checked that the project count stayed at one and the configured key stayed the same. Signed in through a fresh Chrome session with the printed credentials and saw the smoke trace in the project’s Trace Explorer.
- Exercised the Make targets for reset, unsafe and safe runs, trace lookup, inspect, approve, promote, state and review changes. All eight tests passed through `make test`.
- Built the Python 3.12 lab image and started a pre-warmed LangWatch 3.23.0 project. Both `./verify-stack.sh` and `python3 -m tests.rehearse_stack` passed against the running service.
- The replay ran through the ADK runner and registered function tools. The rehearsal verified the unsafe write, rejected kickoff, revised proposal, single approved write and stale approval against SQLite. LangWatch returned the corresponding tool spans by trace ID.
- An existing Codex ChatGPT login passed the provider smoke check and the ADK safe exercise. The model proposed a review update. LangWatch returned the ADK agent, model and proposal spans for that invocation.

## Still to rehearse before distribution

Time fresh setup on a second laptop. Fresh ChatGPT browser sign-in and a billed OpenAI project key were outside this run. Prepare the host environment or build the Docker image before an offline session.
