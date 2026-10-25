# Issue #1162 — действия завершённого подхода в одну строку

Дата: 2026-10-25

## Итог

На завершённом подходе удалена отдельная раскрываемая кнопка «Действия». Кнопки
«Редактировать» и «Вернуть в работу» теперь видимы одновременно и размещаются в одной
компактной строке с touch-target не менее 44 px. Возврат по-прежнему требует явного
подтверждения; обычное редактирование сохраняет `is_completed`.

## Evidence

- [HTML-галерея](./index.html)
- `BEFORE`: реальный браузерный capture актуального `origin/master`
  `94a9b5f3875bae858d0ea816cc47fc9d22ae9dd0`, Chromium, 320/393 px, Dark/Light.
- `AFTER`: реальный browser capture кода из commit
  `534f5407df3d2a920fbce7a3a55aa2625d74c58f`, Chromium и WebKit, 320/360/393/430 px,
  Dark/Light.
- Fixture синтетический: подход 1 завершён со значениями `42.5 × 9`, подход 2 остаётся
  текущим; персональные данные не используются.

В AFTER показаны три фактических состояния новой компоновки:

1. завершённый подход с двумя прямыми действиями;
2. обязательное подтверждение возврата;
3. результат после возврата в работу.

Состояние «меню раскрыто» оставлено только в BEFORE: после удаления «Действия» такого
состояния в новой реализации нет.

Кадры — synthetic browser evidence. Они не подтверждают поведение на физическом устройстве,
в нативном Telegram Mini App, в production и не являются визуальным одобрением владельца.

## Проверки

- `npm run lint` — PASS.
- `npm run build` — PASS.
- `npm run test -- --reporter=dot` — `159 passed`, `991 passed`.
- #1162: Chromium `8/8` и WebKit `8/8`; 320/360/393/430 px, Dark/Light.
- #1162 long-title regression: Chromium `1/1` at 320 px.
- #980 completed-set regression: Chromium `24/24`, включая edit/reopen, geometry, keyboard и
  safe-area.
- UI audit: direct-action layout manually reviewed from real Chromium captures; material
  findings не обнаружены.

## Следующий gate

Нужен пакетный visual review владельца Issue #1162. Успешный CI и эта галерея не заменяют
визуальное одобрение, merge, production deploy, production smoke или закрытие Issue.
