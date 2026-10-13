# #969 — выход из быстрых форм

Актуальный срез для отдельного Draft PR по #969. Скриншоты — реальные браузерные снимки mocked-сценариев с синтетическими данными; исторические доказательства не изменяются.

## Что изменено

- «Сон и настроение»: в embedded-форме есть явная кнопка `Вернуться`; для локального открытия — `Отмена`. При dirty-состоянии сначала показывается подтверждение. Quick Add возвращает пользователя в «Сегодня» и восстанавливает фокус на исходном trigger.
- «Замер»: deep-link `focus=measurements` получает явную кнопку `Вернуться` в существующем embedded-редакторе. Dirty draft не отправляется в историю: перед выходом показывается подтверждение, после подтверждённого выхода draft остаётся в уже существующем scoped `localStorage` и восстанавливается при повторном открытии.
- Для редактирования существующего замера «Отменить изменение» также защищено подтверждением. Общий dock внутрь форм не добавлялся.

API, DB, миграции и структура данных не изменялись.

## BEFORE / AFTER

Baseline снят на актуальной на момент работы ветке #967 `b8d93c360fb484365b12741d3914408941792539`: #969 ещё не имел отдельного выхода. Для замера baseline использует тот же существующий embedded-редактор на 360×800; AFTER снят в quick-entry deep-link на той же ширине.

### Сон и настроение, 390×844

| Движок | BEFORE | AFTER |
| --- | --- | --- |
| Chromium | [Light](before-chromium-wellbeing-light-390x844.png), [Dark](before-chromium-wellbeing-dark-390x844.png) | [Light](after-chromium-wellbeing-light-390x844.png), [Dark](after-chromium-wellbeing-dark-390x844.png) |
| WebKit | — | [Light](after-webkit-wellbeing-light-390x844.png), [Dark](after-webkit-wellbeing-dark-390x844.png) |

### Замер, 360×800

| Движок | BEFORE | AFTER |
| --- | --- | --- |
| Chromium | [Light](before-chromium-measurement-light-360x800.png) | [Light](after-chromium-measurement-light-360x800.png), [Dark](after-chromium-measurement-dark-360x800.png) |
| WebKit | [Light](before-webkit-measurement-light-360x800.png) | [Light](after-webkit-measurement-light-360x800.png), [Dark](after-webkit-measurement-dark-360x800.png) |

Дополнительные AFTER-снимки 390×844: [Chromium](after-chromium-measurement-light-390x844.png), [WebKit](after-webkit-measurement-light-390x844.png), Dark-варианты доступны рядом в этой папке.

## Проверки

- Chromium/WebKit: wellbeing quick exit + measurement quick exit — `4 passed`.
- Chromium/WebKit: существующие measurement add/edit/history и Mobile Web/TMA parity — `4 passed`.
- TypeScript typecheck, Russian UI guard, production build и pre-commit — passed.
- Физический iPhone/Safari, настоящий Telegram-клиент и VoiceOver — `NOT_VERIFIED`.

`OWNER_VISUAL_APPROVAL=PENDING; MERGE=FORBIDDEN; DEPLOY=FORBIDDEN`
