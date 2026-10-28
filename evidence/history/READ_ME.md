# Development checks, not final-release results

The initial suite completed 47 checks: 46 passed and one detached-child fixture failed because its 0.15-second deadline expired before child startup was established. The test was changed to prove startup, allow a two-second deadline, assert bounded controller return, and explicitly terminate the detached fixture. The safety assertion was not removed. The next 52-test run passed. Later checks added installation metadata, session ownership, malformed review and documented Cursor configuration regressions. See ../VERIFICATION.md and final logs for the delivered source.

Two surrounding command attempts were interrupted by the host tool timeout before a complete suite; they are not counted as completed tests. Completed runs are identified by their unittest final summary and results JSON.
