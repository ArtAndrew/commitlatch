# Writing an adapter

An adapter is trusted code. The engine cannot independently validate that a
claimed provider receipt is authentic or that a non-execution assertion is true.
It controls dispatch and records the adapter's evidence, not the provider itself.

```python
from commitlatch import Reconciliation

class ExampleAdapter:
    name = "example/v1:provider-account-id"

    def execute(self, effect_key, arguments):
        # Submit one bounded operation with the durable correlation key.
        # Use native provider idempotency when its contract permits it.
        # Return strict JSON representing a confirmed success.
        raise NotImplementedError

    def reconcile(self, effect_key, arguments):
        # Read a provider receipt and validate its scope and exact parameters.
        # If the operation cannot be established, keep the uncertainty explicit.
        return Reconciliation.unknown("No authoritative receipt available")
```

Requirements:

1. Include provider account, action kind when needed, and contract version in
   `name`. A wrong provider/account must not be used to resolve an old action.
2. Do not hide mutating SDK retries inside execute unless the provider's
   documented idempotency contract makes them safe. This alpha cannot inspect
   internal adapter retries or direct calls outside the library.
3. Return `Reconciliation.succeeded(result, evidence)` only for a matching,
   authoritative result. A pending operation is not a success receipt.
4. Return UNKNOWN for missing/eventually consistent search results, lookup
   failure, multiple receipts, or mismatched parameters.
5. Raise `DefinitelyNotApplied` only when no effect occurred AND no dispatched
   attempt can apply later. The same requirement applies to
   `Reconciliation.not_applied(evidence)`.
6. Reconciliation must not make a new business mutation. A lookup that creates
   a resource on miss is not a read-only reconciliation mechanism.
7. Use bounded timeouts. Keep credentials in adapter configuration, not operation
   arguments. Error class names are recorded; raw exception messages are omitted.
8. Arguments/results must be strict JSON. Non-string map keys, tuples, bytes,
   NaN and infinity are rejected.

The SDK uses its stored argument snapshot to avoid a caller mutating parameters
after registration. Input order is normalized. A successful result can be null.

## Minimum conformance tests

- Confirmed success, repeat with same key, different payload conflict.
- Crash before dispatch and after provider commit but before local completion.
- Timeout before a receipt is known; delayed completion of the original request.
- Wrong provider/account, mismatched receipt arguments, multiple matches.
- Concurrent callers and expired workers returning late.
- Provider idempotency retention expiry, when applicable.
- Provider read consistency and pending/final settlement distinctions.

`DemoSink` is intentionally non-idempotent, persists independently of the ledger,
and supports either exact receipt lookup or no lookup. It is a testing tool only.
