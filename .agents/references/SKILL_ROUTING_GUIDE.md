# Skill routing guide v7

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
| Существенный motion | `$motion-design-engineer` + implementation skill | `$apple-design` при Apple-like physical/gesture trigger; `$performance-engineer` при подтверждённой стоимости; `$accessibility-engineer` при сложном reduced-motion/a11y |
| Design exploration | `$product-designer` + explicit `$ui-prototyper` | `$landing-art-director` для Landing; `$apple-design` при Apple/Liquid Glass/native-feel direction; `$motion-design-engineer` если motion является частью концепции |
| Landing | `$landing-art-director` + `$product-designer` | `$frontend-engineer` при реализации; SEO/performance только по scope |
| UI audit | `$ui-audit` | `$apple-design` только при аудите Apple/Liquid Glass/native-feel contract; `$motion-design-engineer` при существенном motion review; a11y/perf по риску |
| Backend/API | `$backend-engineer` | `$python-engineer` при Python implementation; data/security/privacy по границе |
| Python | `$python-engineer` | domain skill по фактическому коду |
| DB/schema/query | `$data-engineer` | backend/privacy по изменению contract/lifecycle |
| Telegram Bot/TMA platform API | `$telegram-engineer` | `$mobile-engineer` для smartphone runtime; security при trust boundary |
| AI Coach / LLM | `$llm-engineer` | backend/python для implementation; fitness/privacy/security/evidence/analytics/observability по scope |
| Юридический риск РФ | `$ru-legal-risk` | privacy/security/data/AI/billing/Telegram/technical writing только по фактической поверхности |
| Product discovery | `$product-discovery` | `$ux-researcher` только для real-user evidence |
| Release | `$release-manager` + `$platform-engineer` по необходимости | observability/security/privacy только по реальному release risk |

## `mobile-engineer` v6

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

## Motion

`$motion-design-engineer` нужен, когда task:

- создаёт/перерабатывает motion language;
- добавляет transition/gesture/data animation как заметную часть UX;
- проверяет качество существующих animations;
- ищет motion opportunities;
- выполняет dedicated motion hardening.

Одна короткая стандартная CSS transition не требует отдельного skill.

## Apple Design

`$apple-design` - условный reference skill для Apple-подобной interaction/material физики на web/TMA.

Trigger:

- Apple-style или Liquid Glass design direction;
- native-like mobile web/TMA interaction;
- translucent material/depth hierarchy;
- gesture-driven drag/swipe/sheet/drawer;
- spring physics, interruptibility, velocity handoff, momentum projection;
- rubber-banding или physical direct manipulation.

Не загружай его для обычной формы, layout fix, icon audit, backend task или короткой стандартной
transition только потому, что продукт должен выглядеть качественно.

Authority:

- `$product-designer` владеет YFC visual direction, composition и brand;
- `$motion-design-engineer` владеет production motion contract;
- `$apple-design` даёт Apple-specific interaction/material techniques и не превращает YFC в iOS clone;
- YFC sport-tech + lime/black/white anchors, task scope, accessibility, performance и product truth выше
  Apple-like reference patterns.

## UI prototyping

`$ui-prototyper` - explicit only.

Он не должен сам запускаться из обычной feature-task. Используй его, когда владелец хочет несколько действительно разных visual/interaction directions до production implementation.

## AI Coach

Не создавать `$ai-engineer`.

`$llm-engineer` - canonical AI/LLM skill для:

- provider decision/routing;
- AI Coach jobs;
- prompts;
- retrieval;
- tools;
- memory;
- safety;
- evals;
- product AI UX;
- provider reliability/cost/privacy.

## Удалённый skill

`commercial-product-builder` удалён. Крупный multi-stage scope координирует role `orchestrator`, подбирая реальные domain skills по streams.

## Legal risk РФ

`$ru-legal-risk` обязателен для dedicated legal-risk audit. В обычной feature/fix task он является
условным skill только при изменении персональных/health-related данных, external providers, AI,
payments, legal/consent UI, analytics/cookies, data residency, recommendation logic,
advertising/claims или external content licenses.

Skill готовит `SAFE / BALANCED / ACCEPT_RISK / AVOID`, recommendation, остаточный риск и
`LEGAL_COUNSEL_REQUIRED`, но не принимает решение за владельца и не превращает `HIGH` legal risk
в lifecycle blocker без отдельного task/release gate.

## Бюджет контекста

- обычная implementation task: примерно 2-5 core skills;
- review/QA: base skill роли + 1-2 профильных;
- audit/release: последовательные streams;
- не загружать одинаковые общие правила из нескольких skills, если один уже владеет областью.
