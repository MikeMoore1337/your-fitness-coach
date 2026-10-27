---
name: playwright-testing
description: >
  Design, implement and maintain reliable Playwright tests for YFC Web and TMA.
  Use for browser E2E, visual checks, responsive/mobile verification, auth,
  network evidence, fixtures, debugging and Playwright configuration.
---

# playwright-testing

Пиши Playwright-тесты, которые доказывают пользовательское поведение и дают понятный failure evidence.

## Baseline

- предпочитай semantic locators: role/label/name;
- CSS/test id используй, когда semantic contract недостаточен или проверяется geometry/style;
- используй web-first assertions и auto-wait;
- не используй фиксированные sleeps;
- каждый тест должен быть изолирован и не зависеть от порядка;
- shared setup оформляй через fixtures/helpers, а не module-level mutable state;
- URL/config/auth должны переиспользовать существующую project infrastructure;
- не добавляй новый fixture layer, если существующий YFC harness решает задачу.

## Test intent

Перед кодом сформулируй:

- Given: какое состояние гарантированно создано;
- When: какое пользовательское действие выполняется;
- Then: какой наблюдаемый результат обязан быть доказан.

Если сценарий обещает persistence/backend side effect, одного визуального изменения недостаточно.
Добавь доказательство request/response, persisted state или reload/re-entry по подходящему уровню.

## Locators

Приоритет:

1. `getByRole` с accessible name;
2. `getByLabel`;
3. устойчивый project-owned test id;
4. scoped text locator;
5. CSS только для структуры/geometry/visual contract;
6. XPath - только при обоснованной невозможности остальных вариантов.

Не превращай accessible copy в нестабильный глобальный substring selector.

## Assertions and waiting

- assertion должен проверять обещанное состояние, а не существование handle;
- после navigation/action жди нужный outcome, а не произвольную паузу;
- для запросов arm observer/interception до action;
- отсутствие элемента доказывай только после доказанного состояния, в котором он обязан исчезнуть;
- коллекцию сначала докажи непустой, если дальнейшие assertions проходят циклом по элементам.

## Network and mocking

- не mock собственный YFC слой только ради зелёного E2E, если цель теста - проверить сквозной contract;
- third-party dependencies можно стабилизировать через controlled mocks;
- optimistic UI mutation для критичного write-flow должна иметь call/persistence proof;
- учитывай offline/reconnect только когда это часть task/risk.

## Auth

Используй существующий auth fixture/storageState/setup project.
Не храни literal credentials в spec.
Protected-route тест обязан доказать, что проверяет нужную authenticated surface, а не fallback/login page.

## Mobile/TMA

Соблюдай YFC Mobile/TMA acceptance matrix.
Отдельно фиксируй automated viewport evidence и real Telegram evidence.
Проверяй keyboard, safe areas, touch, sticky layers, viewport resize, reload/resume, если применимо.

## Visual/geometry

Screenshot baseline полезен только для стабильного contract.
Для touch targets, overlap, clipping, centering и safe-area допустимы explicit geometry assertions.
Перед non-null geometry assertions убедись, что locator действительно должен быть rendered/visible.

## Failure evidence

При падении предпочитай существующие:

- trace;
- screenshot;
- video;
- Playwright report;
- request/console evidence.

Не чинить selector до выяснения, product defect это или test defect.
