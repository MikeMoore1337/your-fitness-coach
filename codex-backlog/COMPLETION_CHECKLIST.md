# Completion checklist

- [ ] Current GitHub Issue and linked specification were used as scope.
- [ ] Branch is short-lived and based on current `origin/master`.
- [ ] Targeted tests and applicable static/type/build checks pass locally.
- [ ] PR targets protected `master` and the current PR head has green required Checks.
- [ ] Real security, privacy, legal, destructive and owner gates were handled when applicable.
- [ ] Merge result is visible in GitHub history.
- [ ] Application deployment ran only when changed paths require it.
- [ ] Production smoke and immutable deployment evidence pass for an application release.
- [ ] Rollback path remains available for a production release.
- [ ] Worktree/artifact cleanup, if attempted, was best effort and did not delete dirty/unique work.
- [ ] No local controller, lease, queue, fingerprint or lifecycle database was introduced.
