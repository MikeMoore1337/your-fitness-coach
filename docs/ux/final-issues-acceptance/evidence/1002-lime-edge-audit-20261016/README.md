# Issue #1002 — доказательный аудит толстых односторонних лаймовых граней

Дата аудита: 2026-10-16. Базовая ревизия на старте: `origin/master` = `474d920d29e373043d4216586095ad7c90f7eb2e`.

Это подготовительный audit-only пакет. В приложенные исходники Web/PWA/TMA не внесены изменения; временный Playwright harness после сбора доказательств удалён. Issue #1002 остаётся `Backlog`, а owner visual approval, merge и deploy не выполнялись.

При финальной проверке live `origin/master` уже продвинулся до `34fee7003e0ea280abda9579194acb70dabd50bb` после merge PR #1013. Его diff затронул Progress hero/flow, но не изменил подтверждённые A-селекторы (`progress-report-*` или `.cardio-log`); поэтому Draft PR #1023 помечен GitHub как `BEHIND`. Перед реализацией A-правок нужно повторить exact-head computed check на актуальном master.

## Критерий классификации

Удаляемым считалась только асимметричная декоративная грань толщиной больше обычной рамки: отдельный `border-left/right/top/bottom`, выраженная inset-полоса или псевдоэлемент. Лаймовая рамка толщиной 1–2 px, `outline`, focus/active/selected/semantic state, CTA, иконка и текст сами по себе дефектом не считаются.

## Итог

- **A — 6 подтверждённых runtime-инстансов в 5 application-селекторах.** Это 1 desktop rail в overview, 1 factual summary, 1 program card, 2 exercise cards и 1 top edge в cardio log.
- **A\* — 1 подтверждённый AI Coach rail**, но он принадлежит пересекающейся области Issue #1003 и не должен меняться в этом worktree.
- **B — сохранены** обычные равномерные лаймовые рамки, включая профильный control и выбранный audience control Landing.
- **C — сохранены** active/current/selected/focus/semantic состояния: активная тренировка, выбранная точка графика, data confidence, success/attention/demo-boundary и wellbeing choices из PR #1000.
- **D — оставлены** неоднозначные или owner-approved композиции: Pulse insight/completion rails, auth explanatory context и source-only ветки без browser-confirmed fixture.

## Browser evidence

Финальные JSON-файлы содержат по **72 попытки capture** каждый для Chromium Dark/Light и WebKit Dark/Light. Проверены ширины `320`, `360`, `390`, `393`, `430` и `1440 px`; во всех четырёх наборах `horizontalOverflow = 0` для всех 72 попыток. Фактический DOM был доступен в 32/72 Chromium Dark, 30/72 Chromium Light и 24/72 в каждом WebKit наборе; остальные записи явно сохранены как loading/authorization attempts и не используются как доказательство селектора.

- Chromium Dark: `computed-chromium-dark.json` — локальный диагностический файл, не включён в публичный PR
- Chromium Light: `computed-chromium-light.json` — локальный диагностический файл, не включён в публичный PR
- WebKit Dark: `computed-webkit-dark.json` — локальный диагностический файл, не включён в публичный PR
- WebKit Light: `computed-webkit-light.json` — локальный диагностический файл, не включён в публичный PR

Представительные валидные BEFORE-скриншоты ниже именованы по сценарию, viewport, теме и browser. Остальные локальные диагностические captures не включаются в PR, чтобы не превращать evidence в 55 MB dump. Невалидные кадры, оставшиеся на loading-state, намеренно не связываются из этой матрицы.

### Подтверждённые A

