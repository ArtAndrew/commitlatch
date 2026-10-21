# Validation — 2026-10-21

Version: 0.1.0a1. Environment: macOS, Python 3.9.6.

- All 22 local unittest tests passed, including real process crashes, independent
  competing processes, stale-worker fencing, ambiguous receipts and read-only replay.
- A wheel was built without downloading runtime dependencies and installed into a
  fresh virtual environment. The installed CLI was run outside the source tree.
- The installed package's three crash scenarios produced these observed results:

| Scenario | Final state | External test effects | Dispatch attempts |
| --- | --- | ---: | ---: |
| Blind retry | DUPLICATED | 2 | 2 |
| Receipt reconciliation | SUCCEEDED | 1 | 1 |
| Unobservable outcome | UNKNOWN | 1 | 1 |

Each scenario terminated its worker with exit code 42 after the independent test
sink committed its effect. The UNKNOWN scenario refused a second dispatch.

The quickstart also ran against the installed wheel: a lost response was reconciled,
and a repeated business key returned the stored receipt with one total test effect.

The HTML report was generated. Automated browser visual inspection was blocked
by the browser's local-file URL policy; no visual verification is claimed.

## GitHub Actions

[Run #1](https://github.com/ArtAndrew/commitlatch/actions/runs/39558606204)
completed successfully for commit `2958d3917d60b55c20189795b1240d62b3ef6006`.
All six combinations passed: ubuntu-latest and macos-latest, each with Python
3.9, 3.11 and 3.13. Each job ran the 22 tests, installed the package, checked
its CLI version and executed the crash demo.

No live payment provider, HTTP fault proxy, PostgreSQL deployment or distributed
service was tested. These results are not a production reliability benchmark
or an exactly-once guarantee.


## Alpha 0.1.0a2 — launch package

Locally verified on macOS, Python 3.9.6: all 27 tests passed, including five
new loopback HTTP tests. Local test permissions were needed to bind 127.0.0.1.

The four HTTP scenarios observed effects/POST counts of 2/2, 1/2, 1/1 and 1/1.
The last remained UNKNOWN. See `assets/http-results.json` for raw evidence.

LangGraph 1.2.16 was installed in an isolated Python 3.12.14 environment. Both
normal and opaque examples ran successfully: two reconstructed graph invocations
produced only one POST and one provider effect. The normal result was SUCCEEDED;
the opaque result stayed UNKNOWN. No LLM or paid provider was called.

The new CI job runs both examples. Use the repository Actions page for current
remote run status; the earlier run linked above only covers 0.1.0a1.

The launch GIF is a paced rendering of measured JSON, not a screen recording or
a timing result. The social preview and static final frame were visually checked.

The `0.1.0a2` wheel was built, installed into an isolated Python 3.9 environment,
and its version and `http-demo` command were checked successfully. The final core
suite passed all 27 tests after packaging.
