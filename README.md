# CommitLatch

[![tests](https://github.com/ArtAndrew/commitlatch/actions/workflows/tests.yml/badge.svg)](https://github.com/ArtAndrew/commitlatch/actions/workflows/tests.yml)

**Recover the result. Don't blindly repeat the action.**

CommitLatch is a Python library for uncertain external actions. It records a
business operation before dispatch, preserves completed results, asks an adapter
to reconcile a lost response, and blocks retries when the outcome is unknown.

**Status: experimental alpha, 0.1.0a1.** This release has a SQLite ledger and a local test
service. PostgreSQL, Stripe, Temporal integration and managed hosting are roadmap
items, not shipped capabilities. No production reliability or universal
exactly-once guarantee is claimed.

[Русское описание](README.ru.md) · [Guarantees](docs/GUARANTEES.md) ·
[Adapter contract](docs/ADAPTERS.md) · [Roadmap](docs/ROADMAP.md) ·
[Validation](docs/VALIDATION.md)

## What ships today

- A zero-runtime-dependency Python SDK with a durable SQLite action ledger.
- Stable business keys bound to immutable operation arguments and adapter identity.
- Cached results, receipt reconciliation and explicit `UNKNOWN` outcomes.
- Atomic local claims and rejection of stale workers' ledger updates.
- A CLI, a real process-crash demo and an offline HTML report.
- 22 local tests covering recovery, concurrency and unsafe retry conditions.

Built for developers wiring agents to tools with external side effects. Start
with the adapter contract before using it with a real service. The included
adapter is a test sink; no payment integration ships in this alpha.

## The failure

Your agent requests a refund. The service commits it. The worker dies before
recording the response. Retrying the request may apply a second refund.

Saving the request alone does not tell you whether the external effect happened.
CommitLatch makes that ambiguity explicit instead of silently retrying it.

## Run the crash demo

Clone the repository, then run with Python 3.9 or newer. After cloning, the demo
needs no API keys, Docker, third-party dependencies or network access:

```sh
git clone https://github.com/ArtAndrew/commitlatch.git
cd commitlatch
PYTHONPATH=src python3 -m commitlatch demo --directory demo-output
```

Use an empty/new directory. The command refuses to overwrite an existing run.
Open `demo-output/report.html` for the offline report, or `results.json` for the
machine-readable results. The report and command-line interface are in English.

```text
naive        DUPLICATED  effects=2 attempts=2
reconciled   SUCCEEDED   effects=1 attempts=1
opaque       UNKNOWN     effects=1 attempts=1
```

These are measured outcomes of the bundled deterministic fixture, not production
statistics. Each scenario kills a real child process with `os._exit(42)` after
the test service commits an effect to its own database. The service intentionally
does NOT deduplicate requests. In the opaque case, the demo's observer can count
effects, but the adapter cannot query them and therefore cannot claim success.

The naive baseline demonstrates one bug. It is not a performance or reliability
comparison against correctly configured Temporal, Restate or DBOS.

## Use the library

```python
from commitlatch import CommitLatch, SQLiteLedger, UnknownOutcome

engine = CommitLatch(SQLiteLedger("actions.db"))
# adapter is your implementation of execute() and reconcile().
try:
    result = engine.run(
        namespace="shop-account-1",
        key="order-42/refund-request-1",
        adapter=adapter,
        arguments={"operation": "refund", "amount_minor": 1200},
    )
except UnknownOutcome:
    action = engine.reconcile("shop-account-1", "order-42/refund-request-1", adapter)
    # action["state"] can still be UNKNOWN. Do not treat it as success.
```

For a complete executable example with the test adapter:

```sh
PYTHONPATH=src python3 examples/quickstart.py
```

Use the same namespace, business key, arguments and adapter identity on every
retry of one authorized operation. A separate legitimate operation needs a new
business key. The model must not invent replacement keys to evade this boundary.

When an operation has succeeded, repeating `run()` returns its recorded result
without calling the adapter. Changing the payload or adapter for an existing key
raises `ActionConflict`. When the outcome is unknown, `run()` blocks; only
`reconcile()` performs a lookup. It never automatically calls `execute()`.

Only an adapter-certified non-execution can become `FAILED` and be explicitly
reset using `retry_failed()`. Timeouts and missing search results are not such
proof. This conservative alpha intentionally sacrifices automatic progress
when the provider cannot establish the outcome.

## Inspect and replay

```sh
PYTHONPATH=src python3 -m commitlatch inspect --db demo-output/reconciled/ledger.db
PYTHONPATH=src python3 -m commitlatch replay --db demo-output/reconciled/ledger.db
PYTHONPATH=src python3 -m commitlatch reconcile-demo \
  --db demo-output/opaque/ledger.db \
  --provider-db demo-output/opaque/provider.db --opaque
```

`replay` is read-only event playback. It does not replay arbitrary Python code,
resume an agent, invoke a model or call an external service. `reconcile-demo` is
only for the bundled test adapter, and exits with code 2 if the outcome remains
unknown. Adapter exceptions also fail closed to `UNKNOWN`.

## Install locally

To install the CLI into an isolated environment from this checkout:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/commitlatch demo
```

Installation may fetch build tools; the library itself has zero third-party
runtime dependencies. This alpha is installed from source; there is no published
PyPI release.

## Test

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The suite exercises actual subprocess crashes, independent process contention,
late-worker fencing, payload conflicts, uncertain results, explicit safe retry,
read-only playback and unsafe receipt handling. GitHub Actions runs the suite and
installation checks on Linux/macOS with Python 3.9/3.11/3.13. See the linked
[workflow runs](https://github.com/ArtAndrew/commitlatch/actions/workflows/tests.yml)
for their current status.

## Scope and trust boundary

- SQLite is for one host with local storage, not a distributed/NFS ledger.
- All competing callers for one business operation must share its ledger/key.
- Local leases fence database updates, not already-dispatched external requests.
- Direct calls outside this library, new business keys, deleted ledgers and
  restored stale backups can bypass its protection.
- A successful receipt proves what the adapter verifies. It does not prove
  the action was authorized or appropriate, or that its outcome is irreversible.
- Arguments and results are stored in plaintext. Do not pass credentials or
  sensitive production data into this alpha. Namespace separation is naming,
  not an authentication or tenant-security mechanism.
- The test service uses a separate SQLite transaction to model the commit gap.
  Real network/provider semantics have not yet been tested.

## Contribute

Start with a reproducible failure case and a test. Adapter contributions must
document identity scope, receipt semantics, lookup consistency, in-flight
requests and any idempotency retention window. Do not add blind automatic retry.
See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
