---
name: qa-engineer
description: >
  Build risk-based QA strategy and route verification to focused testing skills.
  Use when behavior changes, regressions must be prevented, release confidence is
  required, or the appropriate test layer is unclear. Prioritize critical user
  journeys and trustworthy evidence over raw test count.
---

# qa-engineer

Это QA strategy/router, а не энциклопедия каждого тестового инструмента.

## Сначала

Определи:

- критические пользовательские сценарии;
- бизнес-инварианты;
- security/privacy-sensitive paths;
- integration boundaries;
- high-change/high-risk areas;
- какой уровень тестирования даст самый дешёвый надёжный сигнал;
- какой evidence нужен для утверждения, что риск действительно закрыт.

## Уровни

Используй подходящий баланс:

- unit - чистая логика;
- integration - БД/очереди/границы;
- API/contract - внешние и внутренние контракты;
- component/UI - поведение интерфейса;
- e2e - небольшое число критических сквозных потоков;
- visual regression - стабильные критические представления при существенном визуальном риске;
- accessibility - автоматические проверки плюс keyboard/focus verification для важных потоков.

Не дублируй один сценарий без причины на каждом уровне.

## Routing

Подключай профильные skills только по фактическому риску:

- Playwright/Web/TMA -> `$playwright-testing`;
- доверие к E2E и false-green risk -> `$e2e-review`;
- pytest/unit/integration design -> `$pytest-test-design`;
- API contracts/HTTP behavior -> `$api-testing`;
- SQL/DB persistence/migrations -> `$database-validation`;
- fixtures/factories/seed/isolation -> `$test-data-management`;
- Pydantic/schema validation -> `$pydantic-contracts`;
- Allure evidence/report structure -> `$allure-reporting`;
- конкретное падение/CI failure -> `$failure-triage`;
- intermittent/flaky behavior -> `$flaky-analysis`;
- пробелы risk/behavior coverage -> `$coverage-analysis`.

Обычно достаточно base skill + 1-2 профильных skills.

## Обязательные риски

Проверяй по применимости:

- validation boundaries;
- auth/authz;
- negative/error paths;
- retries/idempotency;
- concurrency/races;
- timezone/date boundaries;
- empty/null/large inputs;
- external dependency failures;
- migrations и backward compatibility;
- loading/error/empty/recovery states;
- privacy-sensitive export/deletion/telemetry flows.

## Mobile/TMA continuous gate

Для client-facing YFC task используй `references/MOBILE_TMA_ACCEPTANCE_MATRIX.md` и общий harness task `50A`.

Минимум:

- `360x800`, `390x844`, `430x932`;
- touch и `hover: none`;
- no horizontal overflow и touch-target review;
- keyboard/focus/safe-area/stable viewport;
- light/dark/reduced motion;
- reload/background/offline/reconnect, если flow хранит состояние;
- Mobile Web и mocked TMA parity;
- desktop regression.

Разделяй evidence:

1. automated Mobile Web;
2. mocked TMA adapter;
3. real Telegram Android;
4. real Telegram iOS;
5. непроверенные среды.

Не выдавай narrow desktop viewport за real-device verification.

## Test trust

Количество зелёных тестов не является самостоятельным доказательством качества.

Для критических новых или существенно изменённых E2E сценариев проверь:

- соответствует ли assertion заявленному intent;
- может ли тест пройти при сломанной feature;
- доказан ли side effect/persistence, если это часть обещания;
- не маскируют ли retry/skip/conditional branch проблему;
- не проверяется ли только optimistic UI вместо реального результата.

## Адаптация к проекту

Перед запуском найди существующие scripts, wrappers, configs, CI quality gates и artifact directories.
Используй их вместо выдуманных команд.
