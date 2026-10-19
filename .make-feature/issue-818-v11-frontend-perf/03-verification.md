# Make Feature verification — Product V11-03 / Issue #818

Status: READY_FOR_RELEASE_APPROVAL after corrected exact-head CI;
owner release approval, merge, deploy and Issue closure remain pending.

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
| Reduced-motion helper | Targeted Playwright regression | `2/2` passed; `0s`, `1e-05s`, `0.01ms` pass; `150ms`, mixed visible duration and malformed units fail |
| Reduced-motion media state | Targeted Playwright regression | `forced-colors: active` and `prefers-reduced-motion: reduce` both matched |
| Mobile Chromium + WebKit | Critical mobile regression suite | `48/52` passed; only Progress light/dark Chromium and Active Workout Chromium/WebKit baseline screenshots failed; functional/geometry checks passed |
| Warm/transition evidence | Opt-in profiles | completed; warm cache limitation is documented |
| Pre-commit | Source commit hooks | passed |
| CI contracts | `.venv\\Scripts\\python.exe -m pytest tests/test_ci_contract.py` | 53/53 passed |
| Previous PR-head CI | [run 39324048719](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39324048719) | aggregate failed only unchanged `progress-experience.spec.ts:2992` (`0s` vs `1e-05s`) |
| Corrected exact-head CI | [run 39329542165](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39329542165) | commit `8c9acec`; aggregate `checks` and all required jobs passed; extended/weekly suites skipped by routing |
| Evidence-only follow-up | Documentation-only commit after the green run | Must retain green required checks; no runtime files change |
| Field/device proof | Real device, Telegram WebView, CrUX/RUM, production traces | `NO_DATA` |

## Residuals

The `/app` lazy waterfall is fixed without weakening authorization or the entry budget. Small
Today/Programs residuals, variable Programs/Encyclopedia resource totals, local-preview warm
cache limitations and unavailable field/device evidence remain explicit. The proposed runtime
threshold is diagnostic only and is not an owner-approved SLA.
