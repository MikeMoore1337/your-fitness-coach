# Issue #960 — baseline-preserving Variant A review

Это статический review-пакет после решения владельца выбрать функциональную логику Variant A.
Он не является production-компонентом и не меняет frontend runtime, API, БД, PDF или Coach OS.

## Что именно сохраняется

За основу взят действующий `RestTimer` на исходном SHA `4c92832415d4eb994cf6b849a67074742f07ea50`:

- sticky-верхняя панель и safe-area top;
- матовый Liquid Glass, фирменные цвета, типографика, радиусы и текущая плотность;
- существующий countdown `Отдых`, контекст `Далее` и ряд `+30 сек / +60 сек / Пропустить`;
- отдельный reserved flow без click-through и без перекрытия первого поля/нижней навигации;
- системные 44×44 touch targets, видимый keyboard focus и `prefers-reduced-motion`.

Минимальная добавка Variant A:

1. `Факт 00:42` рядом с текущим обратным счётчиком;
2. `Завершить отдых` в том же стиле управляющих элементов.

На 320/360/393/430 px CTA получает отдельную строку, чтобы не сжимать существующие три кнопки.
На desktop сохранён тот же порядок чтения и тот же max-width панели; добавление не превращается
в новый card, modal или отдельный редизайн. В overtime-состоянии `Осталось` зафиксировано на
`00:00`, `Факт` продолжает расти, а `План завершён` остаётся нейтральным статусом.

## Макеты

Каждый SVG — обезличенный synthetic fixture с реальным viewport width. Состояния показаны отдельно:

| Viewport | Dark countdown | Dark overtime | Light countdown | Light overtime |
| --- | --- | --- | --- | --- |
| 320 px | [SVG](screenshots/320-dark-countdown.svg) | [SVG](screenshots/320-dark-overtime.svg) | [SVG](screenshots/320-light-countdown.svg) | [SVG](screenshots/320-light-overtime.svg) |
| 360 px | [SVG](screenshots/360-dark-countdown.svg) | [SVG](screenshots/360-dark-overtime.svg) | [SVG](screenshots/360-light-countdown.svg) | [SVG](screenshots/360-light-overtime.svg) |
| 393 px | [SVG](screenshots/393-dark-countdown.svg) | [SVG](screenshots/393-dark-overtime.svg) | [SVG](screenshots/393-light-countdown.svg) | [SVG](screenshots/393-light-overtime.svg) |
| 430 px | [SVG](screenshots/430-dark-countdown.svg) | [SVG](screenshots/430-dark-overtime.svg) | [SVG](screenshots/430-light-countdown.svg) | [SVG](screenshots/430-light-overtime.svg) |
| Desktop 1280 px | [SVG](screenshots/1280-dark-countdown.svg) | [SVG](screenshots/1280-dark-overtime.svg) | [SVG](screenshots/1280-light-countdown.svg) | [SVG](screenshots/1280-light-overtime.svg) |

`prototype.html` — локальный интерактивный просмотр двух состояний и двух тем. Он использует
только этот каталог и не подключает production-бандл, сеть или пользовательские данные.

## Поведение, которое макет фиксирует

- Start происходит один раз после принятого завершения рабочего подхода.
- `+30 сек` и `+60 сек` двигают только плановый deadline; они не меняют `Факт` и не заменяют
  `planned_rest_seconds` измеренным значением.
- Достижение нуля даёт одно уведомление, но не terminal state: `Факт` продолжает расти.
- `Завершить отдых` фиксирует явную отметку пользователя и не отмечает следующий подход.
- `Пропустить` остаётся отдельным действием и не создаёт достоверный measured interval.
- После выбранного hard cutoff при resume/reload/reconnect сессия становится `unknown`, display
  elapsed прекращается; это исключает бесконечный отсчёт после ухода пользователя.
- Forgotten-stop предлагает `Завершить сейчас`, `Исправить время` или `Не учитывать`; коррекция
  разрешена только в диапазоне `started_at…now` и помечается отдельно.

## Review-проверки

Static-пакет предназначен для owner review. До реализации нужно подтвердить:

- отсутствие горизонтального overflow и перекрытия нижней навигации на всех пяти ширинах;
- contrast, `:focus-visible`, Tab order, 44×44 targets, reduced motion и safe-area intent;
- что сохранены нынешние `+30`, `+60`, `Пропустить`, порядок и смысл уведомления;
- одну threshold policy: A (относительная, bounded 12–24 часа) или B (fixed 60 минут/12 часов);
- exact implementation copy и отдельный `OWNER_IMPLEMENTATION_APPROVAL`.

SVG и локальный prototype — `DISCOVERY_EVIDENCE`, не real AFTER evidence. Physical iPhone/Safari,
real TMA, VoiceOver и production acceptance остаются `NOT_VERIFIED`.

Для повторной генерации SVG без зависимостей:

```text
node docs/ux-proposals/issue-960/review/generate-mockups.mjs
```
