# YFC Codex skills v8 - focused contracts

Skills задают профессиональный способ выполнения работы. Role задаёт ответственность прохода, task - scope и результат.

## Базовые правила

1. `Рекомендуемые skills` task - core skills primary role.
2. `Условные skills` открываются только при фактическом trigger.
3. Skill не расширяет scope.
4. Для обычной implementation task держи примерно 2-5 core skills.
5. QA: `$qa-engineer` как strategy/router + обычно не более 1-2 профильных skills.
6. Не создавать отдельного lifecycle agent на каждый skill или QA-профиль.
7. Большой end-to-end scope координирует role `orchestrator`, а не специальный meta-skill.
8. QA work profiles описаны в `references/QA_AUTOMATION_ARCHITECTURE.md`; это modes существующих roles.
9. `commercial-product-builder` удалён как дублирующий orchestration/lifecycle.
10. Отдельного `ai-engineer` нет: AI/LLM/AI Coach scope принадлежит `$llm-engineer`.
11. `$ui-prototyper` используется только явно для design exploration.
12. `$motion-design-engineer` используется для существенного motion design/implementation/review.
13. `$ru-legal-risk` обязателен для dedicated legal-risk audit и условен для обычной feature task по trigger.

## QA v8

QA разделён на strategy и узкие рабочие контракты:

- `qa-engineer` - risk strategy/router;
- `playwright-testing` - browser implementation;
- `e2e-review` - доверие к E2E/false-green review;
- `pytest-test-design` - Python test design;
- `api-testing`, `database-validation`, `pydantic-contracts` - boundary contracts;
- `test-data-management` - deterministic fixtures/data;
- `allure-reporting` - evidence/report quality;
- `failure-triage` - конкретное падение;
- `flaky-analysis` - intermittent failures;
- `coverage-analysis` - risk/behavior gaps.

UI visual/product audit остаётся отдельным `$ui-audit`.

## Design

Для обычных задач текущая production design system остаётся baseline.
Для owner-approved redesign task дизайн может быть пересмотрен при сохранении YFC anchors:
sport-tech, mobile-first, lime/black/white, product truth, accessibility, usability, performance.

См.:

- `references/SKILL_ROUTING_GUIDE.md`;
- `references/ROLE_ROUTING_GUIDE.md`;
- `references/QA_AUTOMATION_ARCHITECTURE.md`;
- `references/DESIGN_GUARDRAILS.md`.
