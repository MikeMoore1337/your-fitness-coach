# Product V11-06 / Issue #821 — measured decision and change plan

Status: baseline measured; implementation selected; exact-head after receipt pending

## Baseline evidence

The live GitHub Actions sample contains 20 completed `CI` runs. It includes 17 successes, one
cancelled scheduled run and two failures. For comparable PR-style cross-stack runs, wall time
from `created_at` to `updated_at` ranged from 372–527 seconds in the recent sample; the historical
cross-stack reference was 763 seconds and the frontend-only reference was 510 seconds.

The observed run-level queue component (`run_started_at - created_at`) had median 0 seconds and
maximum 566 seconds in the 20-run sample. It is not runner CPU time. GitHub's returned job records
expose status/steps but not processor time or billing CPU seconds, so processor time is `NO_DATA`.

Representative recent cross-stack runs:

| run | result | wall | max job | Python shards | frontend smoke | start spread |
|---|---:|---:|---:|---:|---:|---:|
| 39435906918 | success | 419 s | 344 s | 304–335 s | 280–344 s | 393 s |
| 39366352585 | success | 372 s | 305 s | 301–305 s | 262–289 s | 345 s |
| 39245697126 | success | 527 s | 364 s | 304–326 s | 271–364 s | 390 s |
| 39248645986 | success | 408 s | 358 s | 255–321 s | 268–358 s | 382 s |
| 39217415385 | success | 402 s | 354 s | 255–320 s | 277–354 s | 381 s |
| 39064430417 | success | 763 s | 398 s | 264–327 s | 286–398 s | 669 s |

The five Python shards collect 1,739 tests in the historical run (348 per shard) and use four
xdist workers. Recent frontend smoke uses five shards and two Playwright workers. The sample does
not prove a stable shard imbalance or a runner-account capacity fix. `npm ci` was about 5–6 seconds
per job and `uv sync` 0–6 seconds in the earlier evidence, so setup is not the critical path.

Observed artifact costs are dominated by existing runtime/container evidence rather than this
change: run `39435906918` published 8 artifacts / 63.67 MiB and run `39245697126` published 8 /
66.41 MiB. The scheduled cancelled run `39168451628` published 21 / 11.86 MiB, including 12.26 MiB
of Allure results. These values are artifact sizes, not upload CPU time. Dockerfile/SBOM/digest
work remains #851 scope.

The confirmed duplication is in `ci.yml`: on PRs `security-audit` performs the full shared
dependency audit, while the router also schedules the separate `dependency-audit` job for
cross-stack/dependency profiles. The security job's Trivy scan is independent and must remain.

## Chosen minimal change

1. Make `dependency-audit` a required group in every PR scope profile. This preserves the exact
   full npm + uv audit that `security-audit` previously ran for every PR, including frontend,
   backend, migration, workflow and documentation profiles.
2. Let that job depend only on `scope-router`, so its independent audit can run alongside quality.
3. Remove only the duplicate dependency setup/audit from `security-audit`; retain checkout,
   mandatory Trivy `vuln,misconfig,secret` scan and its required aggregate result.
4. Strengthen `verify_results` so an empty or malformed expected set cannot pass, and add negative
   tests for empty, missing, skipped and failed mandatory jobs plus profile routing.

## Affected-file matrix

| Surface | Change | Contract/test |
|---|---|---|
| `scripts/ci_contract.py` | PR profiles and aggregate validation | `tests/test_ci_contract.py` |
| `.github/workflows/ci.yml` | dependency-audit ownership and concurrency | workflow contract tests |
| `tests/test_ci_contract.py` | routing, single-owner audit and false-green negatives | targeted pytest |
| `.make-feature/product-v11-06-ci-efficiency/` | measured evidence/receipts only | deployment scope remains no-deploy |

No Dockerfile, SBOM, image digest, app, PostgreSQL, deploy workflow or parallel product scope is
changed.

## Rejected options

- Shard count/worker changes: the available runs do not prove a stable test imbalance, and prior
  4-worker E2E experiment was rejected after a reproducible failure.
- Combining frontend or Python jobs: it would serialize independent required checks and reduce
  failure isolation without proven wall-time benefit.
- Skipping browser/system installation on a cache hit: the cache does not contain runner-level
  system packages, so that would risk false green CI.
- Changing Docker/container or provenance jobs: explicitly owned by #851.
