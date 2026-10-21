# CommitLatch 0.1.0a2 — lost HTTP responses, observable recovery

An external service can commit an action and lose its response. This alpha makes
that failure reproducible over loopback HTTP and shows four recovery strategies.

## Try it

```sh
git clone https://github.com/ArtAndrew/commitlatch.git
cd commitlatch
PYTHONPATH=src python3 -m commitlatch http-demo
```

The synthetic provider drops the connection after committing. Assertions verify:

| Strategy | Effects | POSTs | Result |
| --- | ---: | ---: | --- |
| Blind retry | 2 | 2 | Duplicate |
| Native idempotency key | 1 | 2 | Success |
| CommitLatch + receipt lookup | 1 | 1 | Success |
| CommitLatch + unavailable lookup | 1 | 1 | UNKNOWN; repeat blocked |

Native provider idempotency is a valid solution. CommitLatch adds a durable local
intent record and explicit reconciliation; it cannot establish an outcome that
the provider cannot prove.

## New in this alpha

- Real TCP response-loss fixture with an independent provider database.
- Five additional tests: 27 core tests in total.
- Optional LangGraph 1.2.16 example, tested on Python 3.12, with success and
  unavailable-lookup paths. No model calls or API keys.
- Reproducible result animation, raw JSON and documented fixture assumptions.
- Provider-request and bug-report templates.

## Limits

Experimental alpha. The HTTP provider is a local test fixture, not a production
integration. No universal exactly-once guarantee, agent checkpoint recovery,
PostgreSQL backend or managed service. Apache-2.0. See the README and
`docs/VALIDATION.md` for evidence and boundaries.

Run the demo and open a Discussion with the provider operation you need,
its idempotency/receipt contract, and a small synthetic failure scenario.
