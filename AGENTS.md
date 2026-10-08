# Your Fitness Coach repository rules

Your Fitness Coach is one product exposed through the browser and Telegram Mini App. `frontend/`
is React/TypeScript/Vite, `backend/` is Python/FastAPI/SQLAlchemy/Alembic, `bot/` is Aiogram,
and PostgreSQL is the shared database. Preserve the current modular architecture unless the
current change has a concrete, owner-approved reason to change it.

## Source of truth and scope

Use this order for the current work:

1. the current owner/user request;
2. the current GitHub Issue and its linked specification, when present;
3. current source, tests, migrations, Git history, PR Checks and Actions;
4. this file and relevant profile documentation.

GitHub is the operational source of truth:

`Issue -> short-lived branch -> Pull Request -> Checks -> protected master -> Actions deploy/smoke`.

An Issue is the task contract. A tracked Markdown specification may be linked from it when the
scope is large. A local mirror, fingerprint, database, lease, queue, owner record, lifecycle
transition or archive record is never required to understand or continue ordinary work.

Keep work scoped. Do not start another product task, roadmap stage or migration after the current
request unless the owner sends a new prompt.

## GitHub Flow

- Start from a fresh `origin/master` and use one short-lived branch for the change.
- Open a PR targeting protected `master`; direct pushes and force-pushes to `master` are forbidden.
- Required deterministic Checks are the merge gate. The aggregate `checks` result must be green.
- GitHub PR head, branch rules and Checks are sufficient for current-base/exact-head decisions.
- Merge only after required Checks and applicable human/legal/security/destructive gates pass.
- A merged `master` revision is the release revision. GitHub Actions records deployment and smoke.
- If a session is interrupted, continue from `git status`, `git branch`, `git log`, `git worktree
  list`, `gh pr view/status` and `gh run list`. No local recovery database is needed.

Normal changes do not need a generic approval between implementation, PR, CI and merge. Preserve
real gates for destructive production operations, secrets, credentials, irreversible user-data
operations, history rewrites, paid resources, legal/privacy decisions and explicitly owner-gated
visual redesigns.

## Architecture and implementation

- Keep business rules out of transport/presentation layers where practical.
- Enforce authorization and critical validation on trusted server boundaries.
- Prefer an existing helper, a standard-library/native platform feature, an installed dependency,
  then the smallest complete implementation.
- Do not add a framework, service, queue, lock, database or compatibility layer for speculative
  future work.
- Preserve validation, authorization, error handling, security, accessibility, typing and tests.
- Fix shared root causes after checking all callers; do not patch only one symptom path.
- Ordinary user-facing UI is EVOLVE: read `codex-backlog/ACTIVE_DESIGN_SOURCE.md`,
  `.agents/references/DESIGN_GUARDRAILS.md` and `docs/design/YFC_PRODUCT_UI_CONTRACT.md` before
  changing authenticated UI. RETHINK requires an explicit owner-approved exploration task.
- Use the shared `WeekStrip` for ordinary seven-day week contexts.

## RUSSIAN_USER_FACING_UI (mandatory)

- All new authenticated Web, Telegram Mini App, athlete-cabinet and trainer-cabinet UI copy is
  Russian by default. This includes headings, labels, buttons, placeholders, hints, dialogs,
  notifications, errors, statuses, chart/card labels and accessibility copy such as `aria-label`.
- Allowed exceptions are `Your Fitness Coach`, official external brand names, necessary technical
  or common fitness abbreviations without a practical Russian equivalent, and user-generated text.
  `follow-up`, `review`, `rollout` and `Nutrition Planning` are not exceptions.
- New or changed user-facing literals are checked by the AST-based `frontend` guard through
  `npm run lint`; the guard is part of the required `frontend-checks` CI group. Do not add inline
  bypasses. Legacy English UI is tracked separately and must not be expanded by new changes.

## Verification and security

Run risk-based targeted checks, then the applicable repository checks. Meaningful checks include
pytest, frontend tests/build/typecheck/lint/format, mypy, migrations, integration/E2E, CodeQL,
dependency audit and Trivy. Do not weaken a check, hide a failure or delete application coverage
to make a migration pass.

