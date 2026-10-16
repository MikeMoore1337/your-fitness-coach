# #865 — финальный AFTER реализации PR #1013

Пакет снят из работающего приложения после реализации утверждённой композиции. Это не
изолированный HTML-прототип: проверялся production build фронтенда через Playwright preview,
с mocked platform API и синтетическими данными.

## Матрица

- Chromium и WebKit.
- Light и Dark.
- Mobile: `320`, `360`, `390`, `393`, `430px`.
- Desktop: `1280`, `1440`, `1920`, `2560px`.
- Состояния: `closed-closed`, `help-open`, `custom-open`, `help-and-custom-open`.
- Всего: `144` реальных crop-скриншота (`2 × 9 × 2 × 4`).

В форме «Свой период» использованы заполненные значения `2025-01-01` и `2025-01-30`.
В Chromium видны локализованные даты `01.01.2025` и `30.01.2025`; в WebKit — полный
ISO-формат `2025-01-01` и `2025-01-30`, без обрезания последнего символа.

## Представительные кадры

Полный набор находится в этом каталоге. Ниже — кадры для быстрой проверки обеих тем,
мобильной и desktop-геометрии, закрытого/раскрытого пояснения и custom form.

| Движок | Ширина | Тема | Состояние | Кадр |
| --- | ---: | --- | --- | --- |
| Chromium | 320 | Light | `closed-closed` | [PNG](chromium-320-light-closed-closed.png) |
| Chromium | 430 | Light | `help-and-custom-open` | [PNG](chromium-430-light-help-and-custom-open.png) |
| Chromium | 1280 | Light | `help-open` | [PNG](chromium-1280-light-help-open.png) |
| Chromium | 1280 | Light | `custom-open` | [PNG](chromium-1280-light-custom-open.png) |
| Chromium | 320 | Dark | `closed-closed` | [PNG](chromium-320-dark-closed-closed.png) |
| Chromium | 430 | Dark | `help-and-custom-open` | [PNG](chromium-430-dark-help-and-custom-open.png) |
| WebKit | 320 | Light | `custom-open` | [PNG](webkit-320-light-custom-open.png) |
| WebKit | 1280 | Dark | `custom-open` | [PNG](webkit-1280-dark-custom-open.png) |

Физический iPhone/Safari, нативный Telegram Mini App и VoiceOver этим пакетом не
подтверждаются: для них остаётся `NOT_VERIFIED` без прямого device evidence.
