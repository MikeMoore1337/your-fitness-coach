# Питание: сравнение реализации с макетом #1440

Исходный dev: [f1251b12](https://github.com/MikeMoore1337/your-fitness-coach/commit/f1251b12fcfbd5ebbf7728e2b62253523dba9fe3). Код проверяемой объединённой версии: [8bd5c7a0](https://github.com/MikeMoore1337/your-fitness-coach/commit/8bd5c7a0ca22784f1cf0f7110053b5f1feb481a6). Она включает изменения [#1482](https://github.com/MikeMoore1337/your-fitness-coach/pull/1482) и [#1483](https://github.com/MikeMoore1337/your-fitness-coach/pull/1483). Исходный принятый [макет с двумя лаймовыми кнопками](https://github.com/MikeMoore1337/your-fitness-coach/tree/37204e064a738f80a3428c81aa63130ea4feb60c/docs/ux-proposals/issue-1479/after).

Реальные рендеры локального приложения с синтетическими ответами API, не скриншоты production и не физические устройства. Одинаковый тестовый день и содержимое; возможны отличия из-за динамических состояний и изменений интерфейса. Chromium 151.0.7922.34 и Playwright WebKit 26.5, viewport: 844 px по высоте на мобильных размерах, 900 px на 1280; снимки полной страницы.

## Дневник: до и после

| Браузер | Тема | Ширина | До | После |
| --- | --- | ---: | --- | --- |
| chromium | light | 320 | [До](before/chromium-light-320.png) | [После](after/chromium-light-320.png) |
| chromium | light | 360 | [До](before/chromium-light-360.png) | [После](after/chromium-light-360.png) |
| chromium | light | 393 | [До](before/chromium-light-393.png) | [После](after/chromium-light-393.png) |
| chromium | light | 430 | [До](before/chromium-light-430.png) | [После](after/chromium-light-430.png) |
| chromium | light | 1280 | [До](before/chromium-light-1280.png) | [После](after/chromium-light-1280.png) |
| chromium | dark | 320 | [До](before/chromium-dark-320.png) | [После](after/chromium-dark-320.png) |
| chromium | dark | 360 | [До](before/chromium-dark-360.png) | [После](after/chromium-dark-360.png) |
| chromium | dark | 393 | [До](before/chromium-dark-393.png) | [После](after/chromium-dark-393.png) |
| chromium | dark | 430 | [До](before/chromium-dark-430.png) | [После](after/chromium-dark-430.png) |
| chromium | dark | 1280 | [До](before/chromium-dark-1280.png) | [После](after/chromium-dark-1280.png) |
| webkit | light | 320 | [До](before/webkit-light-320.png) | [После](after/webkit-light-320.png) |
| webkit | light | 360 | [До](before/webkit-light-360.png) | [После](after/webkit-light-360.png) |
| webkit | light | 393 | [До](before/webkit-light-393.png) | [После](after/webkit-light-393.png) |
| webkit | light | 430 | [До](before/webkit-light-430.png) | [После](after/webkit-light-430.png) |
| webkit | light | 1280 | [До](before/webkit-light-1280.png) | [После](after/webkit-light-1280.png) |
| webkit | dark | 320 | [До](before/webkit-dark-320.png) | [После](after/webkit-dark-320.png) |
| webkit | dark | 360 | [До](before/webkit-dark-360.png) | [После](after/webkit-dark-360.png) |
| webkit | dark | 393 | [До](before/webkit-dark-393.png) | [После](after/webkit-dark-393.png) |
| webkit | dark | 430 | [До](before/webkit-dark-430.png) | [После](after/webkit-dark-430.png) |
| webkit | dark | 1280 | [До](before/webkit-dark-1280.png) | [После](after/webkit-dark-1280.jpg) |

## Состояния на 393 px

| Браузер / тема | КБЖУ: ноль / неизвестно / выше цели | Вода: ручной ввод / история / отмена | Статус: закрыт / открыт / пусто / сохранение / ошибка |
| --- | --- | --- | --- |
| chromium / light | [zero](states/chromium-light-393-macro-zero.png) · [unknown](states/chromium-light-393-macro-unknown.png) · [excess](states/chromium-light-393-macro-excess.png) | [custom](states/chromium-light-393-water-custom.png) · [history-open](states/chromium-light-393-water-history-open.png) · [undo](states/chromium-light-393-water-undo.png) | [closed](states/chromium-light-393-status-closed.png) · [open](states/chromium-light-393-status-open.png) · [empty](states/chromium-light-393-status-empty.png) · [loading](states/chromium-light-393-status-loading.png) · [error](states/chromium-light-393-status-error.png) |
| chromium / dark | [zero](states/chromium-dark-393-macro-zero.png) · [unknown](states/chromium-dark-393-macro-unknown.png) · [excess](states/chromium-dark-393-macro-excess.png) | [custom](states/chromium-dark-393-water-custom.png) · [history-open](states/chromium-dark-393-water-history-open.png) · [undo](states/chromium-dark-393-water-undo.png) | [closed](states/chromium-dark-393-status-closed.png) · [open](states/chromium-dark-393-status-open.png) · [empty](states/chromium-dark-393-status-empty.png) · [loading](states/chromium-dark-393-status-loading.png) · [error](states/chromium-dark-393-status-error.png) |
| webkit / light | [zero](states/webkit-light-393-macro-zero.png) · [unknown](states/webkit-light-393-macro-unknown.png) · [excess](states/webkit-light-393-macro-excess.png) | [custom](states/webkit-light-393-water-custom.png) · [history-open](states/webkit-light-393-water-history-open.png) · [undo](states/webkit-light-393-water-undo.png) | [closed](states/webkit-light-393-status-closed.png) · [open](states/webkit-light-393-status-open.png) · [empty](states/webkit-light-393-status-empty.png) · [loading](states/webkit-light-393-status-loading.png) · [error](states/webkit-light-393-status-error.png) |
| webkit / dark | [zero](states/webkit-dark-393-macro-zero.png) · [unknown](states/webkit-dark-393-macro-unknown.png) · [excess](states/webkit-dark-393-macro-excess.png) | [custom](states/webkit-dark-393-water-custom.png) · [history-open](states/webkit-dark-393-water-history-open.png) · [undo](states/webkit-dark-393-water-undo.png) | [closed](states/webkit-dark-393-status-closed.png) · [open](states/webkit-dark-393-status-open.png) · [empty](states/webkit-dark-393-status-empty.png) · [loading](states/webkit-dark-393-status-loading.png) · [error](states/webkit-dark-393-status-error.png) |

Масштаб текста 200%, viewport 320 × 844: [Chromium](states/chromium-light-320-text-200.png) · [WebKit](states/webkit-light-320-text-200.png). Это увеличение шрифта в тестовом браузере, а не проверка реального устройства.

## Что изменилось и что сохранено

- Под неделей стоят два равнозначных действия «Добавить еду» и «Добавить воду»; быстрый ввод сохранён как видимое действие в окне добавления еды. В сравнении с прежней отдельной кнопкой путь увеличился на одно открытие окна.
- Карточки КБЖУ, компактные строки приёмов пищи, горизонтальный прогресс воды и видимые пункты «Дополнительно» приведены к принятой композиции. Действия, предупреждения о неполных данных, источник цели, редактирование на дату, история, сохранённые ёмкости, отмена и ошибки сохранены.
- Общая шапка и навигация берутся из действующей оболочки приложения; они не заменяются статичной оболочкой прототипа. Дополнительные фактические сведения и действия могут отличаться от изображения макета.

## Проверки и ограничения

- Локальная сборка и frontend lint: PASS. Unit: 189 файлов / 1481 тест до завершающих визуальных уточнений; повторная проверка затронутых компонентов: 96 тестов PASS. Полный Chromium-прогон дневника: 128 тестов PASS.
- Chromium/WebKit: 108 сценариев еды, воды, КБЖУ и планирования, затем 34 финальных проверки экранов и воды, 30 проверок семи дней/размеров/клавиатуры, 40 проверок состояний, 10 проверок статуса и масштабирования. После исправления ожидания включённого состояния отдельный повтор/отмена: 4 PASS. Результаты относятся к указанным локальным прогонам, не к общему CI.
- Реальные устройства, screen reader, Telegram и production: NOT_VERIFIED. Mocked TMA/PWA и автоматические браузеры не заменяют проверку на устройстве.
- Снимки регрессии CI по существующему дизайну необходимо обновлять только после визуальной приёмки фактической реализации; не считать их текущие отличия техническим PASS.
