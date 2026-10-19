# Verification record

## Local evidence

- Exact local HEAD: `HEAD` is the commit reported by `git log -1` at PR handoff;
  the immutable SHA is recorded in the PR/Issue evidence after push.
- `tests/test_connection_budget_preflight.py` and
  `tests/test_trusted_runtime_collector.py`: `49 passed`.
- `tests/test_deployment_scope.py` and `tests/test_zero_downtime_deploy.py`: `60 passed`.
- `backend/tests/test_alembic_config.py`: `4 passed`; DB application marker test:
  `1 passed`.
- Coverage includes read-only SQL shape, PG15/PG16 reserved behavior, permission and
  attribution failures, topology gaps, pooler, extra consumers, trust forgery,
  stale/future/mixed context and sanitized failures.
- Ruff check/format passed for changed Python files.
- Mypy passed for changed backend configuration/session files.
- `deployment_scope.py --base origin/master --head HEAD --json`: `deploy_required=true`;
  deploy paths are Dockerfile, Compose and backend runtime setup. Tooling/docs/tests
  remain no-deploy paths.
- Docker/production collector run: `NOT_VERIFIED` by scope.

## Required before review handoff

- `git diff --check` and full changed-path review.
- `scripts/deployment_scope.py --base origin/master --head HEAD --json`.
- Exact-head GitHub Checks on the Draft PR.
- Issue #848 comment with PR, SHA, test evidence and explicit remaining owner gates.

## Explicit non-claims

No production PostgreSQL budget, production attribution, safety-headroom approval,
production dry run, gate activation, merge or deploy is claimed by this record.
