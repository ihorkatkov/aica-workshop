import secrets
import sqlite3

ACTIONS = {"schedule_kickoff", "request_review_update"}

class Store:
    def __init__(self, path, validate):
        self.db = sqlite3.connect(path, isolation_level=None, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.validate = validate
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS deal(id TEXT PRIMARY KEY, security_review TEXT,
            stage TEXT, revision INTEGER NOT NULL, review_requests INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS proposal(id TEXT PRIMARY KEY, action TEXT NOT NULL,
            revision INTEGER NOT NULL, status TEXT NOT NULL);
        INSERT OR IGNORE INTO deal VALUES('D-104', 'open', 'pilot_requested', 1, 0);
        """)

    def state(self):
        return dict(self.db.execute("SELECT * FROM deal").fetchone())

    def reset(self):
        self.db.executescript("""
        BEGIN IMMEDIATE;
        DELETE FROM proposal;
        UPDATE deal SET security_review='open', stage='pilot_requested',
          revision=revision+1, review_requests=0;
        COMMIT;
        """)
        return self.state()

    def set_review(self, value):
        self.db.execute("UPDATE deal SET security_review=?, revision=revision+1", (value,))
        return self.state()

    def _apply(self, action):
        if action == "schedule_kickoff":
            self.db.execute("UPDATE deal SET stage='kickoff_scheduled', revision=revision+1")
        elif action == "request_review_update":
            self.db.execute("UPDATE deal SET review_requests=review_requests+1, revision=revision+1")
        else:
            raise ValueError("Unknown action.")

    def unsafe_write(self, action):
        if action not in ACTIONS:
            return {"status": "rejected", "code": "UNKNOWN_ACTION"}
        self._apply(action)
        return {"status": "applied_without_checks", "record": self.state()}

    def _transaction(self, fn):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            result = fn()
            self.db.execute("COMMIT")
            return result
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def propose(self, action):
        if action not in ACTIONS:
            return {"status": "rejected", "code": "UNKNOWN_ACTION"}
        def txn():
            row = self.state()
            error = self.validate(row, action)
            if error:
                return {"status": "rejected", **error}
            pid = secrets.token_hex(6)
            self.db.execute("INSERT INTO proposal VALUES(?, ?, ?, 'pending')",
                            (pid, action, row["revision"]))
            return {"status": "pending", "proposal_id": pid, "action": action,
                    "revision": row["revision"]}
        return self._transaction(txn)

    def proposal(self, pid):
        row = self.db.execute("SELECT * FROM proposal WHERE id=?", (pid,)).fetchone()
        return dict(row) if row else None

    def approve(self, pid):
        changed = self.db.execute(
            "UPDATE proposal SET status='approved' WHERE id=? AND status='pending'", (pid,)).rowcount
        return {"status": "approved", "proposal_id": pid} if changed else {
            "status": "rejected", "code": "NOT_PENDING"}

    def promote(self, pid):
        def txn():
            p = self.proposal(pid)
            if not p or p["status"] != "approved":
                return {"status": "rejected", "code": "NOT_APPROVED"}
            row = self.state()
            if row["revision"] != p["revision"]:
                self.db.execute("UPDATE proposal SET status='stale' WHERE id=?", (pid,))
                return {"status": "rejected", "code": "STALE_STATE",
                        "message": "The record changed after the proposal. Request a fresh proposal."}
            error = self.validate(row, p["action"])
            if error:
                return {"status": "rejected", **error}
            self._apply(p["action"])
            self.db.execute("UPDATE proposal SET status='applied' WHERE id=?", (pid,))
            return {"status": "applied", "proposal_id": pid, "record": self.state()}
        return self._transaction(txn)