| ID | Экран и фактическая грань | Селектор и источник | Точная будущая правка | BEFORE |
|---|---|---|---|---|
| A-01 | Progress report overview; desktop-only lime rail, `3 px` слева | `.progress-report-overview`, [`design-v2.css:410`](https://github.com/MikeMoore1337/your-fitness-coach/blob/474d920d29e373043d4216586095ad7c90f7eb2e/frontend/src/styles/design-v2.css#L410) | Удалить только `border-left`; не менять padding, token, фон или layout | Desktop computed evidence зафиксирован в [summary](./computed-summary.md); PNG не включён из-за pre-commit лимита 500 KB |
| A-02 | Progress report factual summary; `3 px` lime слева + равномерная нейтральная рамка `1 px` | `.progress-report-factual-summary`, [`design-v2.css:461`](https://github.com/MikeMoore1337/your-fitness-coach/blob/474d920d29e373043d4216586095ad7c90f7eb2e/frontend/src/styles/design-v2.css#L461) | Удалить только `border-left`; нейтральную рамку сохранить | [Dark 393 Chromium](./before/report-393-dark-chromium.png), [Light 393 Chromium](./before/report-393-light-chromium.png) |
| A-03 | Progress report program card; `3 px` lime слева | `.progress-report-program`, [`design-v2.css:571`](https://github.com/MikeMoore1337/your-fitness-coach/blob/474d920d29e373043d4216586095ad7c90f7eb2e/frontend/src/styles/design-v2.css#L571) | Удалить только `border-left` | [Dark 393 Chromium](./before/report-393-dark-chromium.png), [Light 393 Chromium](./before/report-393-light-chromium.png) |
| A-04 | Две карточки упражнений в report; `3 px` lime слева + нейтральная рамка `1 px` | `.progress-report-exercises article`, [`design-v2.css:590`](https://github.com/MikeMoore1337/your-fitness-coach/blob/474d920d29e373043d4216586095ad7c90f7eb2e/frontend/src/styles/design-v2.css#L590) | Удалить только `border-left`; рамку и структуру карточек сохранить | [Dark 393 Chromium](./before/report-393-dark-chromium.png), [Light 393 Chromium](./before/report-393-light-chromium.png) |
| A-05 | Today → Cardio quick entry; `3 px` lime сверху, остальные стороны нейтральные `1 px` | `.cardio-log`, [`design-v2.css:8723`](https://github.com/MikeMoore1337/your-fitness-coach/blob/474d920d29e373043d4216586095ad7c90f7eb2e/frontend/src/styles/design-v2.css#L8723) | Удалить только `border-top`; остальные грани сохранить | [Dark 393 Chromium](./before/today-cardio-393-dark-chromium.png), [Light 393 Chromium](./before/today-cardio-393-light-chromium.png), [Dark 1440 Chromium](./before/today-cardio-1440-dark-chromium.png), [Light 1440 Chromium](./before/today-cardio-1440-light-chromium.png) |

### A\* — подтверждено, но заблокировано пересечением #1003

| ID | Экран и фактическая грань | Селектор и источник | Решение на этом этапе | BEFORE |
|---|---|---|---|---|
| A\*-01 | Nutrition → contextual AI Coach; `3 px` lime слева, видимая карточка в synthetic fixture | `.ai-coach-contextual-entry`, [`ai-coach.css:38`](https://github.com/MikeMoore1337/your-fitness-coach/blob/474d920d29e373043d4216586095ad7c90f7eb2e/frontend/src/features/ai/ai-coach.css#L38) | Не менять в #1002: #1003 скрывает весь AI Coach UI. После #1003 повторно проверить, что карточка недоступна и rail не возвращается | [Dark 390 Chromium](./before/nutrition-390-dark-chromium.png), [Light 390 Chromium](./before/nutrition-390-light-chromium.png) |

## B — обязательно сохранить: нормальные рамки

- Профильный mobile control: равномерная лаймовая рамка `2 px` по четырём сторонам; это не односторонняя грань. [Dark](./before/profile-393-dark-chromium.png), [Light](./before/profile-393-light-chromium.png).
- Landing audience switch: равномерная выбранная рамка; сохраняется вместе с `aria-current`/selected semantics. Computed result зафиксирован в [summary](./computed-summary.md); oversized full-page PNG оставлен только в локальном raw evidence.
- Обычные `1 px` лаймовые рамки кнопок, карточек и меню не затрагиваются точечными будущими изменениями A-01…A-05.

## C — обязательно сохранить: state и доступность

- Active Workout: `.today-workout-focus__header` имеет нижнюю `2 px` лаймовую грань как часть текущего состояния; `.active-workout-set.is-current` имеет равномерную `1 px` рамку и `3 px` lime inset shadow. Это active/current contract, не декоративная рамка. Источники: [`design-v2.css:1740`](https://github.com/MikeMoore1337/your-fitness-coach/blob/474d920d29e373043d4216586095ad7c90f7eb2e/frontend/src/styles/design-v2.css#L1740), [`design-v2.css:2533`](https://github.com/MikeMoore1337/your-fitness-coach/blob/474d920d29e373043d4216586095ad7c90f7eb2e/frontend/src/styles/design-v2.css#L2533). [Dark](./before/today-active-393-dark-chromium.png), [Light](./before/today-active-393-light-chromium.png), [WebKit Dark](./before/today-active-393-dark-webkit.png), [WebKit Light](./before/today-active-393-light-webkit.png).
- Progress success rail `.app-section--progress .progress-insights__column--good` (`ux-ia-redesign.css:571`), selected data point `.data-viz-chart__selection` (`data-viz.css:239`) и `.progress-report-confidence` (`design-v2.css:11609`) являются success/selection/data-completeness semantics; их не удалять.
- Demo current/safety/conversion edges (`demo.css:160,182,302,331,358`, `demo-cabinet.css:22,75`) сохраняются как synthetic/demo state. [Dark](./before/demo-393-dark-chromium.png), [Light](./before/demo-393-light-chromium.png).
- Wellbeing selected choice из PR #1000 сохранён: `box-shadow: none`, выбранная рамка и focus outline остаются независимыми. Текущее правило: [`design-v2.css:4339`](https://github.com/MikeMoore1337/your-fitness-coach/blob/474d920d29e373043d4216586095ad7c90f7eb2e/frontend/src/styles/design-v2.css#L4339).
- Focus outlines, `:hover`, `:active`, `:focus-visible`, selected nav insets, semantic warning/attention rails и lime CTA не являются кандидатами на глобальное обнуление.

## D — неоднозначно, оставить до решения владельца

- Owner-approved Pulse composition: `.progress-body-metric--data-insight` (`pulse-concepts.css:39`, `7 px`) и `.workout-completion__hero` (`design-v2.css:2803`, затем Pulse override). Это может выглядеть как rail, но входит в утверждённый Pulse visual language; автоматическое удаление нарушит дизайн.
- Auth explanatory context: `.login-demo-context` (`auth.css:410`) и `.login-auth-heading > p:last-child` (`auth.css:443`) имеют односторонний lime accent, но это публичный explanatory context, а не однозначный случай из A. Оставлены без изменения до owner decision.
- Source-only или неактивные в текущем synthetic fixture ветки (`nutrition-report-coverage`, `program-history-workout`, Coach OS notes, trainer capability, legacy `.day-card`, exercise-guide/weekly-review variants) не объявляются исправленными без отдельного runtime evidence.

Representative non-defect screens: [Progress Dark](./before/progress-393-dark-chromium.png), [Progress Light](./before/progress-393-light-chromium.png), [Progress history Dark](./before/progress-history-393-dark-chromium.png), [Progress history Light](./before/progress-history-393-light-chromium.png), [Coach Dark](./before/coach-393-dark-chromium.png), [Coach Light](./before/coach-393-light-chromium.png), [Login Dark](./before/login-393-dark-chromium.png), [Login Light](./before/login-393-light-chromium.png).

## Пересечение с Issue #1003

На момент аудита у #1003 нет branch/PR и нет фактического diff; Issue остаётся открытым. Его заявленная область затрагивает как минимум:

- `frontend/src/features/ai/ai-coach.css`;
- `AiCoachContextualEntry.tsx`, `AiAdaptationProposal.tsx`, `AiCoachExperience.tsx`, `AiCoachWorkspace.tsx`;
- `MiniAppPage.tsx`, `WorkoutCompletionSummary.tsx`;
- AI/TMA/coach visual E2E fixtures.

Поэтому A\*-01 зафиксирован доказательно, но CSS не менялся. После завершения #1003 нужно проверить его скрытое состояние и только затем закрыть вопрос о видимом AI rail; конкурентную правку в этот пакет не добавлять.

Отдельно существует Draft PR #1013 по Progress (`head=86d8e9ed49906bbdf477dde3996077730e1b190a`); он не изменялся и не должен получать конкурентную правку тех же Progress selectors.

## Минимальный план следующего этапа

После завершения #1003 и owner visual gate:

1. Внести только пять точечных изменений: удалить `border-left` в A-01…A-04 и `border-top` в A-05.
2. Не менять палитру, токены, общую толщину рамок, радиусы, box-shadow других состояний, псевдоэлементы и layout.
3. Для каждого селектора добавить targeted computed assertion: запрещённая сторона не должна быть lime и быть толще обычной рамки; не вводить глобальное правило `border: 0`, `box-shadow: none` или `outline: none`.
4. Повторить Dark/Light, Chromium/WebKit, widths `320/360/390/393/430/1440`, Web/PWA/mock TMA, keyboard focus и `scrollWidth <= innerWidth`; отдельно повторить active workout, set cards, wellbeing и скрытие AI Coach.
5. Получить реальные AFTER captures на exact SHA, затем отдельно пройти owner visual acceptance, merge и deploy approval.

## Ограничения доказательств

Все данные в этом пакете synthetic/test-only. Physical iPhone/Safari, native Telegram, VoiceOver, production credentials/traffic и production runtime не проверялись. WebKit подтвердил active-workout smoke, но report/Nutrition/Cardio WebKit captures в этом прогоне не вышли из loading-state и потому остаются `NOT_PROVEN`; для них нужны повторные captures после исправления fixture/wait. AFTER-скриншотов, owner acceptance, merge и deploy пока нет. Ранний mobile regression smoke имел только baseline mismatch Progress golden (Light 741 px / 0.01, Dark 716 px / 0.01); goldens не изменялись и этот результат не объявляется исправлением #1002.
