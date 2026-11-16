---
name: release-manager
description: >
  Prepare and verify a production release: migration order, rollout, smoke checks, success
  criteria, monitoring, rollback or forward-fix and post-deploy validation. Use for release
  readiness or deployment planning; actual production deployment requires explicit authorization.
---

# release-manager

Before release, prepare a checklist appropriate to the product and change.

Verify:

- Reproducible build artifacts.
- Green required tests and checks.
- Validated migrations.
- Prepared configuration/secrets.
- Backward compatibility and external dependencies.
- Feature flags, if present.
- Rollback/forward-fix path.
- Backups for changes that might corrupt data.
- Smoke tests.
- Monitoring/alerts capable of observing the change.

## Release success criteria

Before deployment, define several observable success signals for the change:

- Critical user journey succeeds.
- Error rate and latency have not materially degraded.
- Migrations/background processing complete.
- No spike in client/server exceptions.
- Product-critical success signals work when instrumented.

Never reduce success criteria to “deployment succeeded”.

After deployment, verify health/readiness, errors, latency, critical journeys, background jobs/queues, migrations, new logs/metrics/traces and the defined product-specific success signals.

Release notes should describe user-facing or operationally meaningful changes, not restate the Git diff.

## Project adaptation

Derive release order from actual services/apps, migrations, generated contracts, background jobs, feature flags and external dependencies. Never assume a deployment topology. Preparation/local verification does not authorize production actions.

In this repository, a production revision reaches remote `master` only through a merged PR with a green `checks` status. GitHub Actions verifies merge SHA, determines the changed-path scope and runs the production workflow for application changes. Direct or forced pushes, history rewrites and manual production actions outside this standard path require separate owner approval, a backup and preflight.
