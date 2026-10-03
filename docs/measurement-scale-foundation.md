# Product v7 measurement and scale foundation

This document is the bounded contract for Task 544. It describes the existing
first-party lifecycle ledger and the admin-only aggregate report. It does not
introduce a provider, event warehouse, data lake, opaque score or raw event
archive.

## Lifecycle evidence contract

The ledger contract is `yfc-lifecycle-milestone-v2`:

- supported schema versions are `1` and `2`; new writes use version `2`;
- stored fields are an internal account key, an allowlisted milestone type,
  schema version, UTC timestamp, optional internal workout/program references,
  server surface, server-confirmed flag and authoritative outcome status;
- the server is the only writer. Browser and TMA retries use the same
  server-side deduplication key, so one authoritative outcome produces at most
  one row;
- workout/program context is checked against the owning account before a row is
  written. Cross-account or missing context is rejected;
- no names, contact identifiers, Telegram identifiers, food/exercise values,
  body or health data, notes, prompts, provider payloads, tokens or token-bearing
  URLs are stored in this ledger.

The coarse `users.measurement_eligibility` value is an operational boundary, not
a product score. `real_client` is the only eligible value for production client
cohorts. `demo`, `test`, `synthetic`, `load_test` and `technical` rows remain
reconcilable but are excluded from KPI denominators. Non-production reports are
also fail-closed.

## Retention and deletion

Account-linked evidence is pruned by the worker using:

- `LIFECYCLE_MILESTONE_RETENTION_DAYS` — default `180` days, configurable with
  a minimum of 180 days;
- `LIFECYCLE_AGGREGATE_RETENTION_DAYS` — default and maximum `730` days (24
  months). Reports are computed on demand; no account-level aggregate snapshot
  is persisted.

`delete_user_cascade` removes lifecycle rows before account deletion, and the
ledger foreign key also uses `ON DELETE CASCADE`. The report counts any orphan
row as `post_deletion_milestones`; retained aggregate output contains no account
identifier and therefore cannot restore an account after deletion.

## Reconciliation output

`GET /api/v1/admin/funnel` returns factual aggregate metadata and
`data_quality` counters for:

- duplicate milestones and duplicate Web/TMA authoritative outcomes;
- impossible order relative to registration and the program/workout sequence;
- known demo/test/technical contamination;
- client-only success without a server-confirmed outcome;
- post-deletion/orphan rows;
- unauthorized or cross-account workout/program references;
- malformed schema versions and retention-expired rows.

The report excludes invalid rows from KPI evidence. It always includes the
cohort date range, `period_days`, KPI window, numerator, denominator, cohort
size, exclusions and `sample_status`. Product effect remains
`NOT_YET_PROVEN`; `INSUFFICIENT_SAMPLE` is returned until there are at least
four completed weekly cohorts and preferably 100 eligible real accounts.

Client activation/retention KPIs and trainer capacity/share metrics remain
separate reports. No percentage is presented without its numerator and
denominator.

## Bounded scale evidence

The deterministic backend test
`backend/tests/test_lifecycle_measurement_foundation.py` exercises realistic
client/trainer fixtures at 10, 30 and 100 clients. It records only aggregate
query count and local p50/p95 duration; it does not emit account identifiers or
claim production latency.

The current local SQLite evidence showed:

- trainer capacity: 8 SQL queries at each fixture size, with p50/p95 in the
  low single-digit milliseconds;
- client lifecycle report: 22/42/112 SQL queries for 10/30/100 clients and
  approximately 6/13/31 ms p50/p95 at the 100-client fixture.

The linear client-report query growth is the existing per-account recovery
schedule check. It is recorded as the current bottleneck evidence; no index or
infrastructure change is claimed or added without production-like EXPLAIN/load
evidence. These local synthetic numbers are not a production SLO or a device/TMA
benchmark.

For this foundation, `env change required: no`: defaults are safe and no new
provider, secret, credential, DNS record or production integration is added.
