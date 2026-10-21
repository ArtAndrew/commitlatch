import argparse
import json
import sys
from pathlib import Path

from .engine import CommitLatch
from .ledger import SQLiteLedger
from .model import CommitLatchError


def main(argv=None):
    parser = argparse.ArgumentParser(description="Explicit recovery contracts for agent actions")
    parser.add_argument("--version", action="version", version="CommitLatch 0.1.0a1")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Run three real process-crash scenarios with test data")
    demo.add_argument("--directory", help="New or empty output directory")
    for name in ("inspect", "replay", "reconcile-demo"):
        command = commands.add_parser(name, help={
            "inspect": "Inspect one action", "replay": "Print recorded events; never execute an action",
            "reconcile-demo": "Reconcile a test-sink operation (test adapter only)"}[name])
        command.add_argument("--db", required=True)
        command.add_argument("--namespace", default="demo")
        command.add_argument("--key", default="refund/order-42/request-1")
        if name == "reconcile-demo":
            command.add_argument("--provider-db", required=True)
            command.add_argument("--opaque", action="store_true")
    internal = commands.add_parser("_worker", help=argparse.SUPPRESS)
    internal.add_argument("directory")
    internal.add_argument("scenario", choices=("naive", "reconciled", "opaque"))
    args = parser.parse_args(argv)
    try:
        if args.command == "_worker":
            from .demo import worker
            worker(args.directory, args.scenario)
            return 0
        if args.command == "demo":
            from .demo import run_demo
            root, data = run_demo(args.directory)
            for case in data["scenarios"]:
                print("%-12s %-11s effects=%d attempts=%d" % (
                    case["scenario"], case["state"], case["effects"], case["attempts"]))
            print("Report: " + str(root / "report.html"))
            print("Data:   " + str(root / "results.json"))
            return 0
        if not Path(args.db).is_file():
            raise ValueError("Ledger does not exist")
        ledger = SQLiteLedger(args.db, read_only=args.command != "reconcile-demo")
        if args.command == "reconcile-demo":
            if not Path(args.provider_db).is_file():
                raise ValueError("Test provider database does not exist")
            from .demo import DemoSink
            action = CommitLatch(ledger).reconcile(
                args.namespace, args.key, DemoSink(args.provider_db, observable=not args.opaque))
            print(json.dumps(action, indent=2))
            return 2 if action["state"] == "UNKNOWN" else 0
        action = ledger.get(args.namespace, args.key)
        value = ledger.events(action["id"]) if args.command == "replay" else action
        if args.command == "replay":
            print("Recorded events only; no external calls or workflow resumption.", file=sys.stderr)
        print(json.dumps(value, indent=2))
        return 0
    except (CommitLatchError, ValueError, KeyError) as error:
        print(type(error).__name__ + ": " + str(error), file=sys.stderr)
        return 2
