# Do you need CommitLatch?

Start with your provider's own idempotency and receipt APIs. Read their account
scope, parameter-binding rules, retention window, and pending/final states.
CommitLatch does not replace that contract.

| Situation | Practical choice |
| --- | --- |
| One provider has native idempotency and your application already persists the right key and result | You may not need this library |
| Your existing workflow runtime already implements the same durable identity and receipt checks | Keep that implementation; do not add a second retry owner without a reason |
| Several callers need one local record, immutable operation parameters and a shared recovery decision | Evaluate CommitLatch against your existing implementation |
| A response can be lost, but the provider exposes an authoritative matching receipt | An adapter can reconcile the result without another mutation |
| The provider cannot prove the outcome | CommitLatch can stop another dispatch; it cannot recover missing evidence |
| You need multi-host storage, real payment integrations, authorization or a hosted service today | This alpha is not ready for that deployment |

## What the current core adds

- One `(namespace, business_key)` bound to immutable arguments and adapter identity.
- Durable intent before dispatch, stored results and an event history.
- Local concurrency claims and rejection of stale ledger writes.
- An explicit UNKNOWN state that does not silently become a retry.
- A small adapter contract that states what can and cannot be proven.

## What would be misleading

“Exactly once for any API,” “never duplicates payments,” and “replaces LangGraph
or Temporal” are not claims this project makes. Calling the provider directly,
changing keys, restoring stale ledgers or making false adapter assertions can
bypass the boundary. A local lease cannot cancel an already-dispatched request.

Our native-idempotency baseline succeeds too. The point of the HTTP demo is to
make different recovery decisions inspectable, not to make an existing mechanism
look broken. See [methodology and limitations](HTTP_DEMO.md).
