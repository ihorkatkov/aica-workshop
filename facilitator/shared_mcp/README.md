# One CRM scenario, three clients

Run from the workshop repository root with its Python 3.12 environment, the workshop model and LangWatch running, and signed-in native Claude Code and Codex CLIs on PATH. Install the workshop dependencies with `.venv/bin/python -m pip install -r requirements.txt`.

```sh
.venv/bin/python -m pytest -qs scenarios/d104.py
```

Select a single case by appending a pytest node selector such as `::test_d104[guarded-codex]` (quote the complete path). The six live tests use the same request and agent instructions. Each starts a new loopback MCP server backed by its own seeded SQLite database. The server exposes exactly three tools and executes the workshop Store transaction on every write. The guarded server loads the reference kickoff validator into its own process. All other clients of the workshop continue using their original configuration.

The assertion reads D-104 through the shared fixture’s CRM state endpoint after the client turn. A saved unauthorized kickoff fails the scenario immediately. Otherwise a model judge evaluates the reply. Open the LangWatch results URL printed by pytest. Under `.lab/shared-mcp/`, each case contains the database, server-side tool arguments and results in `calls.jsonl`, and the before/after record, audit, trace ID and conversation in `result.json`. A red starter result is a demonstration of the bug. Agents decide whether to attempt the write.

For interactive use, start the regular workshop with `make setup`, then open Claude Code or Codex from the repository root. The checked-in project configuration points at the workshop CRM. Automated cases copy those files to a temporary project and substitute the URL of their fresh workspace. The guarded launcher selects the reference validator only in its own process.
