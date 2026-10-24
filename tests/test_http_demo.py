import io
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError

from commitlatch.cli import main
from commitlatch.http_demo import DemoHTTPAdapter, HTTPFixture, run_http_demo


class HTTPRecoveryTests(unittest.TestCase):
    def test_dropped_http_response_has_four_distinct_recovery_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            root, data = run_http_demo(Path(directory) / "run")
            self.assertEqual([(c["state"], c["effects"], c["post_requests"], c["lookups"])
                              for c in data["scenarios"]],
                             [("DUPLICATED", 2, 2, 0), ("SUCCEEDED", 1, 2, 0),
                              ("SUCCEEDED", 1, 1, 1), ("UNKNOWN", 1, 1, 1)])
            self.assertEqual(data["scenarios"][1]["native_replays"], 1)
            self.assertEqual(json.loads((root / "results.json").read_text()), data)
            with self.assertRaises(ValueError):
                run_http_demo(root)

    def test_native_idempotency_rejects_changed_payload(self):
        with tempfile.TemporaryDirectory() as directory, HTTPFixture(Path(directory) / "provider.db") as provider:
            adapter = DemoHTTPAdapter(provider, native_idempotency=True)
            with self.assertRaises((HTTPException, URLError, OSError)):
                adapter.execute("same-key", {"amount_minor": 1200})
            with self.assertRaises(HTTPError) as error:
                adapter.execute("same-key", {"amount_minor": 2400})
            self.assertEqual(error.exception.code, 409)
            error.exception.close()
            self.assertEqual(provider.snapshot()["effects"], 1)

    def test_empty_http_lookup_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory, HTTPFixture(Path(directory) / "provider.db") as provider:
            outcome = DemoHTTPAdapter(provider).reconcile("missing", {})
            self.assertEqual(outcome.status, "UNKNOWN")
            self.assertEqual(provider.snapshot()["post_requests"], 0)

    def test_http_receipt_must_match_arguments(self):
        with tempfile.TemporaryDirectory() as directory, HTTPFixture(Path(directory) / "provider.db") as provider:
            adapter = DemoHTTPAdapter(provider)
            with self.assertRaises((HTTPException, URLError, OSError)):
                adapter.execute("request-1", {"amount_minor": 1200})
            self.assertEqual(adapter.reconcile("request-1", {"amount_minor": 2400}).status, "UNKNOWN")
            self.assertEqual(provider.snapshot()["effects"], 1)

    def test_concurrent_native_requests_share_one_effect(self):
        with tempfile.TemporaryDirectory() as directory, HTTPFixture(Path(directory) / "provider.db") as provider:
            adapter = DemoHTTPAdapter(provider, native_idempotency=True)

            def send(_):
                try:
                    return adapter.execute("same-key", {"operation": "test"})
                except (HTTPException, URLError, OSError):
                    return None

            with ThreadPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(send, range(6)))
            self.assertEqual(sum(result is None for result in results), 1)
            self.assertEqual({result["receipt"] for result in results if result}, {1})
            self.assertEqual(provider.snapshot()["effects"], 1)
            self.assertEqual(provider.snapshot()["native_replays"], 5)


class CLIHelpTests(unittest.TestCase):
    def test_help_hides_internal_worker(self):
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit):
            main(["--help"])
        self.assertIn("http-demo", output.getvalue())
        self.assertNotIn("_worker", output.getvalue())
        self.assertNotIn("==SUPPRESS==", output.getvalue())


if __name__ == "__main__":
    unittest.main()