Repository-native security review is conditional and uses the security skill and threat model.
Deterministic CodeQL, dependency and Trivy checks remain ordinary PR Checks; they do not need an
OpenAI credential or an LLM verdict.

`scripts/agent_flow.py`, `scripts/agent_harness.py`, Graphify and host Ponytail are optional local
assistance. They may suggest roles, inspect code or write derived evidence only when explicitly
invoked. Their absence or failure cannot block a branch, PR, merge or deployment. They do not own
branches/releases, create queues/leases, or store lifecycle state.

## Deployment contract

Production delivery is GitHub Actions-native:

`merged master -> exact CI success -> stateless changed-path decision -> immutable bundle ->
migrations -> rollout -> production smoke/evidence`.

The deploy workflow uses `concurrency.group: production` with `cancel-in-progress: false`. Do not
add a repository-local mutex or replacement owner. Application deploy is required for actual
runtime, migration, image, production configuration and scripts copied into an application image.
Documentation, backlog, governance, tests-only, CI/deploy workflows and host-side delivery helpers
do not deploy unchanged application runtime. Unknown non-governance paths are handled
conservatively by the stateless helper.

Deployment evidence under the production `.artifacts/operations/deployments/` area is operational
release evidence, not development lifecycle state. Keep immutable bundle/revision checks, safe
migration sequencing, health checks, worker/bot ownership checks, smoke and rollback. Rollback is
an owner-authorized GitHub Actions operation against known successful production evidence and does
not depend on local task state.

## Worktrees and artifacts

Worktrees are a local convenience only. They are not task identity, operational truth or release
correctness. Clean merged worktrees/branches may be removed as best effort. Never automatically
delete dirty worktrees or branches with unique commits. Preserve interrupted or owner-saved work
until the owner explicitly asks for destructive cleanup.

`.artifacts/` is ignored evidence and temporary storage only:

- `.artifacts/worktrees/` for local convenience;
- `.artifacts/tasks/<LABEL>/{temporary,evidence,deliverables,logs}/` for explicitly requested local
  evidence;
- `.artifacts/runtime/{cache,tmp,tests}/` for reproducible runtime data;
- `.artifacts/shared/` for reusable local assets such as the optional Graphify graph;
- `.artifacts/operations/{backups,deployments,recovery}/` for protected operational evidence.

Use `scripts/artifact_manager.py` for bounded path-safe cleanup when needed. Cleanup and artifact
housekeeping are best effort and warnings; they are never completion, merge or deployment gates.
Operational backups and deployment evidence are not ordinary garbage.

## Optional analysis tools

For non-trivial architecture impact analysis, `python scripts/graphify_yfc.py bootstrap` may build
derived navigation data under `.artifacts/shared/graphify/`. Prefer scoped queries, then verify the
real source/tests/migrations/docs. A tooling-only failure falls back to direct inspection.

The optional harness may validate small pytest-backed eval manifests and propose owner-review
learning candidates. It must not persist transcripts, secrets or lifecycle state and has no place
in required CI.

## Permanent anti-recurrence rule

STANDARD GIT/GITHUB FIRST. ONE OPERATIONAL SOURCE OF TRUTH. STATELESS HELPERS. FAIL CLOSED ONLY
FOR REAL SAFETY.

Without a new direct owner approval, do not create a second operational source of truth, a
repository-local lifecycle state machine, a generic branch/PR/CI/merge/deploy orchestrator, a
delivery/release/implementation owner, a custom lease/queue/mutex, mandatory Issue mirroring,
fingerprint gate, readiness/recovery state, local exact-head database, worktree registry as truth,
artifact/archive prerequisite, or a custom deploy classifier when native changed-path logic is
sufficient.

Before proposing any new lifecycle mechanism, check Git, GitHub Issues/PRs, Rulesets, Checks,
Actions, Actions concurrency and Environments/Deployments in that order. If native mechanisms are
insufficient, stop with `NEW_ORCHESTRATION_OWNER_APPROVAL_REQUIRED` and describe the unresolved
problem, native options checked, smallest addition, state/failure modes and removal path. Do not
implement it under another name.
