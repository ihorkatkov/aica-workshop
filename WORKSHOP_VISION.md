# AICA workshop vision

**How do you stop an AI agent from breaking production?**

AICA Summit hands-on lab · 26 November 2026 · Ihor Katkov

## What we want people to leave with

I want participants to run and improve a real ADK agent and its CRM server, observe plausible mistakes, and leave with a design they can apply to a workflow of their own: **agents propose, systems validate, humans promote.** The interesting question is what the software does when an agent gets something wrong. A validator should turn a bad proposal into specific feedback the agent can act on, while the system keeps control over what actually changes.

By the end, each pair should be able to point to a trace that explains the failure, a policy change they made themselves, and a state check that proves their guardrail worked. They should also be able to name one write in their own workflow, the evidence it requires, a case the system should reject, and who can approve it.

## Audience and choice of exercise

Plan for up to 22 people, about 11 pairs, with mixed experience. Participant responses raised sales conversion, delegation, agent identity and isolation, controlled execution, and preventing production harm. They did not converge on building a sales automation product. Use sales as a recognizable setting for the exercise, not as the topic. Newer builders get a concrete introduction to tools and traces. Experienced builders get a design problem: permissions, useful rejection, stale approvals, and exactly-once effects under retries.

The public invitation asked people to bring a workflow. Honor that in the debrief: give pairs a few minutes to translate the pattern to one action in a workflow they care about. Keep the implementation exercise shared. Building everyone’s real integration during the session would crowd out the practical work and introduce credentials and setup we do not need.

## The case: a realistic synthetic CRM

Use one standard Google ADK agent, an editable prompt, registered HTTP tools, and a separate FastAPI/SQLite CRM. Participants edit the same agent directly; there are no flawed/workshop/reference runtime choices. No custom model selector, scripted assistant summary, or model-free participant path. ADK Web is the interactive interface; separate LangWatch Scenario pytest files exercise the same agent and CRM through real multi-turn conversations.

The fixture world contains 30 deals, 10 companies, and 60 contacts: ambiguous company/site names, conflicting notes, open/missing/expired reviews, cleared reviews, and existing activities. Fix the business date so tests do not decay overnight. Give each scenario an isolated CRM workspace and ADK session; compare baseline and improved versions against identical fixtures and criteria.

1. **Observe the flawed baseline.** An ordinary action-oriented prompt and broad write tools operate against a server that does not enforce business rules. Trace what the real model decided and check persisted effects. Do not hardcode or force a mistake. A refusal is an observed outcome, not a failed demo harness.
2. **Improve the agent and server.** Participants can change the prompt and tools, and implement the server policy. Replace direct mutation with proposals. A rejected action returns a specific reason and a useful allowed alternative. The starter policy remains intentionally incomplete.
3. **Inspect real outcomes in the CRM.** The starter CRM shows deals, stage, security-review state, kickoff counts, notes, and business Activity. It does not supply a proposal/approval/promotion workflow or show Pending requests. Participants implement agent approvals and server enforcement themselves, then demonstrate their outcome through persisted records. The CRM also supports direct human business actions: request a security review, update its status and validity, and schedule kickoff. Activity distinguishes Human from Agent writes. These actions do not approve agent proposals.
4. **Measure useful progress as well as harm.** Scenario's simulated user and judge are real LLMs. Use deterministic assertions for record identity, proposals, and persisted side effects, and judges for conversational quality. Refusing everything must fail. Keep scenario expectations separate from agent/server implementation.
5. **Explore the batch.** Ask the agent to work through the whole queue. Check omissions, wrong-record updates, duplicate actions, and valid no-ops. Run focused cases in the room; broader repeated comparisons can be prepared beforehand. Record model, cases, repetitions, failures, and traces before claiming improvement.

The workshop shows a separate server boundary with local demo identities. It does not claim production-grade authorization or isolation. Participants must enforce their chosen write authorization on the server, not merely hide tools in the prompt. The starter supplies no approval/promotion endpoints.

## Run of show

