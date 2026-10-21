# CommitLatch 0.1.0a1 — first experimental alpha

**Recover the result. Don't blindly repeat the action.**

An agent calls an external service. The service commits the action. The worker
dies before recording the response. A blind retry can apply the action twice.

CommitLatch records the operation before dispatch and makes uncertain outcomes
explicit. A matching receipt can recover the result. If the provider cannot
establish the outcome, the operation stays UNKNOWN and another dispatch is blocked.

## Included

- Python SDK with no third-party runtime dependencies.
- SQLite action ledger and immutable business-key binding.
- Completed-result reuse and adapter-based receipt reconciliation.
- Atomic local claims and fencing of stale ledger updates.
- Inspection and read-only event playback through the CLI.
- A real child-process crash demo with an English offline HTML report.
- 22 locally passing tests, including independent-process contention.

## Try it from the repository

```sh
PYTHONPATH=src python3 -m commitlatch demo --directory demo-output
```

The bundled fixture produces two effects with blind retry, one confirmed effect
with reconciliation, and one unresolved effect with a blocked retry when lookup
is unavailable. These are local test outcomes, not production reliability claims.

## Current limits

This is an experimental, single-host alpha. It includes a synthetic test adapter,
not a real payment integration. PostgreSQL, Stripe sandbox, network-fault testing
and a Temporal example are next. No universal exactly-once guarantee is offered.

The source is licensed under Apache-2.0. No PyPI package has been published.
