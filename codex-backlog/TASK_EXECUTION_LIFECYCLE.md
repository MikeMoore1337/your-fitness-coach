# Task execution lifecycle

This is the compact active lifecycle for an Issue-backed change:

Git and GitHub are the operational source of truth; no local lifecycle database is required.

1. read the Issue, linked specification and current source;
2. create or reuse one short-lived branch from current `origin/master`;
3. implement the smallest complete change and run targeted verification;
4. commit, push and open/update a PR targeting protected `master`;
5. wait for the PR head's deterministic required Checks;
6. fix real failures on the branch and let GitHub rerun Checks;
7. merge after green Checks and applicable real-risk gates;
8. let Actions deploy only when changed paths affect the application, then run smoke/evidence;
9. record result in the PR, Checks, Actions and Git history.

There is no mandatory local state machine, lease, delivery owner, queue, fingerprint, task mirror,
exact-head database, worktree registry or archive/cleanup gate. Interrupted work resumes from Git
and GitHub inspection. Optional worktrees, Graphify, Agent Flow, Agent Harness and artifacts cannot
block ordinary work.

Required Checks must be green. Fail closed for authentication, authorization, secrets, dangerous
migrations, destructive data changes, security/legal boundaries and deployment failure. Treat
cleanup, stale clean worktrees, local branches, optional metadata and developer tooling failures
as warnings.

Rollback is an owner-authorized GitHub Actions operation using known successful production evidence;
it does not require local lifecycle state. Do not start another product task automatically.
