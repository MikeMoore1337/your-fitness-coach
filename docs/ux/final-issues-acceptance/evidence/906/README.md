# #906 — Hero: BEFORE / proposal A / proposal B

Статус: `NOT_IMPLEMENTED_OWNER_GATE`. Это изолированное локальное предложение для выбора владельца; production-код, `master`, PR merge и deployment не менялись.

Снимки получены из реально запущенной Chromium-сборки на runtime `733933a73a3bc27ca596b9efb00751105a539a86` (ветка PR #936 после исправления #903), сервер `http://127.0.0.1:4173`, headless Chromium, device scale factor 1, шрифты дождались `document.fonts.ready`, viewport CSS px. `BEFORE` — текущий runtime без временного CSS overlay; `A` и `B` — тот же route/data/theme с временным overlay только на `.ref-hero`.

| Route | Viewport | Theme | BEFORE | Variant A | Variant B |
|---|---:|---|---|---|---|
| `/for-athletes` | 2560×1440 | dark | [BEFORE](before-athletes-qhd-dark.jpg) | [A](a-athletes-qhd-dark.jpg) | [B](b-athletes-qhd-dark.jpg) |
| `/for-athletes` | 2560×1440 | light | [BEFORE](before-athletes-qhd-light.jpg) | [A](a-athletes-qhd-light.jpg) | [B](b-athletes-qhd-light.jpg) |
| `/for-trainers` | 2560×1440 | dark | [BEFORE](before-trainers-qhd-dark.jpg) | [A](a-trainers-qhd-dark.jpg) | [B](b-trainers-qhd-dark.jpg) |
| `/for-trainers` | 2560×1440 | light | [BEFORE](before-trainers-qhd-light.jpg) | [A](a-trainers-qhd-light.jpg) | [B](b-trainers-qhd-light.jpg) |
| `/for-athletes` | 1920×1080 | dark | [BEFORE](before-athletes-hd-dark.jpg) | [A](a-athletes-hd-dark.jpg) | [B](b-athletes-hd-dark.jpg) |
| `/for-athletes` | 1920×1080 | light | [BEFORE](before-athletes-hd-light.jpg) | [A](a-athletes-hd-light.jpg) | [B](b-athletes-hd-light.jpg) |
| `/for-trainers` | 1920×1080 | dark | [BEFORE](before-trainers-hd-dark.jpg) | [A](a-trainers-hd-dark.jpg) | [B](b-trainers-hd-dark.jpg) |
| `/for-trainers` | 1920×1080 | light | [BEFORE](before-trainers-hd-light.jpg) | [A](a-trainers-hd-light.jpg) | [B](b-trainers-hd-light.jpg) |
| `/for-athletes` | 1440×900 | dark | [BEFORE](before-athletes-desktop-dark.jpg) | [A](a-athletes-desktop-dark.jpg) | [B](b-athletes-desktop-dark.jpg) |
| `/for-athletes` | 1440×900 | light | [BEFORE](before-athletes-desktop-light.jpg) | [A](a-athletes-desktop-light.jpg) | [B](b-athletes-desktop-light.jpg) |
| `/for-trainers` | 1440×900 | dark | [BEFORE](before-trainers-desktop-dark.jpg) | [A](a-trainers-desktop-dark.jpg) | [B](b-trainers-desktop-dark.jpg) |
| `/for-trainers` | 1440×900 | light | [BEFORE](before-trainers-desktop-light.jpg) | [A](a-trainers-desktop-light.jpg) | [B](b-trainers-desktop-light.jpg) |

## Параметры вариантов

- **A — conservative:** высота Hero `900px`, focal position `65% 34%`. Плюсы: минимальное изменение первого экрана и более ранний переход к следующему разделу. Минусы: часть верхнего силуэта и оборудования остаётся ближе к границе кадра на широких viewport.
- **B — cinematic:** высота Hero `980px`, focal position `65% 27%`. Плюсы: больше вертикального пространства и спокойнее кадрирование лица/рук/оборудования. Минусы: ниже виден следующий раздел и выше стоимость вертикального скролла.

Оба варианта сохраняют header, audience switch, типографику, CTA, пропорции изображения и текущие маршруты. Ни один вариант не выбран за владельца; до решения не создаётся production PR для #906.

Полная provenance: [`provenance.json`](provenance.json).