**Thursday, 26 November, 14:15–15:45 CET, Raadzaal, KIT Amsterdam.** The organizer confirmed 75 minutes of lab plus 15 minutes of Q&A. Keep the live setup in the session. The clock below is a facilitation plan, not a reason to wait for every laptop to finish.

| Time (CET) | What we do | What participants should see |
| --- | --- | --- |
| 14:15–14:35 | Pair up, run `make setup`, sign in to LangWatch, open the first trace. | Each pair can run the lab and inspect a trace. |
| 14:35–14:50 | Run the flawed real agent, compare trace and CRM, reset. | A plausible decision crossed a write boundary it should not have had. |
| 14:50–15:20 | Improve prompt, tools, and server policy in pairs. Rerun scenarios, approve and promote, then stretch to batch or stale state. | Invalid actions are rejected, revised actions make progress, and only an exact, still-valid approval produces a write. |
| 15:20–15:30 | Translate the design to a workflow each pair brought, then compare examples. | Each pair can name its action, validation rule, rejection feedback, and approver. |
| 15:30–15:45 | Q&A and compare observed failures and fixes. | Time to discuss what would change in a real deployment. |

If time slips, pair up around a working environment and cut the batch and stale-state stretch before cutting the trace, policy edit, or proof of promotion.

## Environment and distribution

- **Source:** the workshop repository and README. `agents/` contains standard ADK agents and prompts, `lab/tools.py` the HTTP clients, `crm/` the server and policy exercise, `fixtures/` the CRM world, and `scenarios/` the LangWatch Scenario tests.
- **Local services:** Docker Compose starts LangWatch, the CRM, and ADK Web. `make setup` prepares the account/project, checks telemetry, and verifies a real model/tool round trip. The local CRM desk is on port 8001; scenario groups use short commands such as `make scenarios kickoff`. `make pull` prepares images ahead of time. A prepared Python host path runs the same agent and tools when Docker is unavailable; it still needs a reachable CRM and real model.
- **Participant model access:** a shared hosted CLIProxyAPI Codex service on Boxd, with one workshop-only proxy key per pair. Participants receive preconfigured private `.env` files; provider OAuth stays on the server. Never commit credentials or include them in snapshots. No individual provider login is required for the session. Participants can configure their own OpenAI-compatible provider afterward.
- **No modelless fallback:** if model access fails, join a working pair. Record and resolve proxy availability, quota, and setup issues before the session.
- **Boxd:** the model proxy is hosted there; attendee VM snapshots are not the default delivery path.

## Evidence and remaining checks

The old replay tests are superseded and do not establish the new architecture's behavior. Separate deterministic server tests, real-model scenario observations, browser verification, and setup/load checks. A single successful scenario is not a reliability estimate. Preserve failed baseline traces and check matched before/after runs without weakening expectations.

The organizer committed to send the 22 attendees the corrected time, room and laptop reminder. Treat dispatch as unverified until there is evidence. For the facilitator: arrive at KIT, Mauritskade 63, by **13:15 CET**; pick up the speaker badge at Marble Hall registration and go to Raadzaal for tech setup. Slides are optional. Keep private logistics and participant correspondence out of public repository updates.

## Guardrails for agents continuing the work

Preserve the intentionally flawed baseline and starter-policy exercise. Their failure is part of the lesson. Keep fixtures synthetic and keep real email, CRM, calendar writes, production integrations, and credentials out of the lab. Fix setup friction before adding features. Verify behavior from persisted state and use traces to explain it. Report what you ran separately from what you inferred. Do not publish changes, provision paid infrastructure, or contact participants on the strength of this brief.

## Follow-on: promoting operator changes

The current workshop already uses multiple entities and scenario comparisons. The follow-on expands this into promoting a reusable **operator change**, with a larger independent holdout suite and versioned tested changes.

Then let pairs ask an agent to propose a small change to the operator in a disposable environment. Keep regression tests and holdout expectations outside its write scope. The system returns concrete failures for bounded revisions. A human promotes the exact tested diff. That is the larger design we want people to explore: software that gives agents enough feedback to keep working without giving them the authority to promote their own changes.
