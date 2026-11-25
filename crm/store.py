"""SQLite transactions own validation, approvals and synthetic effects."""

import json
from pathlib import Path
import secrets
import sqlite3

from . import policy

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
          CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, workspace TEXT,
            deal_id TEXT, action TEXT, revision INTEGER, status TEXT);
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

    def reset(self, workspace):
        def txn():
            self.db.execute("INSERT OR REPLACE INTO workspaces VALUES(?)", (workspace,))
            for table in ("records", "proposals", "audit"):
                self.db.execute(f"DELETE FROM {table} WHERE workspace=?", (workspace,))
            fixture = json.loads(FIXTURE.read_text())
            for kind in ("companies", "contacts", "deals"):
                for record in fixture[kind]:
                    self.save(workspace, kind, {**record, "as_of": fixture["as_of"]})
            self.log(workspace, "reset", {})
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
            "proposals": [
                dict(r)
                for r in self.db.execute(
                    "SELECT * FROM proposals WHERE workspace=? ORDER BY rowid",
                    (workspace,),
                )
            ],
            "audit": [
                {**dict(r), "detail": json.loads(r["detail"])}
                for r in self.db.execute(
                    "SELECT * FROM audit WHERE workspace=? ORDER BY id", (workspace,)
                )
            ],
        }

    def validate(self, workspace, record, action):
        return policy.validate(record, action)

    def apply(self, workspace, record, action):
        # Guarded promotion is also a no-op when the business effect already exists.
        field = "kickoffs" if action == "schedule_kickoff" else "review_requests"
        if record[field]:
            return False
        record[field] += 1
        record["revision"] += 1
        if action == "schedule_kickoff":
            record["stage"] = "kickoff_scheduled"
        self.save(workspace, "deals", record)
        return True

    def action(self, workspace, deal_id, action, direct=False):
        if action not in ACTIONS:
            return {"status": "rejected", "code": "UNKNOWN_ACTION"}

        def txn():
            record = self.get(workspace, deal_id)
            if "security_review" not in record:
                raise ValueError("Expected a deal ID")
            if direct:
                if not policy.ALLOW_DIRECT_WRITES:
                    return {"status": "rejected", "code": "DIRECT_WRITE_DISABLED"}
                # Intentionally flawed: trusts the caller; repeated writes duplicate effects.
                field = (
                    "kickoffs" if action == "schedule_kickoff" else "review_requests"
                )
                record[field] += 1
                record["revision"] += 1
                if action == "schedule_kickoff":
                    record["stage"] = "kickoff_scheduled"
                self.save(workspace, "deals", record)
                self.log(
                    workspace, "unsafe_write", {"deal_id": deal_id, "action": action}
                )
                return {"status": "applied_without_checks", "record": record}
            error = self.validate(workspace, record, action)
            if error:
                self.log(
                    workspace,
                    "rejected",
                    {"deal_id": deal_id, "action": action, **error},
                )
                return {"status": "rejected", **error}
            field = "kickoffs" if action == "schedule_kickoff" else "review_requests"
            if record[field]:
                return {
                    "status": "no_change",
                    "reason": "Activity already recorded",
                    "record": record,
                }
            existing = self.db.execute(
                "SELECT * FROM proposals WHERE workspace=? AND deal_id=? AND action=? AND revision=? AND status IN ('pending','approved')",
                (workspace, deal_id, action, record["revision"]),
            ).fetchone()
            if existing:
                return dict(existing)
            pid = secrets.token_hex(6)
            self.db.execute(
                "INSERT INTO proposals VALUES(?,?,?,?,?,'pending')",
                (pid, workspace, deal_id, action, record["revision"]),
            )
            self.log(
                workspace,
                "proposed",
                {"proposal_id": pid, "deal_id": deal_id, "action": action},
            )
            return self.proposal(workspace, pid)

        return self.transaction(txn)

    def proposal(self, workspace, pid):
        row = self.db.execute(
            "SELECT * FROM proposals WHERE workspace=? AND id=?", (workspace, pid)
        ).fetchone()
        if not row:
            raise KeyError("Proposal not found")
        return dict(row)

    def approve(self, workspace, pid):
        def txn():
            proposal = self.proposal(workspace, pid)
            if proposal["status"] != "pending":
                return {"status": "rejected", "code": "NOT_PENDING"}
            self.db.execute("UPDATE proposals SET status='approved' WHERE id=?", (pid,))
            self.log(workspace, "approved", {"proposal_id": pid})
            return self.proposal(workspace, pid)

        return self.transaction(txn)

    def promote(self, workspace, pid):
        def txn():
            proposal = self.proposal(workspace, pid)
            if proposal["status"] == "applied":
                return {"status": "already_applied", "proposal_id": pid}
            if proposal["status"] != "approved":
                return {"status": "rejected", "code": "NOT_APPROVED"}
            record = self.get(workspace, proposal["deal_id"])
            if record["revision"] != proposal["revision"]:
                self.db.execute(
                    "UPDATE proposals SET status='stale' WHERE id=?", (pid,)
                )
                self.log(workspace, "stale", {"proposal_id": pid})
                return {"status": "rejected", "code": "STALE_STATE"}
            error = self.validate(workspace, record, proposal["action"])
            if error:
                return {"status": "rejected", **error}
            changed = self.apply(workspace, record, proposal["action"])
            self.db.execute("UPDATE proposals SET status='applied' WHERE id=?", (pid,))
            self.log(
                workspace,
                "promoted",
                {"proposal_id": pid, "deal_id": record["id"], "changed": changed},
            )
            return {
                "status": "applied" if changed else "no_change",
                "proposal_id": pid,
                "record": record,
            }

        return self.transaction(txn)

    def set_review(self, workspace, deal_id, status):
        def txn():
            record = self.get(workspace, deal_id)
            record.update(
                security_review=status,
                review_valid_until="2026-12-31" if status == "cleared" else None,
                revision=record["revision"] + 1,
            )
            self.save(workspace, "deals", record)
            self.log(
                workspace, "review_changed", {"deal_id": deal_id, "status": status}
            )
            return record

        return self.transaction(txn)
