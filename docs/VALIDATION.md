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
