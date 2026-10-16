# #865 — финальный AFTER после исправления native date inputs

Пакет снят из работающего приложения PR #1013 после fresh frontend build и Playwright preview.
Использованы mocked platform API и безопасные синтетические данные; изолированный HTML-прототип
не использовался как источник AFTER.

## Матрица

- Chromium и WebKit.
- Light и Dark.
- Mobile: `320`, `360`, `390`, `393`, `430px`.
- Desktop: `1280`, `1440`, `1920`, `2560px`.
- Состояния: `closed-closed`, `help-open`, `custom-open`, `help-and-custom-open`.
- Всего: `144` реальных crop-скриншота (`2 × 9 × 2 × 4`).

В форме «Свой период» использованы заполненные значения `2025-01-01` и `2025-01-30`.
В Chromium видны полные локализованные даты `01.01.2025` и `30.01.2025`; в WebKit — полные
ISO-даты `2025-01-01` и `2025-01-30`.

## Представительные кадры

| Движок | Ширина | Тема | Состояние | Кадр |
| --- | ---: | --- | --- | --- |
| Chromium | 320 | Light | `closed-closed` | [PNG](chromium-320-light-closed-closed.png) |
| Chromium | 430 | Dark | `help-and-custom-open` | [PNG](chromium-430-dark-help-and-custom-open.png) |
| Chromium | 1280 | Light | `custom-open` | [PNG](chromium-1280-light-custom-open.png) |
| Chromium | 1440 | Light | `custom-open` | [PNG](chromium-1440-light-custom-open.png) |
| Chromium | 2560 | Dark | `help-and-custom-open` | [PNG](chromium-2560-dark-help-and-custom-open.png) |
| WebKit | 320 | Dark | `custom-open` | [PNG](webkit-320-dark-custom-open.png) |
| WebKit | 1280 | Light | `custom-open` | [PNG](webkit-1280-light-custom-open.png) |
| WebKit | 1440 | Dark | `help-and-custom-open` | [PNG](webkit-1440-dark-help-and-custom-open.png) |
| WebKit | 2560 | Light | `custom-open` | [PNG](webkit-2560-light-custom-open.png) |

Полный набор находится в этом каталоге. Физический iPhone/Safari, нативный Telegram Mini App и
VoiceOver этим пакетом не подтверждаются: для них остаётся `NOT_VERIFIED` без прямого device
evidence.

## Что защищает regression

`frontend/tests/e2e/progress-experience.spec.ts` проверяет обе настоящие `input[type=date]` на
каждой ширине и в обеих темах в сфокусированном и расфокусированном состояниях. Помимо DOM/value
контрактов тест снимает заполненный и пустой input, сравнивает фактические пиксели текста,
измеряет доступную текстовую область с учётом padding и календарного резерва и проверяет отсутствие
обрезания до календарного значка. Отдельно проверяются одна строка «Свой период», ARIA/focus,
четыре комбинации раскрытия, overlap и горизонтальный overflow. Golden snapshots не обновлялись.
