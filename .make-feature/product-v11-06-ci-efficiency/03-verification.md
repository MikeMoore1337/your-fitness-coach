# Product V11-06 / Issue #821 — verification receipt

Status: final receipt exact-head green; PR remains open for owner merge/release gates
PR: [#1136](https://github.com/MikeMoore1337/your-fitness-coach/pull/1136)
Final receipt HEAD: `328875bdbe615ca651ab6af5525c92a68441ccbd`

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

Final run [39458428445](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39458428445)
completed successfully for `328875bdbe615ca651ab6af5525c92a68441ccbd`. The preceding implementation
run [39457145434](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39457145434)
also completed successfully for the prior code-only SHA.

- Run wall: 524 seconds (`2026-10-20T16:33:04Z` to `2026-10-20T16:41:48Z`).
- Observable run-level queue component: 0 seconds (`created_at == run_started_at`). The first
  router job started at 16:24:27Z; later runner allocation is visible in job timestamps, but
  GitHub exposes no processor/billing CPU seconds: `PROCESSOR_TIME=NO_DATA`.
- Actions job API: 31 jobs; 28 success, 3 expected skipped, 0 failed. Skips were the PR-inapplicable
  extended mobile, weekly cross-browser and scheduled report jobs.
- Aggregate `checks`: success at 16:41:47Z, 18 seconds.
- CodeQL Python and JavaScript/TypeScript: success.
- Free PR security audit / Trivy: success.
- Dependency audit: success, one job, 28 seconds.
- Five Python shards: 245, 262, 281, 294, 309 seconds.
- Five frontend smoke shards: 261, 281, 312, 313, 366 seconds.
- PostgreSQL migrated stack, mobile regression, workflow contracts, policy, critical smoke and
  all four container jobs: success.
- Artifacts: 8 artifacts, 67.09 MiB; this is not an upload CPU measurement. Docker/container
  artifacts remain #851 scope.

## Before/after interpretation

The 20-run pre-change sample had 17 successes, one cancelled scheduled run and two failures; its
all-event median wall was 468 seconds. Comparable recent 31-job cross-stack PRs ranged from
372–527 seconds (historical references included 763 seconds). The two post-change observations
were 409 seconds for the code-only run and 524 seconds for this final receipt run; the closest
same-day 31-job reference `39435906918` was 419 seconds. This confirms substantial runner/cache
variation and does not prove a stable wall-time speedup.

The duplicated operation is proven removed by the final job shape. Before, run `39435906918` had
`Free PR security audit=136s` with setup plus the shared dependency audit and a separate
`Dependency audit=33s`; the code-only after run had `Free PR security audit=29s` and
`Dependency audit=43s`; the final receipt run has `32s` and `28s`. The security job contains
checkout plus Trivy only, and the dependency job is the sole npm/uv audit owner. A second baseline
(`39245697126`) was `34s + 32s`, showing runner/cache variability. Therefore:

- confirmed benefit: one duplicate npm/uv audit and its duplicate setup/cache work are removed on
  PR profiles; security coverage remains split between one dependency job and one Trivy job;
- observed successful-job wall sums were 4,325s in the code-only after run and 4,391s in the final
  receipt run versus 4,541s in reference `39435906918`; these are aggregate job wall, not processor
  time, and are not a stable speed claim;
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

The PR is open and unmerged. Final exact-head Checks are green. Merge, production deploy, release
approval and Issue #821 closure remain separate owner-authorized decisions.
