# #969 — выход из быстрых форм

Исторический срез Draft PR #978 от 13 октября 2026 года, до production-релиза #991. Эти реальные браузерные снимки mocked-сценариев с синтетическими данными не подтверждают актуализированную реализацию поверх #991. Новые AFTER входят в единый финальный пакет legacy PR после интеграционного прогона; исходные файлы сохранены без изменений.


## Актуализация после #991, 14 октября 2026 года

Основа: `f99f1954c007567cefeec7dc882f14e68de6b0ba`. Актуальный master добавлен обычным merge в существующую ветку #978, без перезаписи истории. Новые правила выхода используют существующие компоненты подтверждения и Telegram BackButton.

- Сравнение замера учитывает пустые поля, нормализованный текст и порядок дополнительных показателей. Контекст редактирования восстанавливается вместе с локальным черновиком и не отправляется в API.
- При недоступном локальном хранилище подтверждение честно сообщает о потере значений. Незавершённое название дополнительного показателя также получает явное предупреждение.
- Удаление другой записи сохраняет текущий черновик. Удаление редактируемой записи предупреждает о потере её несохранённых изменений и очищает только соответствующий черновик.
- Выход и повторная отправка блокируются на время записи. Telegram BackButton проходит тот же guard; при открытом подтверждении Back отменяет только подтверждение и возвращает фокус.
- Локальные проверки: typecheck, lint с Russian UI guard, build, `git diff --check`, Prettier для изменённых frontend-файлов — PASS; адресные unit — 27 тестов / 3 файла; Chromium/WebKit — 32 сценария (26 новых + 6 существующих).
- Полный локальный `format:check` сообщает о 507 исходных CRLF-файлах в Windows checkout. Изменённые frontend-файлы проходят проверку; полный формат проверяет Linux CI актуального head.

Матрица новых сценариев: Mobile Web 320/360/390/393/430 px × Dark/Light × Chromium/WebKit; mocked TMA 390 px × обе темы и движка. Проверены пустой и изменённый ввод, отмена/подтверждение выхода, возврат фокуса, повторное открытие черновика, сохранение истории, редактирование и удаление без дублирующих запросов. Суженный viewport моделирует открытую клавиатуру; это не физическая экранная клавиатура.

Физический iPhone/Safari, настоящий Telegram, VoiceOver, OS-клавиатура и выгрузка/закрытие вкладки — `NOT_VERIFIED`. Новый глобальный browser-unload/history blocker не добавлялся. Это покрытие UI-кнопок и Telegram BackButton. Итоговые AFTER и совместная проверка публикуются одним интеграционным пакетом #959; снимки ниже остаются историческими.

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
