---
name: e2e-review
description: >
  Independently review Playwright/Cypress-style end-to-end tests for false greens,
  weak assertions, bypasses, hidden skips, missing side-effect proof and test smells.
  Use after AI- or human-written E2E changes and for trust audits of existing specs.
---

# e2e-review

Цель - ответить не "тест зелёный?", а "тест действительно доказывает заявленное поведение?".

## Review contract

Для каждого изменённого критичного E2E:

1. прочитай название/intent;
2. найди Given/When/Then;
3. определи, какое сломанное поведение должно сделать тест красным;
4. проверь, что assertions действительно ловят эту поломку;
5. проверь isolation, auth, data и runtime assumptions;
6. отдели introduced/worsened finding от pre-existing debt.

## P0 - false green / silent bypass

Ищи:

- название обещает результат, а assertion проверяет только видимость общего контейнера;
- action есть, meaningful Then отсутствует;
- swallowed errors;
- committed focused test;
- locator/Promise/boolean проверяется так, что assertion всегда или почти всегда true;
- conditional branch позволяет пропустить обязательную часть сценария;
- protected surface тестируется без гарантированного auth;
- optimistic UI принимается за доказательство backend write;
- critical check выполняется только внутри потенциально пустого цикла.

## P1 - надёжность и диагностика

Ищи:

- missing await;
- hard sleeps;
- unstable nth/substring selector без причины;
- unnecessary serial/shared state;
- retry скрывает воспроизводимую проблему;
- stale manually captured auth state без programmatic regeneration;
- force action без объяснения;
- direct selector API вместо locator contract;
- test data зависит от общего persistent environment.

## P2 - maintainability

Ищи:

- zombie/duplicate tests;
- unused helpers/POM methods;
- unjustified skip без причины/revisit condition;
- meaningless abstraction;
- чрезмерное дублирование проверки одного риска на одном уровне.

## Required evidence

Finding должен содержать:

- severity;
- spec/test;
- обещанный intent;
- фактическое доказательство;
- как тест может пройти ошибочно;
- concrete fix direction.

Не помечай pattern как defect автоматически. Контекст теста является источником истины.

## Scope

Этот skill проверяет качество E2E.
UI aesthetics принадлежат `$ui-audit`.
Playwright implementation patterns принадлежат `$playwright-testing`.
