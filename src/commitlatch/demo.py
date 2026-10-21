"""An intentionally non-idempotent test sink, in a separate SQLite database.

This is a simulator, not a remote API or a Stripe adapter. Its independent
transaction exposes the same local-ledger/external-effect commit gap.
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from .engine import CommitLatch
from .ledger import SQLiteLedger
from .model import DefinitelyNotApplied, Reconciliation, UnknownOutcome, canonical


class DemoSink:
    def __init__(self, path: str, observable: bool = True, fault: str = "none"):
        self.path = str(Path(path).resolve())
        self.observable = observable
        self.fault = fault
        # Account identity is part of the adapter name, preventing wrong-target recovery.
        self.name = "demo-sink/v1:" + self.path
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS effects (
                receipt INTEGER PRIMARY KEY AUTOINCREMENT,
                effect_key TEXT NOT NULL,
                arguments TEXT NOT NULL
            )""")

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def execute(self, effect_key, arguments):
        if self.fault == "reject-before-effect":
            raise DefinitelyNotApplied("Test service rejected before executing")
        if self.fault == "raise-before-effect":
            raise ConnectionError("Dispatch outcome deliberately unavailable")
        with self._db() as db:
            # There is deliberately no UNIQUE constraint on effect_key.
            cursor = db.execute("INSERT INTO effects(effect_key,arguments) VALUES(?,?)",
                                (effect_key, canonical(arguments)))
            receipt = cursor.lastrowid
        result = {"receipt": receipt, "operation": arguments.get("operation", "test")}
        if self.fault == "exit-after-effect":
            # A real process death: no finally block and no ledger acknowledgement.
            os._exit(42)
        if self.fault == "raise-after-effect":
            raise ConnectionError("Response deliberately dropped after committed effect")
        return result

    def reconcile(self, effect_key, arguments):
        if not self.observable:
            return Reconciliation.unknown("Provider offers no lookup for this operation")
        with self._db() as db:
            rows = db.execute("SELECT receipt,arguments FROM effects WHERE effect_key=?",
                              (effect_key,)).fetchall()
        if len(rows) != 1:
            # Absence does NOT prove a previously dispatched request cannot arrive later.
            return Reconciliation.unknown("Lookup found %d receipts; outcome is not proven" % len(rows))
        receipt, saved_arguments = rows[0]
        if saved_arguments != canonical(arguments):
            return Reconciliation.unknown("Receipt arguments do not match the original operation")
        return Reconciliation.succeeded(
            {"receipt": receipt, "operation": arguments.get("operation", "test")},
            "Test service durable receipt #%d" % receipt)

    def count(self):
        with self._db() as db:
            return db.execute("SELECT COUNT(*) FROM effects").fetchone()[0]


def worker(directory: str, scenario: str) -> None:
    root = Path(directory)
    sink = DemoSink(str(root / "provider.db"), fault="exit-after-effect")
    if scenario == "naive":
        sink.execute("example-refund", {"operation": "refund", "amount_minor": 1200})
    else:
        engine = CommitLatch(SQLiteLedger(str(root / "ledger.db")), lease_seconds=0.05)
        engine.run("demo", "refund/order-42/request-1", sink,
                   {"operation": "refund", "amount_minor": 1200})


def run_demo(directory=None):
    root = Path(directory).resolve() if directory else Path(tempfile.mkdtemp(prefix="commitlatch-"))
    if root.exists() and any(root.iterdir()):
        raise ValueError("Demo output directory must be empty; existing data will not be overwritten")
    root.mkdir(parents=True, exist_ok=True)
    results = []
    for scenario in ("naive", "reconciled", "opaque"):
        case_dir = root / scenario
        case_dir.mkdir()
        completed = subprocess.run(
            [sys.executable, "-m", "commitlatch", "_worker", str(case_dir), scenario],
            capture_output=True, text=True, timeout=20)
        if completed.returncode != 42:
            raise RuntimeError("Fault injection worker did not reach its crash point: " + completed.stderr)
        sink = DemoSink(str(case_dir / "provider.db"), observable=scenario != "opaque")
        if scenario == "naive":
            sink.execute("example-refund", {"operation": "refund", "amount_minor": 1200})
            results.append({"scenario": scenario, "state": "DUPLICATED", "effects": sink.count(),
                            "attempts": 2, "worker_exit": completed.returncode,
                            "events": [
                                {"kind": "EXTERNAL_EFFECT_COMMITTED", "detail": {"receipt": 1}},
                                {"kind": "WORKER_KILLED", "detail": {"exit": 42}},
                                {"kind": "BLIND_RETRY", "detail": {"receipt": 2}},
                            ]})
            continue
        ledger = SQLiteLedger(str(case_dir / "ledger.db"))
        engine = CommitLatch(ledger)
        action = ledger.get("demo", "refund/order-42/request-1")
        remaining = (action["lease_until"] or 0) - time.time()
        if remaining > 0:
            time.sleep(remaining + 0.01)
        action = engine.reconcile("demo", "refund/order-42/request-1", sink)
        # Re-submitting the exact operation must cache the result or block, not dispatch.
        try:
            engine.run("demo", "refund/order-42/request-1", sink,
                       {"operation": "refund", "amount_minor": 1200})
        except UnknownOutcome:
            pass
        results.append({"scenario": scenario, "state": action["state"], "effects": sink.count(),
                        "attempts": action["attempts"], "worker_exit": completed.returncode,
                        "events": ledger.events(action["id"])})
    expected = [("DUPLICATED", 2), ("SUCCEEDED", 1), ("UNKNOWN", 1)]
    if [(item["state"], item["effects"]) for item in results] != expected:
        raise RuntimeError("Demo invariant failed; refusing to generate a success report")
    data = {"version": "0.1.0a2", "test_only": True, "scenarios": results}
    (root / "results.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    from .report import render_demo
    (root / "report.html").write_text(render_demo(data), encoding="utf-8")
    return root, data
