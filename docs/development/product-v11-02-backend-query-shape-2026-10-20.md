# Product V11-02 / #817: Coach client weight-query shape (Phase 1)

Issue: [#817](https://github.com/MikeMoore1337/your-fitness-coach/issues/817), parent [#814](https://github.com/MikeMoore1337/your-fitness-coach/issues/814). Baseline: `master` `aba8275040578e69fe597bea350351cf4351392f`, 2026-10-20.

## Confirmed source-level finding

`services/programs.py::list_clients` already avoids N+1 database roundtrips: the existing `backend/tests/test_performance.py::test_coach_client_list_query_count_is_constant` expected five SQL statements for 25 clients. However, its windowed latest-weight query constructed one `(user_id = :id AND measured_on <= :today)` branch **per active coach client**, in addition to an outer `user_id IN (...)` predicate. The SQL text and number of bound values therefore increased with the number of clients, even when everyone shared the same local calendar date. This is a query-shape observation, **not** a measured PostgreSQL production latency or planner regression.

## Bounded fix

- Compute each client's own `today_for_user(user)`, preserving the existing IANA timezone fallback.
- Group authorized client IDs by the resulting **local date**.
- Filter measured weights with `(user_id IN (:ids_for_date) AND measured_on <= :local_date)` per distinct local date, not per client.
- Drop the redundant outer `user_id IN (...)` because every group already covers precisely the same authorized client IDs.
- Keep the existing `row_number() OVER (PARTITION BY user_id ORDER BY measured_on DESC, id DESC)` ranking and all other response construction, security filters and nutrition relations unchanged.

For 25 clients with one common local date, the complete SQLAlchemy bound-value count (including the final `rank == 1` value) changes from **76** (25 outer IDs + 25 per-client IDs + 25 per-client dates + rank) to **27** (25 grouped IDs + one date + rank). The local-day comparison branch count changes **25 → 1**. A separate simplified SQLAlchemy/SQLite compilation check showed 2,288 versus 524 SQL characters and 76 versus 27 positional bindings; those figures describe a reduced query model, not a captured production query plan or latency result. The integration regression test checks the real query shape and bound count. These are **not** SQL execution-time measurements. A two-local-day fixture additionally asserts separate cutoffs; future measurements remain excluded.

## Verification

- SQL statement/query-count regression: existing 25-client fixture plus weight fixtures, one ranked query, one date predicate and 26 bound values. The historical five-query count remains asserted.
- Local-day semantics: independent clients in `Pacific/Honolulu` and `Pacific/Kiritimati`, history and future dates, with separate SQL date predicates.
- CI should run all ordinary Python/backend, PostgreSQL stack, security, frontend/contract and deployment policy jobs. This report does not presume pass before a successful exact-head run.
- No schema, migration, index, pool setting, backend endpoint, auth policy, token, frontend resource or production configuration changes.

## Evidence limits / remaining Issue #817 work

- Production PostgreSQL p50/p95/p99, actual planner/EXPLAIN/BUFFERS, data distribution, runtime pool waits, connection usage, and overall route latency: **NO_DATA**. The unrelated #848 connection-budget safety gate is still **NOT_PROVEN**.
- The next stage of #817 should compare fixed synthetic PostgreSQL fixtures (small/medium/trainer-scale), query counts, SQL duration, total request latency, response bytes, and safe EXPLAIN for high-impact endpoints including Coach OS, Today, workouts and nutrition. No index or pool changes without a measured justification.
- This phase improves a demonstrably overlong SQL predicate construction. It does **not** certify full #817 acceptance or production speedup.

## Release boundary

PR remains Draft while technical verification is pending. Owner has authorized normal merge in general, but merging this application-code PR into `master` would trigger automatic production deployment. Respect Product V11 P0 #848: no affected rollout before the trusted capacity preflight is proven and active. No forced merge, no production query, deploy, migration or Issue closure from this phase.
