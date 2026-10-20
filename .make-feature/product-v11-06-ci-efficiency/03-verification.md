# Product V11-06 / Issue #821 — verification receipt

Status: exact-head first receipt green; this receipt commit must receive its own exact-head rerun
PR: [#1136](https://github.com/MikeMoore1337/your-fitness-coach/pull/1136)
Implementation HEAD before this receipt: `e4f59eefce50b824c2aedca10136772235e56635`

## Local verification

| Check | Result |
|---|---|
| Pre-commit hooks | PASS |
| `scripts/ci_contract.py validate` | PASS; `ci-contract-v2`, digest `c53a8154cef3515eeb2c8b84caa5c62caf9e3acc71182b62e344357043ef9d25` |
| CI workflow YAML parse | PASS |
| CI/routing/timing/deployment/security contract suite | PASS; 104 passed |
| Ruff format/check for changed Python | PASS |
| `git diff --check` | PASS |
| Deployment scope | PASS: `deploy_required=false`, `deploy_paths=[]` |

The broader neighbouring scheduled-regression selection was not a clean local gate: 143 tests
passed and 4 were skipped, while 4 existing Allure/SSH publisher tests failed on the Windows
sandbox temporary-directory/auth-fixture path. Those failures are outside the changed files and
were not hidden or weakened.

## Exact-head GitHub Actions

Run [39457145434](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39457145434)
completed successfully for `e4f59eefce50b824c2aedca10136772235e56635`.

- Run wall: 409 seconds (`2026-10-20T16:24:24Z` to `2026-10-20T16:31:13Z`).
- Observable run-level queue component: 0 seconds (`created_at == run_started_at`). The first
  router job started at 16:24:27Z; later runner allocation is visible in job timestamps, but
  GitHub exposes no processor/billing CPU seconds: `PROCESSOR_TIME=NO_DATA`.
- Actions job API: 31 jobs; 28 success, 3 expected skipped, 0 failed. Skips were the PR-inapplicable
  extended mobile, weekly cross-browser and scheduled report jobs.
- Aggregate `checks`: success at 16:31:12Z.
- CodeQL Python and JavaScript/TypeScript: success.
- Free PR security audit / Trivy: success.
- Dependency audit: success, one job, 43 seconds.
- Five Python shards: 228, 261, 306, 321, 324 seconds.
- Five frontend smoke shards: 262, 267, 285, 286, 326 seconds.
- PostgreSQL migrated stack, mobile regression, workflow contracts, policy, critical smoke and
  all four container jobs: success.
- Artifacts: 8 artifacts, 66.00 MiB; this is not an upload CPU measurement. Docker/container
  artifacts remain #851 scope.

## Before/after interpretation

The 20-run pre-change sample had 17 successes, one cancelled scheduled run and two failures; its
all-event median wall was 468 seconds. Comparable recent 31-job cross-stack PRs ranged from
372–527 seconds (historical references included 763 seconds), so the 409-second exact-head run
is within the observed runner/cache variation. The closest same-day 31-job reference
`39435906918` was 419 seconds; the exact-head run was 409 seconds, but this single comparison does
not prove a stable wall-time speedup.

The duplicated operation is proven removed by the final job shape. Before, run `39435906918` had
`Free PR security audit=136s` with setup plus the shared dependency audit and a separate
`Dependency audit=33s`; after, `Free PR security audit=29s` contains checkout plus Trivy only and
`Dependency audit=43s` is the sole npm/uv audit owner. A second baseline (`39245697126`) was
`34s + 32s`, showing runner/cache variability. Therefore:

- confirmed benefit: one duplicate npm/uv audit and its duplicate setup/cache work are removed on
  PR profiles; security coverage remains split between one dependency job and one Trivy job;
- observed job-wall sum for successful jobs was 4,325s after versus 4,541s in reference run
  `39435906918`, but this is aggregate job wall, not processor time, and is not a stable speed claim;
- stable full-CI acceleration: `NOT_PROVEN` pending more comparable post-change runs;
- cache hit-rate improvement: `NOT_PROVEN`; GitHub connector did not expose the `cache-hit` log
  values, so no cache-based green shortcut was introduced.

## Preserved gates and risks

- Required `checks` still fails on missing, skipped or failed expected jobs; the Python contract now
  also rejects an empty expected set and an expected set without `scope-router`.
- All PR profiles require exactly one router-owned `dependency-audit`; package-manifest routing no
  longer appends a redundant specialized audit group when the full audit is already required.
- CodeQL, Trivy vulnerability/misconfiguration/secret scanning, policy, provenance/container
  contracts, PostgreSQL integration and branch-protection job names remain present.
- No production application, PostgreSQL gate #848, Dockerfile, SBOM, digest pinning, deploy workflow,
  paid runner or controller/state mechanism was changed.

## Remaining gates

The PR is open and unmerged. The receipt commit itself must be pushed and rerun through exact-head
Checks before final status is reported. Merge, production deploy, release approval and Issue #821
closure remain separate owner-authorized decisions.
