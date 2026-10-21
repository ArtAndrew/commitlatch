import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from commitlatch import (ActionBusy, ActionConflict, ActionFailed, CommitLatch,
                         InvalidState, OwnershipLost, Reconciliation,
                         SQLiteLedger, UnknownOutcome)
from commitlatch.demo import DemoSink, run_demo
from commitlatch.report import render_demo


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.ledger = SQLiteLedger(str(self.root / "ledger.db"))
        self.now = 1000.0
        self.engine = CommitLatch(self.ledger, lease_seconds=10, clock=lambda: self.now)
        self.sink = DemoSink(str(self.root / "provider.db"))
        self.args = {"operation": "refund", "amount_minor": 1200}

    def run_action(self, sink=None, args=None, key="refund-1", namespace="shop"):
        return self.engine.run(namespace, key, sink or self.sink,
                               self.args if args is None else args)

    def test_repeated_business_key_returns_recorded_result_without_new_effect(self):
        receipt = self.run_action()
        restarted = CommitLatch(SQLiteLedger(self.ledger.path))
        self.assertEqual(restarted.run("shop", "refund-1", self.sink, self.args), receipt)
        self.assertEqual(self.sink.count(), 1)

    def test_changed_payload_rejected_before_external_call(self):
        self.run_action()
        with self.assertRaises(ActionConflict):
            self.run_action(args={"operation": "refund", "amount_minor": 2400})
        self.assertEqual(self.sink.count(), 1)

    def test_same_key_in_different_namespaces_is_a_distinct_operation(self):
        self.run_action(namespace="shop-a")
        self.run_action(namespace="shop-b")
        self.assertEqual(self.sink.count(), 2)

    def test_different_provider_cannot_reuse_or_reconcile_an_operation(self):
        self.sink.fault = "raise-after-effect"
        with self.assertRaises(UnknownOutcome):
            self.run_action()
        other = DemoSink(str(self.root / "other.db"))
        with self.assertRaises(ActionConflict):
            self.run_action(sink=other)
        with self.assertRaises(ActionConflict):
            self.engine.reconcile("shop", "refund-1", other)
        self.assertEqual(other.count(), 0)

    def test_lost_response_is_reconciled_without_dispatch(self):
        self.sink.fault = "raise-after-effect"
        with self.assertRaises(UnknownOutcome):
            self.run_action()
        with self.assertRaises(UnknownOutcome):
            self.run_action()
        action = self.engine.reconcile("shop", "refund-1", self.sink)
        self.assertEqual(action["state"], "SUCCEEDED")
        self.assertEqual(action["attempts"], 1)
        self.assertEqual(self.run_action(), action["result"])
        self.assertEqual(self.sink.count(), 1)

    def test_opaque_result_stays_unknown_and_retry_is_blocked(self):
        self.sink.observable = False
        self.sink.fault = "raise-after-effect"
        with self.assertRaises(UnknownOutcome):
            self.run_action()
        for _ in range(3):
            self.assertEqual(self.engine.reconcile("shop", "refund-1", self.sink)["state"], "UNKNOWN")
            with self.assertRaises(UnknownOutcome):
                self.run_action()
        with self.assertRaises(InvalidState):
            self.engine.retry_failed("shop", "refund-1")
        self.assertEqual(self.sink.count(), 1)

    def test_missing_receipt_does_not_authorize_retry(self):
        self.sink.fault = "raise-before-effect"
        with self.assertRaises(UnknownOutcome):
            self.run_action()
        action = self.engine.reconcile("shop", "refund-1", self.sink)
        self.assertEqual(action["state"], "UNKNOWN")
        with self.assertRaises(InvalidState):
            self.engine.retry_failed("shop", "refund-1")
        self.assertEqual(self.sink.count(), 0)

    def test_only_proven_nonexecution_can_be_retried(self):
        self.sink.fault = "reject-before-effect"
        with self.assertRaises(ActionFailed):
            self.run_action()
        with self.assertRaises(ActionFailed):
            self.run_action()
        self.assertEqual(self.sink.count(), 0)
        self.engine.retry_failed("shop", "refund-1")
        self.sink.fault = "none"
        self.run_action()
        self.assertEqual(self.sink.count(), 1)
        self.assertEqual(self.ledger.get("shop", "refund-1")["attempts"], 2)

    def test_live_claim_blocks_other_workers_and_reconciliation(self):
        entered, release = threading.Event(), threading.Event()
        sink = self.sink

        class WaitingAdapter:
            name = sink.name

            def execute(self, key, arguments):
                entered.set()
                if not release.wait(5):
                    raise TimeoutError()
                return sink.execute(key, arguments)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.run_action, WaitingAdapter())
            self.assertTrue(entered.wait(5))
            try:
                with self.assertRaises(ActionBusy):
                    self.run_action()
                with self.assertRaises(ActionBusy):
                    self.engine.reconcile("shop", "refund-1", self.sink)
            finally:
                release.set()
            future.result(5)
        self.assertEqual(self.sink.count(), 1)

    def test_expired_worker_is_fenced_but_its_external_request_cannot_be_cancelled(self):
        entered, release = threading.Event(), threading.Event()
        sink = self.sink

        class DelayedAdapter:
            name = sink.name

            def execute(self, key, arguments):
                entered.set()
                if not release.wait(5):
                    raise TimeoutError()
                return sink.execute(key, arguments)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.run_action, DelayedAdapter())
            self.assertTrue(entered.wait(5))
            try:
                self.now += 11
                recovered = self.engine.reconcile("shop", "refund-1", sink)
                self.assertEqual(recovered["state"], "UNKNOWN")
                with self.assertRaises(UnknownOutcome):
                    self.run_action()
            finally:
                release.set()
            with self.assertRaises(OwnershipLost):
                future.result(5)
        self.assertEqual(self.ledger.get("shop", "refund-1")["state"], "UNKNOWN")
        self.assertEqual(sink.count(), 1)
        self.assertEqual(self.engine.reconcile("shop", "refund-1", sink)["state"], "SUCCEEDED")

    def test_multiple_receipts_cannot_be_misreported_as_one_success(self):
        self.sink.fault = "raise-after-effect"
        with self.assertRaises(UnknownOutcome):
            self.run_action()
        action = self.ledger.get("shop", "refund-1")
        self.sink.fault = "none"
        self.sink.execute(action["id"], self.args)  # A bypass outside the SDK.
        self.assertEqual(self.engine.reconcile("shop", "refund-1", self.sink)["state"], "UNKNOWN")
        self.assertEqual(self.sink.count(), 2)

    def test_reconciliation_does_not_trust_mismatched_receipt_arguments(self):
        self.sink.fault = "raise-after-effect"
        with self.assertRaises(UnknownOutcome):
            self.run_action()
        with sqlite3.connect(self.sink.path) as db:
            db.execute("UPDATE effects SET arguments='{}'")
        self.assertEqual(self.engine.reconcile("shop", "refund-1", self.sink)["state"], "UNKNOWN")

    def test_invalid_json_is_rejected_before_registration(self):
        for arguments in ({"amount": float("nan")}, {1: "bad-key"}, {"tuple": (1, 2)}, []):
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    self.run_action(args=arguments)
        self.assertEqual(self.ledger.list_actions(), [])
        self.assertEqual(self.sink.count(), 0)

    def test_invalid_result_is_unknown_not_permission_to_repeat(self):
        sink = self.sink

        class BadResult:
            name = sink.name

            def execute(self, key, arguments):
                sink.execute(key, arguments)
                return object()

        with self.assertRaises(UnknownOutcome):
            self.run_action(sink=BadResult())
        self.assertEqual(self.sink.count(), 1)
        self.assertEqual(self.engine.reconcile("shop", "refund-1", sink)["state"], "SUCCEEDED")

    def test_malformed_reconciliation_fails_closed(self):
        sink = self.sink
        self.sink.fault = "raise-after-effect"
        with self.assertRaises(UnknownOutcome):
            self.run_action()

        class BadReconciliation:
            name = sink.name

            def reconcile(self, key, arguments):
                return Reconciliation("SUCCEEDED", {"ok": True}, None)

        self.assertEqual(self.engine.reconcile("shop", "refund-1", BadReconciliation())["state"], "UNKNOWN")

    def test_exception_messages_are_not_persisted(self):
        sink = self.sink

        class SecretError:
            name = sink.name

            def execute(self, key, arguments):
                raise RuntimeError("Authorization: secret-123")

        with self.assertRaises(UnknownOutcome):
            self.run_action(sink=SecretError())
        action = self.ledger.get("shop", "refund-1")
        self.assertNotIn("secret-123", json.dumps(self.ledger.events(action["id"])))
        self.assertNotIn("secret-123", json.dumps(action))

    def test_none_result_is_a_valid_cached_success(self):
        sink = self.sink

        class NoneResult:
            name = sink.name

            def execute(self, key, arguments):
                sink.execute(key, arguments)
                return None

        self.assertIsNone(self.run_action(sink=NoneResult()))
        self.assertIsNone(self.run_action(sink=NoneResult()))
        self.assertEqual(sink.count(), 1)

    def test_read_only_ledger_rejects_writes(self):
        self.run_action()
        reader = SQLiteLedger(self.ledger.path, read_only=True)
        self.assertEqual(reader.get("shop", "refund-1")["state"], "SUCCEEDED")
        with self.assertRaises(sqlite3.OperationalError):
            reader.prepare("shop", "other", self.sink.name, {}, self.now)

    def test_cli_replay_never_changes_effects_or_events(self):
        self.run_action()
        action = self.ledger.get("shop", "refund-1")
        before = self.ledger.events(action["id"])
        completed = subprocess.run([sys.executable, "-m", "commitlatch", "replay", "--db",
                                    self.ledger.path, "--namespace", "shop", "--key", "refund-1"],
                                   capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), before)
        self.assertEqual(self.ledger.events(action["id"]), before)
        self.assertEqual(self.sink.count(), 1)

    def test_multiprocess_same_key_has_one_external_effect(self):
        script = '''
import sys, time
from commitlatch import CommitLatch, SQLiteLedger, ActionBusy
from commitlatch.demo import DemoSink
class SlowSink(DemoSink):
    def execute(self, key, arguments):
        time.sleep(0.1)
        return super().execute(key, arguments)
engine = CommitLatch(SQLiteLedger(sys.argv[1]))
try:
    engine.run("race", "same-key", SlowSink(sys.argv[2]), {"operation": "test"})
except ActionBusy:
    pass
'''
        workers = [subprocess.Popen([sys.executable, "-c", script, self.ledger.path, self.sink.path],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                   for _ in range(6)]
        for process in workers:
            _, errors = process.communicate(timeout=15)
            self.assertEqual(process.returncode, 0, errors)
        self.assertEqual(self.sink.count(), 1)

    def test_real_process_crashes_produce_expected_evidence(self):
        output, data = run_demo(str(self.root / "demo"))
        cases = data["scenarios"]
        self.assertEqual([(x["state"], x["effects"]) for x in cases],
                         [("DUPLICATED", 2), ("SUCCEEDED", 1), ("UNKNOWN", 1)])
        self.assertEqual([x["worker_exit"] for x in cases], [42, 42, 42])
        self.assertTrue((output / "report.html").is_file())
        with self.assertRaises(ValueError):
            run_demo(str(output))

    def test_report_escapes_untrusted_event_content(self):
        data = {"scenarios": [{"scenario": "opaque", "state": "UNKNOWN", "effects": 1,
                              "attempts": 1, "worker_exit": 42,
                              "events": [{"kind": "<script>alert(1)</script>", "detail": {}}]}]}
        report = render_demo(data)
        self.assertNotIn("<script>", report)
        self.assertIn("&lt;script&gt;", report)


if __name__ == "__main__":
    unittest.main()
