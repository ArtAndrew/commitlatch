"""Single-host SQLite ledger with atomic claims and fenced local completion."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from .model import ActionConflict, OwnershipLost, canonical, fingerprint


class SQLiteLedger:
    def __init__(self, path: str, read_only: bool = False):
        self.path = str(Path(path).expanduser().resolve())
        self.read_only = read_only
        if read_only:
            if not Path(self.path).is_file():
                raise ValueError("Ledger does not exist")
            with self._connection() as db:
                if db.execute("PRAGMA user_version").fetchone()[0] != 1:
                    raise ValueError("Unsupported ledger schema version")
            return
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("Unsupported ledger schema version")
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS actions (
                    id TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    business_key TEXT NOT NULL,
                    adapter TEXT NOT NULL,
                    arguments TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN
                        ('PREPARED','IN_FLIGHT','UNKNOWN','SUCCEEDED','FAILED')),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    lease_token TEXT,
                    lease_kind TEXT,
                    lease_until REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    result TEXT,
                    failure TEXT,
                    UNIQUE(namespace, business_key)
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_id TEXT NOT NULL REFERENCES actions(id),
                    timestamp REAL NOT NULL,
                    kind TEXT NOT NULL,
                    detail TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_by_action
                    ON events(action_id, sequence);
                PRAGMA user_version=1;
            """)

    @contextmanager
    def _connection(self):
        target = Path(self.path).as_uri() + "?mode=ro" if self.read_only else self.path
        db = sqlite3.connect(target, timeout=10, isolation_level=None, uri=self.read_only)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        if not self.read_only:
            db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _transaction(self):
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    @staticmethod
    def _decode(row) -> Dict[str, Any]:
        if row is None:
            raise KeyError("Action not found")
        action = dict(row)
        action["arguments"] = json.loads(action["arguments"])
        action["result"] = (json.loads(action["result"])
                            if action["result"] is not None else None)
        return action

    @staticmethod
    def _event(db, action_id: str, now: float, kind: str,
               detail: Optional[Dict[str, Any]] = None) -> None:
        db.execute("INSERT INTO events(action_id,timestamp,kind,detail) VALUES(?,?,?,?)",
                   (action_id, now, kind, canonical(detail or {})))

    def prepare(self, namespace: str, key: str, adapter: str,
                arguments: Dict[str, Any], now: float) -> Dict[str, Any]:
        for value in (namespace, key, adapter):
            if not isinstance(value, str) or not value.strip() or len(value) > 512:
                raise ValueError("Namespace, business key and adapter must be nonempty strings <=512 chars")
        if type(arguments) is not dict:
            raise ValueError("Action arguments must be a JSON object")
        encoded = canonical(arguments)
        digest = fingerprint(arguments)
        with self._transaction() as db:
            row = db.execute("SELECT * FROM actions WHERE namespace=? AND business_key=?",
                             (namespace, key)).fetchone()
            if row:
                if row["adapter"] != adapter or row["input_hash"] != digest:
                    raise ActionConflict("Business key already bound to different arguments or adapter")
                return self._decode(row)
            action_id = "cl_" + uuid.uuid4().hex
            db.execute("""INSERT INTO actions
                (id,namespace,business_key,adapter,arguments,input_hash,state,created_at,updated_at)
                VALUES(?,?,?,?,?,?,'PREPARED',?,?)""",
                       (action_id, namespace, key, adapter, encoded, digest, now, now))
            self._event(db, action_id, now, "PREPARED", {"input_hash": digest})
            return self._decode(db.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone())

    def get(self, namespace: str, key: str) -> Dict[str, Any]:
        with self._connection() as db:
            return self._decode(db.execute(
                "SELECT * FROM actions WHERE namespace=? AND business_key=?", (namespace, key)).fetchone())

    def list_actions(self):
        with self._connection() as db:
            return [self._decode(row) for row in db.execute("SELECT * FROM actions ORDER BY created_at,id")]

    def events(self, action_id: str):
        with self._connection() as db:
            events = []
            for row in db.execute("SELECT * FROM events WHERE action_id=? ORDER BY sequence", (action_id,)):
                event = dict(row)
                event["detail"] = json.loads(event["detail"])
                events.append(event)
            return events

    def claim(self, action_id: str, purpose: str, now: float, seconds: float):
        """Return (decision, action, token). UNKNOWN is never execution-ready."""
        if purpose not in ("execute", "reconcile"):
            raise ValueError("Invalid claim purpose")
        with self._transaction() as db:
            row = db.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
            action = self._decode(row)
            if action["state"] in ("SUCCEEDED", "FAILED"):
                return action["state"], action, None
            if action["lease_token"]:
                if action["lease_until"] > now:
                    return "BUSY", action, None
                db.execute("""UPDATE actions SET state='UNKNOWN',lease_token=NULL,
                    lease_kind=NULL,lease_until=NULL,updated_at=? WHERE id=?""", (now, action_id))
                self._event(db, action_id, now, "LEASE_EXPIRED", {"purpose": action["lease_kind"]})
                action["state"] = "UNKNOWN"
            required = "PREPARED" if purpose == "execute" else "UNKNOWN"
            if action["state"] != required:
                return action["state"], action, None
            token = uuid.uuid4().hex
            state = "IN_FLIGHT" if purpose == "execute" else "UNKNOWN"
            increment = 1 if purpose == "execute" else 0
            db.execute("""UPDATE actions SET state=?,lease_token=?,lease_kind=?,lease_until=?,
                attempts=attempts+?,updated_at=? WHERE id=?""",
                       (state, token, purpose, now + seconds, increment, now, action_id))
            self._event(db, action_id, now,
                        "ATTEMPT_STARTED" if purpose == "execute" else "RECONCILIATION_STARTED")
            action = self._decode(db.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone())
            return "CLAIMED", action, token

    def finish(self, action_id: str, token: str, state: str, now: float,
               result: Any = None, evidence: Optional[str] = None) -> Dict[str, Any]:
        if state not in ("UNKNOWN", "FAILED", "SUCCEEDED"):
            raise ValueError("Invalid outcome")
        encoded = canonical(result) if state == "SUCCEEDED" else None
        with self._transaction() as db:
            row = db.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
            if row is None or row["lease_token"] != token:
                raise OwnershipLost("Late completion rejected: claim was replaced or recovered")
            db.execute("""UPDATE actions SET state=?,result=?,failure=?,updated_at=?,
                lease_token=NULL,lease_kind=NULL,lease_until=NULL WHERE id=?""",
                       (state, encoded, evidence if state != "SUCCEEDED" else None, now, action_id))
            detail = {"via": row["lease_kind"], "evidence": evidence}
            if state == "SUCCEEDED":
                detail["result"] = result
            self._event(db, action_id, now, state, detail)
            return self._decode(db.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone())

    def retry_failed(self, action_id: str, now: float) -> None:
        from .model import InvalidState
        with self._transaction() as db:
            row = db.execute("SELECT state FROM actions WHERE id=?", (action_id,)).fetchone()
            if row is None or row["state"] != "FAILED":
                raise InvalidState("Only an operation proven not applied can be retried")
            db.execute("UPDATE actions SET state='PREPARED',failure=NULL,updated_at=? WHERE id=?",
                       (now, action_id))
            self._event(db, action_id, now, "RETRY_AUTHORIZED", {"basis": "DEFINITELY_NOT_APPLIED"})
