# YFC: shadcn/ui + Magic UI - выборочное решение #1234

**Decision: REUSE_EXISTING.** Это проверка *исходников* на указанной ревизии PR, не новая оценка живого браузера. Аудит проведён по `frontend/package.json`, `src/shared/ui/common.tsx`, `tabs.ts`, `useModalA11y.ts`, `GlassInteractions.tsx`, `useSemanticMotion.ts`, `src/styles/design-system.css` и `liquid-glass.css`.

## Кандидаты и решение

| Внешний подход | Реальная потребность | Что уже имеется | Решение |
| --- | --- | --- | --- |
| shadcn/ui Dialog (Radix/Base UI) | Корректная клавиатура, Escape, фокус/scroll-lock у модальных экранов | `useModalA11y.ts`: стек диалогов, замыкание Tab, Escape, restore focus, scroll lock и Telegram Back | **REUSE_EXISTING**: внедрение второго слоя Dialog рискованно для Telegram, вложенных панелей и арендованных состояний |
| shadcn/ui Tabs / Button | Accessible keyboard/selection, controls внутри действующей формы | `common.tsx`: native button, role=tab, aria-selected, disabled; `tabs.ts`: Left/Right/Home/End; текущая тема black/lime, white/lime | **REUSE_EXISTING**, добавить повторяемую проверку клавиатурной навигации |
| Magic UI Magic Card (Motion) | Эстетичный локальный pointer highlight с учётом reduced motion | `GlassInteractions.tsx`: один делегированный pointer listener, rAF, pointer fine, no-touch, visibility/reduced-motion; `liquid-glass.css`: theme-specific CSS materials | **REUSE_EXISTING**, не устанавливать `motion` ради дубликата |
| Magic UI animated entrance | Осмысленные анимации состояний без прыжков | `useSemanticMotion.ts`, `useMotionPresence.ts`: фазовая анимация, visibility/reduced-motion, bounded fallback; существующие CSS-токены | **REUSE_EXISTING**, не добавлять декоративную глобальную анимацию |

## Совместимость и лицензирование

`shadcn-ui/ui` и `magicuidesign/magicui` содержат открытые компоненты, но копирование каждого отдельного файла требует подтверждения соответствующей лицензии и зависимостей. Текущий `frontend/package.json` - React 19, Vite 7, без `tailwindcss`, Radix/Base UI, `motion`. Введение их ради вышеперечисленного влечёт новый styling/runtime footprint, риски bundle/производительности, несовместимость токенов (Oswald/Inter, цветные состояния, safe-area, iOS/TMA) и потребует отдельного согласования. Ни одна внешняя реализация не включена, бинарные скрипты и автоматические инсталляторы не запускаются.

## Приёмка и эффект

- Изменения UI-геометрии, темы, дизайна, пользовательского поведения, маршрутов и production CSS: **0**.
- Новые runtime-зависимости: **0**; внешних компонентов **0**.
- Добавлены проверки **реального существующего** выбора вкладок клавиатурой, включая disabled; имеющиеся `Glass.test.tsx` продолжают проверять coalesced rAF, reduced-motion/touch и native button.
- Поэтому графика «до/после» и owner visual approval не требуются **для этого PR**, так как видимый продукт не меняется. Это не отменяет согласование будущего конкретного дизайна.
- Если в будущем выявится реальный gap (доказанный WCAG-дефект, задержки, отсутствие motion/state в конкретном экране), открыть scoped UI Issue с route, state, screenshots Dark/Light на 320/393/desktop, performance diff, проектной границей. Тогда проверить **ровно один** upstream компонент против имеющегося CSS/React, подготовить PNG/HTML и дождаться явного визуального approval **до UI-изменений**. Не использовать #1234 как обход этого gate.

**Честные границы:** проведён анализ исходников и CI регрессий, а не реальная диагностика на физическом iOS/TMA и не эмпирическое сравнение внешних библиотек. Вся текущая интеграция - уже имеющиеся компоненты, подтверждённые текстом и тестами. Это положительное решение **не добавлять** ненужные библиотеки, а не утверждение, что продукт идеален.
