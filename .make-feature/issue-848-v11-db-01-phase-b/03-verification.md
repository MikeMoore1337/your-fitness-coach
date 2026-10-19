# Verification record

## Local evidence

- Exact local HEAD: `HEAD` is the commit reported by `git log -1` at PR handoff;
  the immutable SHA and exact-head Checks URL are recorded in the PR/Issue evidence
  after push.
- `tests/test_connection_budget_preflight.py`,
  `tests/test_trusted_runtime_collector.py`, backend marker/Alembic tests and the
  deployment regression set: `317 passed` in the combined targeted run; deployment
  and rollback subset: `60 passed`.
- Collector-specific coverage: `20 passed`, including future/host/revision mismatch,
  runtime env drift, inconsistent pool overrides, scaled candidate/all-slots,
  unexpected runtime database consumers, sanitized env parsing and bounded timeout.
- Frontend `AiCoachExperience.test.tsx`: `30 passed`; full Vitest: `949 passed`.
- Frontend lint and typecheck: `PASS`.
- Repository-wide frontend `format:check`: `NOT_PASS` on the current baseline
  (`536` existing files reported by Prettier); the changed assertion itself matches
  the formatter output and no frontend production file changed.
- Coverage includes read-only SQL shape, PG15/PG16 reserved behavior, permission and
  attribution failures, topology gaps, pooler, extra consumers, trust forgery,
  stale/future/mixed context and sanitized failures.
- Ruff check/format passed for changed Python files.
- The exact pre-commit `mypy-backend` hook: `PASS` (`284` source files). A direct
  project-venv invocation of `scripts/run_mypy.py` independently reports `122` errors
  in `15` untouched backend modules; no error points to the changed config/migration
  files. This local toolchain discrepancy remains for exact CI to arbitrate.
- Workflow, image and deployment contract groups: `PASS`; policy group: `307 passed,
  4 skipped`.
- `deployment_scope.py --base origin/master --head HEAD --json`: `deploy_required=true`;
  deploy paths are Dockerfile, Compose and backend runtime setup. Tooling/docs/tests
  remain no-deploy paths.
- Container build/migrated PostgreSQL stack and production collector run: `NOT_VERIFIED`
  locally; required exact-head CI is the review gate.

## Required before review handoff

- `git diff --check` and full changed-path review.
- `scripts/deployment_scope.py --base origin/master --head HEAD --json`.
- Exact-head GitHub Checks on the Draft PR.
- Issue #848 comment with PR, SHA, test evidence and explicit remaining owner gates.

## Explicit non-claims

No production PostgreSQL budget, production attribution, safety-headroom approval,
production dry run, gate activation, merge or deploy is claimed by this record.

## Security review result

Confirmed defects corrected in this Phase B revision:

- future timestamps now produce `BLOCKED`, not `UNKNOWN`;
- actual running container environment and replica counts participate in topology;
- candidate overlap accounts for scaled candidate instances;
- runtime container IDs are paired with inspected environment, revision labels and the
  exact child `docker exec` target;
- running OCI revision drift is blocked against `.deployment-sha`;
- bounded commands terminate the process tree and close parent pipes;
- Alembic uses the fixed `yfc-migration` PostgreSQL marker;
- the unrelated frontend unit assertion is scoped to its failure panel and keeps the
  user text, safety category, retry action and successful retry assertions.

Residual owner-gated limits: `application_name` is client-declared, the private token is
not cryptographic attestation, real PostgreSQL attribution/headroom are not proven, and
the production collector has not been run.
