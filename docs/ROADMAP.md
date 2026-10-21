# Delivery roadmap

## Completed: local alpha 0.1.0a1

- Python SDK, SQLite ledger, immutable business-key binding.
- Explicit UNKNOWN, proof-based FAILED, completed-result reuse.
- Atomic claims and fencing of late local writes.
- Real child-process crash fixture with an independent test sink.
- CLI inspection, reconciliation and event playback.
- Offline report and local test suite.
- Installable package metadata and prepared GitHub Actions workflow.

This milestone is a tested vertical slice, not the full 4–6 week MVP.

## Next: first real integration

1. Separate the ledger interface from SQLite-specific implementation details.
2. Implement a PostgreSQL backend with atomic claims, ownership checks and
   conformance tests running against real PostgreSQL. Add Docker Compose.
3. Add one narrowly scoped Stripe sandbox action and receipt verifier.
   Verify native idempotency retention, parameter binding and provider states
   against current official documentation. Test only in sandbox.
4. Run lost-response and delayed-response experiments through a real HTTP fault
   proxy. The local independent-database fixture does not replace these tests.
5. Add one Temporal example with a single retry owner. Generic workflow retries
   must preserve the business key and cannot bypass UNKNOWN handling.

Acceptance: reproducible restart recovery and explicit unresolved outcomes with
the same documented semantics on both backends. No claim of multi-region safety.

## Following: pilot readiness

- Durable human resolution bound to evidence and accountable identity.
  Do not implement a generic "mark successful" or "force retry" button.
- Adapter-specific authority expiry and approval binding.
- Payload redaction/encryption and authenticated operational access.
- Heartbeats, bounded reconciliation scheduling and operational metrics.
- Compare integration effort and incident handling with correctly configured
  Temporal/Restate/DBOS. Publish raw methodology and results.

## Commercial validation

Recruit three teams with real uncertain-outcome incidents in one repeated
workflow. Measure integration days, unresolved cases, duplicate business effects,
and ongoing support effort. Seek paid pilots before building a managed cloud.

Stop expanding the platform if each integration is bespoke consulting or teams
can obtain the same result cheaply using their existing runtime.

## Publication readiness

- Repository: https://github.com/ArtAndrew/commitlatch. Verify PyPI name availability before publishing a package.
- Run the prepared remote CI matrix and add package installation tests.
- Confirm README claims match actual adapters and deployment support.
- Enable a private security-reporting route before public pilot recruitment.
- Tag an experimental prerelease after checking the uploaded source and CI. No PyPI package has been published.
