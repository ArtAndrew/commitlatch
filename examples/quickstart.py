"""Run with PYTHONPATH=src python3 examples/quickstart.py from the repo root."""
import tempfile
from pathlib import Path

from commitlatch import CommitLatch, SQLiteLedger, UnknownOutcome
from commitlatch.demo import DemoSink

with tempfile.TemporaryDirectory(prefix="commitlatch-example-") as directory:
    root = Path(directory)
    engine = CommitLatch(SQLiteLedger(str(root / "ledger.db")))
    adapter = DemoSink(str(root / "service.db"), fault="raise-after-effect")
    args = {"operation": "refund", "amount_minor": 1200}
    try:
        engine.run("shop", "order-42/refund-request-1", adapter, args)
    except UnknownOutcome:
        print("Response lost. No automatic retry.")
    recovered = engine.reconcile("shop", "order-42/refund-request-1", adapter)
    print("Recovered:", recovered["state"], recovered["result"])
    print("External effects:", adapter.count())
    print("Same key returns the receipt:",
          engine.run("shop", "order-42/refund-request-1", adapter, args))
