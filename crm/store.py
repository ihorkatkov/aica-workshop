"""SQLite storage for synthetic CRM records and recorded activity."""

import json
import sqlite3
from pathlib import Path

from . import policy, stages

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/crm.json"
ACTIONS = {"schedule_kickoff", "request_review_update"}


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(
            path, isolation_level=None, timeout=15, check_same_thread=False
        )
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY);
          CREATE TABLE IF NOT EXISTS records(workspace TEXT, id TEXT, kind TEXT, data TEXT,
            PRIMARY KEY(workspace,id));
          CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, workspace TEXT,
            event TEXT, detail TEXT);
        """)

        # Upgrade the earlier multi-agent lab without discarding its CRM evidence.
        if any(
            row[1] == "variant"
            for row in self.db.execute("PRAGMA table_info(workspaces)")
        ):
            self.db.execute("ALTER TABLE workspaces DROP COLUMN variant")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.db.close()

    def transaction(self, fn):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            result = fn()
            self.db.execute("COMMIT")
            return result
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def log(self, workspace, event, detail):
        self.db.execute(
            "INSERT INTO audit(workspace,event,detail) VALUES(?,?,?)",
            (workspace, event, json.dumps(detail)),
        )

    def require_workspace(self, workspace):
        row = self.db.execute(
            "SELECT id FROM workspaces WHERE id=?", (workspace,)
        ).fetchone()
        if not row:
            raise KeyError("Workspace not found")
        return row[0]

    def reset(self, workspace, dataset="kickoff"):
        if dataset not in {"kickoff", "stretch"}:
            raise ValueError("Unknown workshop dataset")

        def txn():
            self.db.execute("INSERT OR REPLACE INTO workspaces VALUES(?)", (workspace,))
            for table in ("records", "audit"):
                self.db.execute(f"DELETE FROM {table} WHERE workspace=?", (workspace,))
            # A reset also clears obsolete request data from older workshop databases.
            if self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='proposals'"
            ).fetchone():
                self.db.execute("DELETE FROM proposals WHERE workspace=?", (workspace,))
            fixture = json.loads(FIXTURE.read_text())
            for kind in ("companies", "contacts", "deals"):
                for record in fixture[kind]:
                    self.save(workspace, kind, {**record, "as_of": fixture["as_of"]})
            if dataset == "stretch":
                for deal_id, note in json.loads(
                    FIXTURE.with_name("stretch.json").read_text()
                ).items():
                    record = self.get(workspace, deal_id)
                    record.update(
                        stage="pilot",
                        kickoffs=1,
                        notes=note,
                        security_review="cleared",
                        review_valid_until="2026-12-31",
                    )
                    self.save(workspace, "deals", record)
            self.log(workspace, "reset", {"dataset": dataset})
            return {
                "workspace": workspace,
                "deals": len(fixture["deals"]),
            }

        return self.transaction(txn)

    def save(self, workspace, kind, record):
        self.db.execute(
            "INSERT OR REPLACE INTO records VALUES(?,?,?,?)",
            (workspace, record["id"], kind, json.dumps(record)),
        )

    def get(self, workspace, record_id):
        self.require_workspace(workspace)
        row = self.db.execute(
            "SELECT data FROM records WHERE workspace=? AND id=?",
            (workspace, record_id),
        ).fetchone()
        if not row:
            raise KeyError("Record not found")
        return json.loads(row[0])

    def deals(self, workspace, query=""):
        self.require_workspace(workspace)
        rows = self.db.execute(
            "SELECT data FROM records WHERE workspace=? AND kind='deals' ORDER BY id",
            (workspace,),
        ).fetchall()
        return [
            r
            for row in rows
            if query.lower() in json.dumps(r := json.loads(row[0])).lower()
        ]

    def state(self, workspace):
        return {
            "workspace": self.require_workspace(workspace),
            "deals": self.deals(workspace),
            "proposals": stages.proposals(self, workspace),
            "audit": [
                {**dict(r), "detail": json.loads(r["detail"])}
                for r in self.db.execute(
                    "SELECT * FROM audit WHERE workspace=? ORDER BY id", (workspace,)
                )
            ],
        }

    def action(self, workspace, deal_id, action, *, actor="agent"):
        if action not in ACTIONS:
            raise ValueError("Unknown CRM action")

        def txn():
            record = self.get(workspace, deal_id)
            if "security_review" not in record:
                raise ValueError("Expected a deal ID")
            error = policy.validate(record, action)
            if error:
                return {"status": "rejected", **error}
            # Starter behavior: participants implement authorization, validation and retries.
            field = "kickoffs" if action == "schedule_kickoff" else "review_requests"
            fields = ["stage", field]
            if action == "request_review_update":
                fields += ["security_review", "review_valid_until"]
            before = {key: record[key] for key in fields}
            record[field] += 1
            record["revision"] += 1
            if action == "schedule_kickoff":
                record["stage"] = "kickoff_scheduled"
            else:
                record["security_review"] = "open"
                record["review_valid_until"] = None
            self.save(workspace, "deals", record)
            self.log(
                workspace,
                "deal_updated",
                {
                    "deal_id": deal_id,
                    "action": action,
                    "actor": actor,
                    "before": before,
                    "after": {key: record[key] for key in fields},
                },
            )
            return {"status": "applied", "record": record}

        return self.transaction(txn)

    def set_review(
        self, workspace, deal_id, status, *, valid_until=None, actor="human"
    ):
        def txn():
            record = self.get(workspace, deal_id)
            if "security_review" not in record:
                raise ValueError("Expected a deal ID")
            before = record["security_review"]
            record.update(
                security_review=status,
                review_valid_until=(valid_until or "2026-12-31")
                if status == "cleared"
                else None,
                revision=record["revision"] + 1,
            )
            self.save(workspace, "deals", record)
            self.log(
                workspace,
                "review_changed",
                {
                    "deal_id": deal_id,
                    "status": status,
                    "previous_status": before,
                    "actor": actor,
                    "valid_until": record["review_valid_until"],
                },
            )
            return record

        return self.transaction(txn)
