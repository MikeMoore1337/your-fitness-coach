# Issue #1432: копирование дня

Исходное состояние: `8280681aa179d2855dde7368f8389d05ee38af98` (`origin/dev`). Реализация: `151b2d822ce078f3e60e086513e7013062af4368`. Снимки AFTER получены с исходников этого коммита; следующий коммит добавляет только этот пакет.

Все данные вымышлены, ответы API и demo transport подменены тестовыми фикстурами. Это реальный рендер приложения, но не проверка production или физического устройства. Chromium 151.0.7922.34, WebKit 26.5; размеры окон указаны в CSS px, высота — 844 px. Сценарии копирования используют 6 и 5 ноября 2026 года как исходную и целевую даты.

## Заполненный день и диалог

| Браузер | Ширина | Тема | BEFORE | AFTER |
|---|---:|---|---|---|
| Chromium | 393 | Dark | [карточка](evidence/before/chromium-dark-393-card.png) · [диалог](evidence/before/chromium-dark-393-dialog.png) | [карточка](evidence/after/chromium-dark-393-card.png) · [выбор даты](evidence/after/chromium-dark-393-dialog.png) · [предпросмотр](evidence/after/chromium-dark-393-preview.png) |
| Chromium | 393 | Light | [карточка](evidence/before/chromium-light-393-card.png) · [диалог](evidence/before/chromium-light-393-dialog.png) | [карточка](evidence/after/chromium-light-393-card.png) · [выбор даты](evidence/after/chromium-light-393-dialog.png) · [предпросмотр](evidence/after/chromium-light-393-preview.png) |
| Chromium | 1280 | Dark | [карточка](evidence/before/chromium-dark-1280-card.png) · [диалог](evidence/before/chromium-dark-1280-dialog.png) | [карточка](evidence/after/chromium-dark-1280-card.png) · [выбор даты](evidence/after/chromium-dark-1280-dialog.png) · [предпросмотр](evidence/after/chromium-dark-1280-preview.png) |
| Chromium | 1280 | Light | [карточка](evidence/before/chromium-light-1280-card.png) · [диалог](evidence/before/chromium-light-1280-dialog.png) | [карточка](evidence/after/chromium-light-1280-card.png) · [выбор даты](evidence/after/chromium-light-1280-dialog.png) · [предпросмотр](evidence/after/chromium-light-1280-preview.png) |
| WebKit | 393 | Dark | [карточка](evidence/before/webkit-dark-393-card.png) · [диалог](evidence/before/webkit-dark-393-dialog.png) | [карточка](evidence/after/webkit-dark-393-card.png) · [выбор даты](evidence/after/webkit-dark-393-dialog.png) · [предпросмотр](evidence/after/webkit-dark-393-preview.png) |
| WebKit | 393 | Light | [карточка](evidence/before/webkit-light-393-card.png) · [диалог](evidence/before/webkit-light-393-dialog.png) | [карточка](evidence/after/webkit-light-393-card.png) · [выбор даты](evidence/after/webkit-light-393-dialog.png) · [предпросмотр](evidence/after/webkit-light-393-preview.png) |
| WebKit | 1280 | Dark | [карточка](evidence/before/webkit-dark-1280-card.png) · [диалог](evidence/before/webkit-dark-1280-dialog.png) | [карточка](evidence/after/webkit-dark-1280-card.png) · [выбор даты](evidence/after/webkit-dark-1280-dialog.png) · [предпросмотр](evidence/after/webkit-dark-1280-preview.png) |
| WebKit | 1280 | Light | [карточка](evidence/before/webkit-light-1280-card.png) · [диалог](evidence/before/webkit-light-1280-dialog.png) | [карточка](evidence/after/webkit-light-1280-card.png) · [выбор даты](evidence/after/webkit-light-1280-dialog.png) · [предпросмотр](evidence/after/webkit-light-1280-preview.png) |

## Пустой день и demo readOnly: AFTER

| Браузер | Ширина | Тема | Состояния |
|---|---:|---|---|
| Chromium | 320 | Dark | [пустой день](evidence/after/chromium-dark-320-empty.png) · [demo](evidence/after/chromium-dark-320-demo.png) |
| Chromium | 320 | Light | [пустой день](evidence/after/chromium-light-320-empty.png) · [demo](evidence/after/chromium-light-320-demo.png) |
| Chromium | 1280 | Dark | [пустой день](evidence/after/chromium-dark-1280-empty.png) · [demo](evidence/after/chromium-dark-1280-demo.png) |
| Chromium | 1280 | Light | [пустой день](evidence/after/chromium-light-1280-empty.png) · [demo](evidence/after/chromium-light-1280-demo.png) |
| WebKit | 320 | Dark | [пустой день](evidence/after/webkit-dark-320-empty.png) · [demo](evidence/after/webkit-dark-320-demo.png) |
| WebKit | 320 | Light | [пустой день](evidence/after/webkit-light-320-empty.png) · [demo](evidence/after/webkit-light-320-demo.png) |
| WebKit | 1280 | Dark | [пустой день](evidence/after/webkit-dark-1280-empty.png) · [demo](evidence/after/webkit-dark-1280-demo.png) |
| WebKit | 1280 | Light | [пустой день](evidence/after/webkit-light-1280-empty.png) · [demo](evidence/after/webkit-light-1280-demo.png) |

Принятый макет: [#1440](https://github.com/MikeMoore1337/your-fitness-coach/issues/1440). Этот пакет ожидает отдельной визуальной приёмки реализации владельцем и не является разрешением на merge или deploy.
