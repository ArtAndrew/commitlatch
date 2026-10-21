"""Loopback HTTP fault fixture, not a production provider adapter.

The server commits to an independent database, then closes the TCP connection
without sending a response. Native idempotency is included as a fair baseline.
"""

import json
import socket
import sqlite3
import tempfile
import threading
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from http.client import HTTPException

from .engine import CommitLatch
from .ledger import SQLiteLedger
from .model import Reconciliation, UnknownOutcome, canonical


class HTTPFixture:
    """Synthetic provider. Binds only to loopback; no authentication or payments."""

    def __init__(self, path, observable=True):
        self.path = str(path)
        self.observable = observable
        self.identity = "loopback-fixture/v1:" + uuid.uuid4().hex
        self.lock = threading.Lock()
        self.posts = self.lookups = self.replays = 0
        self.dropped = set()
        with self.db() as db:
            db.executescript("""
                CREATE TABLE effects(receipt INTEGER PRIMARY KEY, effect_key TEXT, arguments TEXT);
                CREATE TABLE native_keys(key TEXT PRIMARY KEY, arguments TEXT, result TEXT);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    def snapshot(self):
        with self.lock, self.db() as db:
            return {"effects": db.execute("SELECT COUNT(*) FROM effects").fetchone()[0],
                    "post_requests": self.posts, "lookups": self.lookups,
                    "native_replays": self.replays}

    def __enter__(self):
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, code, value):
                content = canonical(value).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def do_POST(self):
                if self.path != "/operations":
                    self.reply(404, {"error": "unknown endpoint"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 65536:
                        raise ValueError("invalid body size")
                    body = json.loads(self.rfile.read(length))
                    key, arguments = body["effect_key"], body["arguments"]
                    if not isinstance(key, str) or not key or not isinstance(arguments, dict):
                        raise ValueError("invalid payload")
                    encoded = canonical(arguments)
                except (ValueError, TypeError, KeyError):
                    self.reply(400, {"error": "invalid payload"})
                    return
                native_key = self.headers.get("Idempotency-Key")
                code = 200
                with fixture.lock:
                    fixture.posts += 1
                    with fixture.db() as db:
                        saved = db.execute("SELECT arguments,result FROM native_keys WHERE key=?",
                                           (native_key,)).fetchone() if native_key else None
                        if saved:
                            if saved[0] != encoded:
                                code, result = 409, {"error": "idempotency payload conflict"}
                            else:
                                fixture.replays += 1
                                result = json.loads(saved[1])
                        else:
                            cursor = db.execute("INSERT INTO effects(effect_key,arguments) VALUES(?,?)",
                                                (key, encoded))
                            result = {"receipt": cursor.lastrowid,
                                      "operation": arguments.get("operation", "test")}
                            if native_key:
                                db.execute("INSERT INTO native_keys VALUES(?,?,?)",
                                           (native_key, encoded, canonical(result)))
                    drop = (code == 200 and self.headers.get("X-Demo-Drop-Response") == "once"
                            and key not in fixture.dropped)
                    if drop:
                        fixture.dropped.add(key)
                if drop:
                    # Independent provider transaction has committed. No status line or body.
                    self.close_connection = True
                    try:
                        self.connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    self.connection.close()
                    return
                self.reply(code, result)

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path != "/receipts":
                    self.reply(404, {"error": "unknown endpoint"})
                    return
                key = parse_qs(parsed.query).get("effect_key", [""])[0]
                with fixture.lock:
                    fixture.lookups += 1
                    if fixture.observable:
                        with fixture.db() as db:
                            rows = db.execute("SELECT receipt,arguments FROM effects WHERE effect_key=?",
                                              (key,)).fetchall()
                    else:
                        rows = []
                if not fixture.observable:
                    self.reply(503, {"error": "receipt lookup unavailable"})
                    return
                self.reply(200, {"receipts": [
                    {"receipt": receipt, "effect_key": key, "arguments": json.loads(arguments)}
                    for receipt, arguments in rows]})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = "http://127.0.0.1:%d" % self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class DemoHTTPAdapter:
    """Trusted fixture client. No implicit mutation retries; loopback HTTP only."""

    def __init__(self, provider, native_idempotency=False):
        self.url = provider.url
        self.name = provider.identity
        self.native_idempotency = native_idempotency

    def execute(self, effect_key, arguments):
        headers = {"Content-Type": "application/json", "X-Demo-Drop-Response": "once"}
        if self.native_idempotency:
            headers["Idempotency-Key"] = effect_key
        request = Request(self.url + "/operations", method="POST", headers=headers,
                          data=canonical({"effect_key": effect_key,
                                          "arguments": arguments}).encode())
        with urlopen(request, timeout=3) as response:
            return json.load(response)

    def reconcile(self, effect_key, arguments):
        try:
            with urlopen(self.url + "/receipts?" + urlencode({"effect_key": effect_key}),
                         timeout=3) as response:
                rows = json.load(response)["receipts"]
        except (HTTPError, URLError, HTTPException, OSError, ValueError, KeyError):
            return Reconciliation.unknown("HTTP receipt lookup unavailable or invalid")
        if not isinstance(rows, list) or len(rows) != 1:
            return Reconciliation.unknown("Lookup did not return exactly one receipt")
        row = rows[0]
        if (not isinstance(row, dict) or row.get("effect_key") != effect_key
                or canonical(row.get("arguments")) != canonical(arguments)
                or type(row.get("receipt")) is not int or row["receipt"] <= 0):
            return Reconciliation.unknown("Receipt does not match the original operation")
        return Reconciliation.succeeded(
            {"receipt": row["receipt"], "operation": arguments.get("operation", "test")},
            "Loopback provider receipt #%d over HTTP" % row["receipt"])


def run_http_demo(directory=None):
    root = Path(directory).resolve() if directory else Path(tempfile.mkdtemp(prefix="commitlatch-http-"))
    if root.exists() and any(root.iterdir()):
        raise ValueError("HTTP demo directory must be new or empty")
    root.mkdir(parents=True, exist_ok=True)
    cases = []
    arguments = {"operation": "refund", "amount_minor": 1200}
    for scenario in ("blind_retry", "native_idempotency", "reconciled", "opaque"):
        with HTTPFixture(root / (scenario + "-provider.db"), observable=scenario != "opaque") as provider:
            adapter = DemoHTTPAdapter(provider, native_idempotency=scenario == "native_idempotency")
            if scenario in ("blind_retry", "native_idempotency"):
                try:
                    adapter.execute("refund-request-1", arguments)
                except (HTTPException, URLError, OSError):
                    pass
                else:
                    raise RuntimeError("The response-loss fault was not reached")
                adapter.execute("refund-request-1", arguments)
                state = "DUPLICATED" if scenario == "blind_retry" else "SUCCEEDED"
            else:
                path = root / (scenario + "-ledger.db")
                engine = CommitLatch(SQLiteLedger(str(path)))
                try:
                    engine.run("demo", "refund-request-1", adapter, arguments)
                except UnknownOutcome:
                    pass
                else:
                    raise RuntimeError("The response-loss fault was not reached")
                # Recreate the engine from the ledger while the provider remains alive.
                engine = CommitLatch(SQLiteLedger(str(path)))
                action = engine.reconcile("demo", "refund-request-1", adapter)
                state = action["state"]
                try:
                    engine.run("demo", "refund-request-1", adapter, arguments)
                except UnknownOutcome:
                    if scenario != "opaque":
                        raise
            cases.append(dict(scenario=scenario, state=state, **provider.snapshot()))
    expected = [("DUPLICATED", 2, 2), ("SUCCEEDED", 1, 2),
                ("SUCCEEDED", 1, 1), ("UNKNOWN", 1, 1)]
    if [(c["state"], c["effects"], c["post_requests"]) for c in cases] != expected:
        raise RuntimeError("HTTP demo invariant failed")
    data = {"test_only": True, "transport": "loopback HTTP over TCP", "scenarios": cases}
    (root / "results.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf8")
    return root, data
