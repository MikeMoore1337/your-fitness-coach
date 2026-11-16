---
name: data-engineer
description: >
  Design or change persistent data models, database schemas, migrations, constraints, indexes,
  transaction semantics, retention and query performance. Use when stored data or migration
  behavior changes; do not use for business logic that does not alter persistence semantics.
---

# data-engineer

Model invariants before modeling tables or collections.

## Schema

Use suitable types and `NOT NULL`/`UNIQUE`/`FK`/`CHECK` constraints when the database must enforce an invariant. Define ownership, lifecycle, timestamps and timezone semantics. Use soft deletion only when there is a real need.

## Lifecycle and privacy

For personal/sensitive data explicitly define owner/access boundary, retention/deletion semantics, cascade/orphan behavior, exportability when required, soft-delete effects on uniqueness/queries, backup implications and exclusion from analytics/debug copies. Coordinate with `$privacy-engineer`; soft deletion is not a universal substitute for proper deletion.

## Indexing

Add indexes for observed query patterns, not speculatively. Check selectivity, composite order, write cost and query plans for important queries.

## Migrations

Production migrations must be reproducible, safe for existing data, compatible with rolling deploys if used, have an explicit rollback/forward-fix strategy and avoid excessive long locks on large tables when relevant. For destructive changes, use expand/contract where appropriate.

## Transactions

Define atomicity and isolation assumptions explicitly.

## Backups

Critical data requires backup plus tested restoration. An unverified restore does not constitute a complete backup strategy.

## Project adaptation

Inspect the actual database, ORM/data-access layer, migration tool, deployment topology and dataset size. Never rewrite already-applied production migrations when the migration system requires immutable history; create a corrective migration.
