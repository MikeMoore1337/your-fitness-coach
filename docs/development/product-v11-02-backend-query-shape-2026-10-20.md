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

For 25 clients with one common local date, the complete SQLAlchemy bound-value count (including the final `rank == 1` value) changes from **76** (25 outer IDs + 25 per-client IDs + 25 per-client dates + rank) to **27** (25 grouped IDs + one date + rank). The local-day comparison branch count changes **25 → 1**. Actual statement length, parameter count, and PostgreSQL query plans must be obtained by the new isolated benchmark; no SQL-text length or plan-time figure is asserted until it has been captured and reviewed. The integration regression test checks the real query shape and bound count. These are **not** SQL execution-time measurements. A two-local-day fixture additionally asserts separate cutoffs; future measurements remain excluded.

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


## Phase 2: PostgreSQL 16 trainer-scale reproducibility

An opt-in synthetic PostgreSQL profile is implemented in
\`backend/tests/test_performance.py::test_coach_weight_query_postgres_profile_is_bounded_and_equivalent\`,
parameterized for **10, 30 and 100 clients**. It runs on the repo's existing
isolated \`TEST_DATABASE_URL\` fixture and skips on SQLite.

- Each synthetic client has twelve historical daily body-weight measurements
  plus one future-dated measurement that must remain invisible.
- Time zones rotate between UTC, Pacific/Honolulu and Pacific/Kiritimati.
  The historical, per-client BEFORE query is reconstructed locally and compared
  to the optimized list_clients results, so authorization and user-specific
  local-day cutoffs are protected.
- Both SELECT statements undergo \`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)\` with
  a transaction-local 5-second timeout. Neither statement changes production
  data or invokes any migration.
- The test requires equivalent results, one ranked query, bounded date
  predicates, fewer SQL characters, and 3N+1 versus N+distinct_days+1 SQL
  parameter bindings.
- The test reports \`V11_02_SYNTHETIC_POSTGRES\` lines when executed with \`pytest -s\`.
  Individual execution-time figures are diagnostics, not performance budgets.
  This paired sample is too small and too cache-sensitive to claim a causal
  p95/p99 improvement.

Reproduce with a separately provisioned PostgreSQL 16 test database and
the repository's normal test environment settings:

~~~bash
TEST_DATABASE_URL="<isolated-test-db-connection-string>" \
  uv run pytest -q -s backend/tests/test_performance.py \
  -k coach_weight_query_postgres_profile
~~~

Do not paste the connection string into public CI output, PRs or a shell log;
the placeholder above is not a real secret.

The normal GitHub Python test matrix already uses PostgreSQL 16 for its
\`TEST_DATABASE_URL\` when the scope router includes Python tests. Passing
that CI validates the PostgreSQL fixture/code path, but **measured BEFORE/
AFTER request-level p95/p99 latency and actual production PostgreSQL metrics
remain NO_DATA**.

## Cross-surface coverage and stop rules

Existing narrow regression tests already cover constant/near-constant query
count for Coach client lists, Coach inbox, Coach attention, nutrition diary,
training analytics and trainer summaries. These tests are *not* evidence that
all route latencies are fast. No N+1 across other endpoints or missing index
was confirmed by this #817 change; refrain from inventing an index migration.

The remaining #817 performance investigation must use a representative
isolated PostgreSQL 16 dataset and capture exact route SQL counts, SQL time,
response payload size and total request duration for authentication,
Today/Workout, Nutrition, Programs and Coach OS. Postgres plan costs and
effective PostgreSQL headroom must be distinguished from actual production
observations. Treat an unmeasured hotspot as NOT_PROVEN rather than as fixed.

### Release gate unchanged

#848 P0 production capacity preflight is a blocking predecessor for affected
rollout. CI on master triggers automatic production deploy; do not merge
PR #1131 until the independent trusted budget gate and headroom are verified
and active. No direct production query, migration, index change or new
paid infrastructure is authorized here.


## Phase 3: representative API request-cost diagnostics (synthetic PG16)

The test \`backend/tests/test_v11_backend_route_profile.py\` exercises **six
real authenticated GET routes**, three repetitions each, against the existing
PostgreSQL 16 test fixtures:

| Area | Method/path | Actor |
|---|---|---|
| Authentication/profile | GET /api/v1/me | athlete |
| Today/active workout | GET /api/v1/workouts/today | athlete |
| Programs | GET /api/v1/programs/templates/mine | athlete |
| Nutrition | GET /api/v1/nutrition/diary?diary_date=... | athlete |
| Coach OS client list | GET /api/v1/coach/clients | trainer |
| Coach OS aggregated inbox | GET /api/v1/coach/inbox | trainer |

This does not manufacture data or attempt production authentication. The
test signs in using the repository's existing **development-only test login**,
checks expected read-route status (including the existing 404 empty-state
when no workout is assigned to Today), X-Request-ID, and existing sanitized
structured request-log fields. FastAPI's local registered route template
may legitimately be empty for the root /me subrouter. It prints only route
names, actor category, requests per route, HTTP median, SQL median, SQL query
count range and serialized response byte size; no response body, identity,
JWT, customer records or database connection details.

~~~
TEST_DATABASE_URL="<isolated-test-db-connection-string>" \
  uv run pytest -q -s backend/tests/test_v11_backend_route_profile.py
~~~

The values are intentionally **diagnostics**, not hidden CI pass/fail timing
thresholds. Only an independently reproduced controlled comparison with a
fixed fixture and execution profile should be promoted to a benchmark.
Production latency/percentiles, actual user traffic mixes, connected devices,
pool wait/overflow and non-YFC connection attribution remain \`NO_DATA\`.

## Final disposition guidance

If the PostgreSQL regression suite passes, a bounded code-quality change can
be declared *technically verified* and retained in PR #1131. That is **not**
sufficient to call the whole #817 closed: the child contract still asks for
ranking hot API calls with real or representative load, query plans, index
usage, migrations' online compatibility and validation against effective #848
capacity. These must either be evidenced or explicitly documented as
deferred/not proven under the owner's acceptance decision.

Issue #817 remains OPEN until exact-head checks, performance evidence,
controlled release under #848, and subsequent post-deploy smoke are reconciled.
