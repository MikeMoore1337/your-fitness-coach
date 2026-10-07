# Backlog global rules

These rules apply to owner-selected backlog work. They describe ordinary GitHub Flow and do not
introduce a repository-local lifecycle.

## Canonical state

The GitHub Issue is the task contract. A linked tracked specification is allowed for large scope,
but local Issue materialization is never mandatory. Git branch, PR, Checks, merged `master`,
Actions deployment and Git history are the only operational records.

## Branch and PR

- Start a short-lived branch from fresh `origin/master`.
- Keep changes task-local and preserve unrelated user work.
- Open a PR to protected `master`; never direct/force-push `master`.
- Merge only after required deterministic `checks` and applicable real-risk gates are green.
- Do not require a second human approval in a single-owner repository unless GitHub policy actually
  requires it.

## Verification

Use targeted tests plus the relevant CI matrix: backend/bot tests, frontend checks/build/E2E,
migrations, integration, dependency audit, CodeQL and Trivy as applicable. CI verifies code and
release integrity, not local worktree cleanliness or optional metadata.

## Deployment

After a successful merge, GitHub Actions uses stateless changed-path classification. Runtime,
migration, image, production configuration and deployment-helper changes deploy an immutable
bundle, perform safe migrations, rollout and production smoke. Documentation, backlog, governance,
tests-only and local tooling do not deploy the application.

Production serialization is Actions `concurrency.group: production` with
`cancel-in-progress: false`. Existing deployment evidence, health checks, migration sequencing,
worker/bot ownership and rollback remain safety mechanisms.

## Gates and cleanup

Only real safety gates remain: secrets/credentials, destructive or irreversible data operations,
history rewrite, paid resources, legal/privacy decisions, security boundaries and explicit owner
gates. Worktree/artifact cleanup is bounded best effort and never a completion gate.

Do not start the next product task automatically.

## Anti-recurrence

STANDARD GIT/GITHUB FIRST. ONE OPERATIONAL SOURCE OF TRUTH. STATELESS HELPERS. FAIL CLOSED ONLY
FOR REAL SAFETY. No controller/orchestrator/owner/lease/queue/fingerprint/recovery database or
mandatory local task mirror may be added without a new direct owner approval after native GitHub
mechanisms have been shown insufficient.
