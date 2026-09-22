# Skill routing guide v8

## Принцип

Skill = профильный рабочий контракт.
Role = ответственность lifecycle.
Task = scope и результат.

Не компенсируй слабую маршрутизацию загрузкой всех skills.

## Основные маршруты

| Изменение | Обычно достаточно | Добавлять при trigger |
| --- | --- | --- |
| Обычный React UI | `$frontend-engineer` | `$product-designer` при реальном UX/visual decision |
| Client-facing smartphone UI | `$frontend-engineer` | `$mobile-engineer` при keyboard/safe-area/lifecycle/device runtime; `$product-designer` при composition decision |
| Существенный motion | `$motion-design-engineer` + implementation skill | `$apple-design` при Apple-like physical/gesture trigger; perf/a11y по риску |
| Design exploration | `$product-designer` + explicit `$ui-prototyper` | landing/apple/motion по фактическому scope |
| UI audit | `$ui-audit` | apple/motion/a11y/perf только по риску |
| Backend/API | `$backend-engineer` | python/data/security/privacy по границе |
| Python | `$python-engineer` | domain skill по фактическому коду |
| DB/schema/query | `$data-engineer` | backend/privacy по contract/lifecycle |
| Telegram Bot/TMA platform API | `$telegram-engineer` | mobile для smartphone runtime; security при trust boundary |
| AI Coach / LLM | `$llm-engineer` | backend/python/fitness/privacy/security/evidence/analytics/observability по scope |
| Юридический риск РФ | `$ru-legal-risk` | privacy/security/data/AI/billing/Telegram/technical writing по поверхности |
| Product discovery | `$product-discovery` | `$ux-researcher` для real-user evidence |
| Release | `$release-manager` + `$platform-engineer` по необходимости | observability/security/privacy по реальному release risk |
| QA strategy | `$qa-engineer` | обычно 1-2 QA/domain skills ниже |
| Playwright/Web/TMA tests | `$qa-engineer` + `$playwright-testing` | `$e2e-review` для critical/new/AI-generated E2E trust review |
| pytest tests | `$qa-engineer` + `$pytest-test-design` | data/api/db/pydantic по boundary |
| API verification | `$qa-engineer` + `$api-testing` | pydantic/db/security/privacy по risk |
| DB verification | `$qa-engineer` + `$database-validation` | test-data-management при сложном state |
| Test data | relevant test skill + `$test-data-management` | только если fixtures/seeds/isolation существенны |
| CI/test failure | `$failure-triage` + framework skill | `$flaky-analysis` только при intermittent/retry signal |
| Flaky test | `$flaky-analysis` + framework skill | data/platform при подтверждённом trigger |
| Coverage audit | `$coverage-analysis` + `$qa-engineer` | domain skill для непонятного contract |
| Allure evidence | relevant test skill + `$allure-reporting` | не подключать только ради обычного pass/fail |

## QA profiles

См. `QA_AUTOMATION_ARCHITECTURE.md`.

`qa-architect`, `test-implementer`, `test-reviewer`, `ci-investigator`, `flaky-analyst`, `coverage-analyst` - рабочие профили, не lifecycle roles.

## Mobile engineer

Не загружай его только потому, что UI виден на телефоне.

Trigger:

- mobile keyboard;
- safe area;
- dynamic/stable viewport;
- foreground/background;
- reload/resume;
- offline/reconnect;
- touch/device-specific behavior;
- Mobile Web/TMA runtime parity;
- device performance.

Responsive layout сам по себе принадлежит `$frontend-engineer`.

## Apple Design

`$apple-design` - conditional reference skill для Apple/Liquid Glass/native-like interaction/material physics.
Он не заменяет YFC product design, accessibility, performance или product truth.

## UI prototyping

`$ui-prototyper` - explicit only.

## AI Coach

`$llm-engineer` - canonical AI/LLM skill.

## Бюджет контекста

- обычная implementation task: примерно 2-5 core skills;
- review/QA: `$qa-engineer` + обычно 1-2 профильных skills;
- audit/release: последовательные streams;
- failure investigation начинается с evidence и не требует загрузки всей QA-библиотеки;
- не загружать одинаковые общие правила из нескольких skills.
