# #1206 - PostgreSQL 16 rest-interval rollout and contract

## Scope and invariants

- Initial auto-start remains `POST /api/v1/workouts/{workout_id}/rest-sessions`. Existing v1 journals and old initial sessions still resolve to the original initial rest. The caller must never send a manual repeat through this endpoint.
- Repeat rest: `POST /api/v1/workouts/rest-sessions/{predecessor_id}/restart`; body `{"started_at":"2026-10-25T08:00:00Z","mutation_id":"durable-client-start-id"}`.
- Server checks ownership, live workout, a completed eligible working set, and terminal predecessor (`completed`/`skipped`). It derives the source, workout and plan. New result keeps the existing response fields, adds nullable `start_mutation_id`, and carries a **new** interval ID.
- Exact replay returns the existing result, even if the interval has since stopped. Same mutation ID with changed payload returns 409; foreign or missing predecessor is 404; invalid context/time is 422.
- DB UNIQUE indexes: one initial interval per `source_set_id` (predecessor NULL), one successor per predecessor, unique mutation per workout, and **at most one running interval per workout**. All existing facts, IDs and nullable measurements remain unchanged.
- Runtime lock order on starts: workout row -> source set / predecessor (and then set) -> rest row. Mutations of an existing interval lock that interval only. The partial unique running index is the final guard for all writers.

## Controlled migration sequence (never blue/green overlap)

1. Run an **authorized read-only production preflight** against actual PG16 and record time, revision, counts, invalid indexes and blockers. Queries below do not invoke user-defined functions.
2. Back up and verify recovery using existing approved #849 pipeline. The backup itself is not permission to restore production.
3. The existing single-slot procedure (approved in #848) drains **all old backend/worker writers**, with observed DB clients and connection budget M=10. Do not allow old backend after new repeat intervals exist.
4. Run Alembic 0131: three nullable columns plus PG16 `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS` for all replacement protections. Measure index build and inspect `pg_index.indisvalid`/`indisready`. PostgreSQL concurrent unique index failures can leave invalid indexes: **STOP**, inspect and manually remediate under a separate authorized step; `IF NOT EXISTS` does not validate an existing invalid index.
5. Run 0132 only in the drained single-slot window. Verified indexed protection must exist before the short `ALTER TABLE ... DROP CONSTRAINT` with `lock_timeout='3s'` and `statement_timeout='30s'`. The online migration validator has one precisely scoped `rest_unique_swap` exception; it is not disabled.
6. Start the exact tested new backend/worker release; verify Alembic head, contract tests, smoke and provenance before reopening traffic. No overlapping old replicas and no speculative second slot.
7. Coordinate #1166 frontend integration against the new restart path. Old clients may continue calling initial start. If multiple sessions per source set have been created, **old backend image rollback is forbidden**; forward-fix the new code and retain the schema/history.

A failed index build, duplicate running record, missing schema revision, migration timeout, preflight failure or loss of DB ownership is **BLOCKED**, not auto-repaired. Do not delete or silently update historical rest rows to pass the migration.

## Production read-only preflight SQL

Run these via a trusted read-only observer in an explicitly read-only transaction; redact user/source identifiers from published output.

```sql
BEGIN READ ONLY;
SELECT version_num FROM alembic_version;
SELECT status, COUNT(*) AS intervals FROM workout_rest_sessions GROUP BY status ORDER BY status;
SELECT COUNT(*) AS workouts_with_multiple_running FROM (
  SELECT workout_id FROM workout_rest_sessions
  WHERE status = 'running' GROUP BY workout_id HAVING COUNT(*) > 1
) candidates;
SELECT COUNT(*) AS rows_without_source_set FROM workout_rest_sessions
WHERE source_set_id IS NULL;
SELECT c.conname, c.contype
FROM pg_constraint c WHERE c.conrelid = 'workout_rest_sessions'::regclass
ORDER BY c.conname;
SELECT i.relname, ix.indisvalid, ix.indisready, ix.indisunique
FROM pg_index ix JOIN pg_class i ON i.oid = ix.indexrelid
WHERE ix.indrelid = 'workout_rest_sessions'::regclass
ORDER BY i.relname;
COMMIT;
```

Required before schema switch: the legacy UNIQUE exists, multiple-running result equals zero, no suspicious invalid replacement indexes, consistent Alembic revision and no competing old-version writers. If any check is unknown, stop.

## Evidence status

- Draft PR #1207: source/tests prepared; not an approval to deploy.
- `PG16_CONCURRENCY`: checked only when a PostgreSQL-backed CI run actually reports PASS. SQLite is not adequate for the concurrent lock oracle.
- `PRODUCTION_PREFLIGHT`: NOT_RUN from this PR environment; requires read-only production access and exact-release evidence.
- `PG16_LOCK_DURATION`: NOT_MEASURED pending isolated test on representative historical rows and long transactions.
- `SINGLE_SLOT_ACTIVATION`: NOT_RUN pending exact-head CI, approved maintenance window and no incompatible active backend.
- `OLD_IMAGE_ROLLBACK_AFTER_MULTIPLE_ROWS`: FORBIDDEN (forward-fix only).
