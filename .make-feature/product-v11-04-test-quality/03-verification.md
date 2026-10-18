# Product V11-04 / Issue #819 — verification receipt

Status: local verification complete; Draft PR/CI pending
Exact HEAD: pending commit
Draft PR: pending
Issue comment: pending

## Acceptance receipts

| Criterion | Command/action | Result | Evidence |
|---|---|---|---|
| Current baseline rechecked | live Issue/PR/Actions read-back plus local inventory | confirmed | 155 unit files; 78 E2E specs / 126 E2E files; 179 Python test files; 9 frontend conditional skips; 22 Python skip/skipif lines; 0 xfail lines |
| Test-quality audit completed | source/fixture/workflow review | confirmed | auth/session, tenant/RBAC/privacy, mutations, recovery, nutrition/programs/coach, PostgreSQL, mobile/TMA and localization matrix in `02-solution.md` |
| Confirmed test gaps fixed | two test-only changes | confirmed locally | mobile selector excludes intentional `WeekStrip` scroll-rail buttons; export download-link cross-user denial asserts `404` |
| Mobile failure classified | scheduled run `39111015160` logs | confirmed | Firefox + WebKit and retry share deterministic `left=-4` geometry; not flaky and not a product overflow |
| Skips/xfails classified | static source inventory | confirmed | frontend skips are opt-in evidence/fixture-origin; Python skips are host capability or PostgreSQL-lock conditional; no xfail |
| Focused tests | `run_pytest.py backend/tests/test_account_lifecycle.py -q` and risk set | passed | 7 passed; 78 passed, 2 PostgreSQL-only skipped |
| Full available regression | `npm test -- --reporter=dot`, `npm run lint`, Playwright `--list` | passed/blocked split | 155 files / 949 tests passed; lint passed; 2 extended tests listed; browser execution unavailable locally |
| Exact-head CI | pending | pending | pending |
| Draft PR and Issue comment | pending | pending | pending |

## Boundaries

Production runtime, physical iPhone/Safari, native Telegram, VoiceOver, and unavailable Docker/PostgreSQL/Windows-blocked suites are not accepted as verified without direct evidence. Local `docker compose ps` could not connect to Docker Desktop; CI remains the PostgreSQL/browser evidence path.
