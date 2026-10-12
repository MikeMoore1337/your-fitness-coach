# PR #963 — acceptance matrix

Срез этой матрицы относится только к техническому завершению PR #963. Контрольный HEAD для
текущей baseline-сверки: `3e7fb0743df127a11505c25fbc48ddb1687393a8`. Точный SHA candidate и
required Checks публикуются в комментарии PR после завершения CI.

| Область | Статус в PR #963 | Доказательство | Оставшееся условие |
|---|---|---|---|
| #865, «О показателях» | `IMPLEMENTED_VERIFIED` | Одобрено владельцем `OWNER_865_VISUAL_APPROVAL=GRANTED`; обновлены только четыре Linux Chromium/WebKit goldens `progress-390x844-{dark,light}.png`; thresholds не менялись | Required CI на exact HEAD; отдельное разрешение на merge/release |
| #871, вариант B | `IMPLEMENTED_VERIFIED` | `OWNER_871_POLICY_APPROVAL=GRANTED_B`; server/client timezone guard, сохранение формы, race/dedupe; pytest, Vitest, Web/PWA/TMA Playwright | Required CI на exact HEAD; существенная новая визуальная переработка не заявлялась |
| #874, числовая parity | `TECHNICAL_CANONICAL_FIX_VERIFIED / VISUAL_OWNER_APPROVAL_PENDING` | Canonical JSON приведён к одному первичному набору фактов; добавлены cross-field invariants и негативная проверка drift; API/server PDF, UI/browser PDF используют согласованные training/nutrition/body/adherence/data-sufficiency значения; empty, one-record и privacy gates сохранены | Owner approval конкретного визуального пакета (компактная полнота данных, one-record/empty states, цветной PDF и pagination), затем implementation/re-audit; required CI на новом exact HEAD; production/real-user proof не заявляется |
| #869/#870 | `PRESERVED` | Интегрированный код и существующие проверки не переписывались | Не расширять scope PR #963 |
| #914 | `PRESERVED` | Таймер отдыха, safe-area и защита от перекрытий сохранены; повторная интеграция не выполняется | Не расширять scope PR #963 |
| #946–#948 | `PRESERVED` | Утверждённый вариант поиска и keyboard states сохранены | Не расширять scope PR #963 |
| Пятиэлементная нижняя навигация | `PRESERVED / OWNER_APPROVED` | Существующий approved dock сохранён; отдельный floating `+` не добавлялся | Не запрашивать повторное визуальное согласование при неизменном результате |
| PR #966 | `ALREADY_INTEGRATED` | Уже является ancestry PR #963; повторная интеграция запрещена | Не cherry-pick/merge повторно |

## Release gates

`MERGE=WAITING_OWNER_APPROVAL` · `DEPLOY=WAITING_OWNER_APPROVAL` · `AUTO_MERGE=DISABLED` ·
`OWNER_VISUAL_APPROVAL=REQUIRED_FOR_NEW_VISUAL_CHANGES` · `env change required: no`.

Issues не закрываются этим техническим коммитом. После зелёного aggregate `checks` на точном
HEAD требуется отдельное разрешение владельца на merge/deploy.

## Текущая визуальная сверка #874

На контрольном HEAD production UI ещё не изменялся. Поэтому зафиксированы как открытые
визуальные наблюдения, а не как исправленные критерии:

- три повторяющиеся большие карточки «Данных достаточно для оценки» занимают значительную
  высоту до основных результатов;
- в one-record состоянии повторяется одна и та же первая/последняя сессия;
- пустые окружности сохраняют заголовок таблицы без строк;
- browser PDF имеет пять страниц с заметным свободным местом и короткой последней страницей.

Подготовлен локальный proposal-only пакет BEFORE/AFTER для компактной полноты данных,
one-record/empty states, цветного print/PDF и pagination. Он не является owner approval,
не публиковался в GitHub и не меняет production UI.
