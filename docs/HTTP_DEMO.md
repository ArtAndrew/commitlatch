# The response vanished. Did the operation happen?

Run from the repository with Python 3.9+:

```sh
PYTHONPATH=src python3 -m commitlatch http-demo --directory http-output
```

The directory must be new or empty. No API keys or packages are needed. The
fixture temporarily binds a server to `127.0.0.1` on an ephemeral port, then
shuts it down. A sandbox that disallows listening sockets must allow this local
test explicitly. No public port is opened.

## Fault and observation

1. A client sends `POST /operations` over a real TCP connection.
2. The synthetic provider commits its effect to its own SQLite database.
3. The provider closes the connection without sending an HTTP response.
4. The client either blindly retries, repeats a native idempotent request,
   reconciles the recorded intent, or preserves an UNKNOWN result.

The observer reads the provider database to count effects. The recovery adapter
can only use the provider's HTTP receipt endpoint. In the opaque scenario that
endpoint returns 503, even though the observer can count the committed effect.

| Strategy | Effects | POST requests | Receipt lookups | Outcome |
| --- | ---: | ---: | ---: | --- |
| Blind retry, non-idempotent endpoint | 2 | 2 | 0 | Duplicate |
| Same native idempotency key | 1 | 2 | 0 | Success |
| CommitLatch + matching receipt | 1 | 1 | 1 | Success |
| CommitLatch + unavailable lookup | 1 | 1 | 1 | UNKNOWN; no new dispatch |

`results.json` records the measured counts. The command checks all four outcomes
before writing the evidence. It recreates the CommitLatch engine from disk before
reconciliation; it does not claim to restart an entire agent or remote provider.

## The native-idempotency baseline matters

The fixture's native key lookup, parameter validation and effect commit happen
in one provider transaction. Reusing a key with different arguments returns 409.
The fixture retains native keys for its lifetime; it does not simulate retention
expiry, asynchronous settlement or a real provider's contract. Native idempotency
already solves duplicate execution under that contract. Keep using it.

CommitLatch adds a shared local record, immutable business identity, cached
results and an explicit boundary for unresolved outcomes. It does not make a
non-idempotent provider universally safe, infer user authorization, or replace
native provider guarantees.

## Boundaries

This is a synthetic loopback integration test. Client and server run in the same
process, communicate through sockets and use separate databases. It is not a
production benchmark, a Stripe test, a network fault proxy, or a proof against
all distributed failures. The separate `demo` command covers actual child-process
termination. Delayed remote completion and provider-specific retention remain
future integration work.

The animation in the README is a paced rendering of recorded JSON results, not
a real-time terminal recording or a latency comparison. Its final frame is also
available as `assets/recovery-results.png`. Regenerate it with `tools/render_assets.py`.
