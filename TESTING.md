# Verification and release gate

Verified on Linux and on an Apple Silicon Mac:
- Seven automated tests launched the actual workshop CLI, persisted and reread SQLite state, and checked trace files.
- The task's learner-policy check failed before the rule and passed with the reference implementation.
- Local HTTP doubles checked the Chat Completions tool schema and correction feedback, the OTLP request, partial rejection, and trace readback.
- Shell syntax and the actual `docker compose config` command passed.

Verified with Docker Desktop and real LangWatch 3.23.0 on the Mac:
- Pulled the images, started the local Compose stack, and checked the healthy app and worker. Local browser reached sign-in; a synthetic login reached organization onboarding. The onboarding terms checkbox was not accepted on anyone's behalf.
- Provisioned a synthetic organization and project using the instance's published local admin API for the technical rehearsal. Trace ingestion and API readback passed for the startup canary and the unsafe write, proposal, and human promotion tool spans.
- `python3 -m tests.rehearse_stack` ran the real containerized CLI against that stack. It verified unsafe kickoff while the review is open, rejection then a revised pending proposal, no change before approval, exactly one write after promotion, and rejection of stale approval without mutating the record.

Still to rehearse before distributing: open the trace in a participant's authenticated dashboard after the human onboarding step, and try a real model call with an authorized API key. No model-provider key was available or used for this rehearsal. For a live room, pre-pull the images and time the cold start on a second machine; the archive has no secrets or rehearsal data.
