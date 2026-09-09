# YFC Codex skills v6 - focused contracts

Skills задают профессиональный способ выполнения работы. Role задаёт ответственность прохода, task - scope и результат.

## Базовые правила

1. `Рекомендуемые skills` task - core skills primary role.
2. `Условные skills` открываются только при фактическом trigger.
3. Skill не расширяет scope.
4. Для обычной implementation task держи примерно 2-5 core skills.
5. QA: base skill роли + обычно не более 1-2 профильных skills.
6. Не создавать отдельного агента на каждый skill.
7. Большой end-to-end scope координирует role `orchestrator`, а не специальный meta-skill.
8. `commercial-product-builder` удалён в v6 как дублирующий orchestration/lifecycle.
9. Отдельного `ai-engineer` нет: AI/LLM/AI Coach scope принадлежит `$llm-engineer`.
10. `$ui-prototyper` используется только явно для design exploration.
11. `$motion-design-engineer` используется для существенного motion design/implementation/review, а не автоматически для любой CSS transition.
12. `$ru-legal-risk` обязателен для dedicated legal-risk audit и подключается условно к обычной
    task только при фактическом legal trigger; он требует актуальных источников, не является
    гарантией compliance и не принимает owner decision.
13. Dedicated legal-risk audit использует primary role `product-lawyer`; remediation после owner
    decision возвращается в отдельную task с обычной implementation-ролью.

## Design v6

Для обычных задач текущая production design system остаётся baseline, чтобы не создавать случайный visual drift.

Для отдельной owner-approved design exploration/redesign task весь Design V2/V2.1 может быть пересмотрен.

Устойчивые YFC anchors:

- sport-tech;
- mobile-first для client-facing flows;
- lime + black + white как фирменное цветовое ядро;
- product truth;
- accessibility;
- usability;
- performance.

Эстетические приёмы не запрещаются по названию. Glow, gradients, glass, cards, 3D, bold motion и другие решения допустимы, если они усиливают YFC и не ломают пользовательскую задачу.

Запоминаемость, delight и "вау" - first-class критерии качества наряду с практичностью.

См.:

- `references/SKILL_ROUTING_GUIDE.md`;
- `references/ROLE_ROUTING_GUIDE.md`;
- `references/DESIGN_GUARDRAILS.md`.
- `skills/ru-legal-risk/references/RU_LEGAL_SOURCE_POLICY.md` для юридической source freshness.

Исторические overlap/release audits являются owner-only material и в public Git не публикуются.
