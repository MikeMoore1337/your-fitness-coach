# Request

YFC Issue #1099: исправить смещение активной тренировки при вводе веса и повторений через
цифровую клавиатуру iOS. Проверить актуальный `master`, воспроизвести сценарий с таймером отдыха,
вводом `50` и `12`, autosave/server ACK, повторным вводом, ручным скроллом, изменением
`visualViewport`, reload, offline→online и переходом к следующему подходу.

Нужно доказать конкретную первопричину, внести минимальное исправление без отключения autosave,
ResizeObserver или viewport handlers, добавить Playwright-регрессию, проверить 320/360/393/430 px,
Dark/Light, Chromium/WebKit, создать отдельный Draft PR для #1099 и подготовить реальные
BEFORE/AFTER материалы. Не менять PR #1098, не выполнять merge/deploy до явного owner approval.

Источник: https://github.com/MikeMoore1337/your-fitness-coach/issues/1099

Оригинальная запись владельца из ChatGPT в Codex недоступна; доказательство строится на описании
Issue и воспроизводимом synthetic/browser сценарии, без заявления о просмотре записи.
