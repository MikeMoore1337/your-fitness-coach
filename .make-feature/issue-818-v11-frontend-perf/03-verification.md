# Make Feature verification — Product V11-03 / Issue #818

Status: READY_FOR_RELEASE_APPROVAL after exact-head required CI; owner release approval,
merge, deploy and Issue closure remain pending.

| Criterion | Action | Result |
| --- | --- | --- |
| Matched bundle baseline | Build and `perf:check` on `42a75a5f` | 310,971 raw / 97,485 gzip; expected guard failure |
| PR before fix | Build/profile on `775cc734` | 295,985 raw / 92,971 gzip; Today 3,482 ms and Programs 3,096 ms p50 |
| Final bundle | Build and `perf:check` on `415b4e72` | 295,889 raw / 92,983 gzip; guard passed |
| CoachPage graph | Compare final manifest/chunk | 186,590 raw / 45,800 gzip; no return of the ~98 KB chunk |
| Lazy boundary | 10-run cold profile | Today -257 ms and Programs -23 ms versus PR before fix |
| API/auth behavior | Route profile + canonical query test | No new duplicates; Nutrition `/me` duplicate exists in all revisions |
| TypeScript/lint | `npm run typecheck`; `npm run lint` | passed |
| Unit behavior | `npm run test` | 157 files, 962 tests passed |
| Browser behavior | `performance-hardening.spec.ts` | Chromium 8/8 passed |
| Mobile Chromium | Critical mobile regression suite | 23/26 passed; 3 screenshot failures reproduced exactly on BEFORE |
| Mobile WebKit | Critical mobile regression suite | 25/26 passed; Active Workout screenshot failure reproduced on BEFORE |
| Warm/transition evidence | Opt-in profiles | completed; warm cache limitation is documented |
| Pre-commit | Source commit hooks | passed |
| Exact-head CI | PR #1126 after documentation commit | must be re-read before release approval |
| Field/device proof | Real device, Telegram WebView, CrUX/RUM, production traces | `NO_DATA` |

## Residuals

The `/app` lazy waterfall is fixed without weakening authorization or the entry budget. Small
Today/Programs residuals, variable Programs/Encyclopedia resource totals, local-preview warm
cache limitations and unavailable field/device evidence remain explicit. The proposed runtime
threshold is diagnostic only and is not an owner-approved SLA.
