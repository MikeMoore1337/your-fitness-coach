# Issue #960 — existing RestTimer composition review

Это обновлённый статический review-пакет после owner-review PR #1044. Функциональная логика
остаётся Variant A, но композиция строго сохраняет действующий `RestTimer`: это не новый
компонент и не перенос standalone-макета Variant A в продукт. Пакет не меняет frontend runtime,
API, БД, PDF или Coach OS.

## Что сохраняется

Проверенная область — `origin/master` `10d3010968bde58554ffeb0925d94fc5d555a48f`; последний
изменённый master commit касается exercise media и не затрагивает RestTimer. За основу взят
`TodayWorkout.tsx` и его CSS:

- sticky-верхняя панель, safe-area top и текущий матовый Liquid Glass;
- фирменные цвета, типографика, скругления, размеры и плотность;
- плановый countdown `Отдых` слева и контекст `Далее` в существующей верхней строке;
- существующий ряд `+30 сек / +60 сек / Пропустить` без изменения порядка и смысла;
- текущая responsive-геометрия панели: около 110 px на узкой ширине и 64 px на desktop;
- 44×44 touch targets, видимый keyboard focus, reduced motion и forced-colors intent.

## Единственная визуальная добавка

В предложенной композиции после текста `Далее` в свободной правой части той же верхней строки
появляется компактный блок:

```text
Факт
00:42   Стоп
```

`Факт` — это только измеренный интервал до явной отметки пользователя; он не означает
физиологическую готовность и не доказывает начало следующего подхода. Действие `Стоп` имеет
доступное имя `Завершить отдых`, находится в том же top row и не занимает отдельную постоянную
строку. В overtime оно сохраняет тот же target, а `План завершён` появляется в существующем
контексте `Далее`; новый ряд или отдельная карточка не добавляются.

На 320 px длинный текст `Далее` обрезается ellipsis в центральной области и не вытесняет
фактический блок или кнопку. На 360/393/430 px сохраняется тот же порядок. На desktop действия
остаются в существующей правой части панели; нижний ряд на mobile по-прежнему содержит ровно
`+30 сек`, `+60 сек`, `Пропустить`.

Точная видимая подпись compact action (`Стоп` или согласованный owner-вариант) остаётся частью
отдельного implementation gate. Threshold Policy A/B не выбирается этим пакетом.

## CURRENT REST TIMER / PROPOSED REST TIMER

| | CURRENT REST TIMER | PROPOSED REST TIMER |
| --- | --- | --- |
| Верхняя строка | `Отдых` + плановый countdown слева; `Далее` по центру | Та же строка; `Факт` и компактный `Стоп` добавлены справа после `Далее` |
| Нижний ряд | `+30 сек` · `+60 сек` · `Пропустить` | Без изменений: те же три действия, тот же порядок и смысл |
| Overtime | Текущий таймер достигает нуля, затем существующий `completedNotice` сворачивает панель | План остаётся `0:00`, `Факт` продолжает расти, `Стоп` остаётся явным terminal action |
| Завершение | Текущий compact notice: `Отдых завершён · дальше: …` + `Скрыть` | `Отдых завершён · факт 0:42` + `Скрыть`; следующий подход остаётся отдельным действием |
| Высота активной панели | Около `110 px` на 320–430 и `64 px` на desktop | Ровно та же высота в countdown/overtime; completion compact-состояние не является постоянной строкой |
| Что не меняется | Liquid Glass, цвета, шрифты, формы, safe-area и sticky-позиция | Всё перечисленное сохраняется; не создаётся новая карточка или независимый RestTimer |

В proposed prototype клик по доступному действию `Завершить отдых` (видимая короткая подпись —
`Стоп`) переводит панель в compact completion state. Это визуально подтверждает явную остановку;
автоматического завершения следующего подхода в макете нет.

## Макеты и сравнение

Каждый SVG — обезличенный synthetic fixture с реальным viewport width. Текущая версия SVG
показывает предложенную baseline-preserving композицию, включая compact completion state:

| Viewport | Countdown Dark / Light | Overtime Dark / Light | Completion Dark / Light |
| --- | --- | --- | --- |
| 320 px | [Dark](screenshots/320-dark-countdown.svg) · [Light](screenshots/320-light-countdown.svg) | [Dark](screenshots/320-dark-overtime.svg) · [Light](screenshots/320-light-overtime.svg) | [Dark](screenshots/320-dark-completed.svg) · [Light](screenshots/320-light-completed.svg) |
| 360 px | [Dark](screenshots/360-dark-countdown.svg) · [Light](screenshots/360-light-countdown.svg) | [Dark](screenshots/360-dark-overtime.svg) · [Light](screenshots/360-light-overtime.svg) | [Dark](screenshots/360-dark-completed.svg) · [Light](screenshots/360-light-completed.svg) |
| 393 px | [Dark](screenshots/393-dark-countdown.svg) · [Light](screenshots/393-light-countdown.svg) | [Dark](screenshots/393-dark-overtime.svg) · [Light](screenshots/393-light-overtime.svg) | [Dark](screenshots/393-dark-completed.svg) · [Light](screenshots/393-light-completed.svg) |
| 430 px | [Dark](screenshots/430-dark-countdown.svg) · [Light](screenshots/430-light-countdown.svg) | [Dark](screenshots/430-dark-overtime.svg) · [Light](screenshots/430-light-overtime.svg) | [Dark](screenshots/430-dark-completed.svg) · [Light](screenshots/430-light-completed.svg) |
| Desktop 1280 px | [Dark](screenshots/1280-dark-countdown.svg) · [Light](screenshots/1280-light-countdown.svg) | [Dark](screenshots/1280-dark-overtime.svg) · [Light](screenshots/1280-light-overtime.svg) | [Dark](screenshots/1280-dark-completed.svg) · [Light](screenshots/1280-light-completed.svg) |

Для визуального сравнения `prototype.html` поддерживает `mode=baseline` (действующий UI) и
`mode=proposed` (новая композиция), а также `state=countdown|overtime|completed` и
`theme=dark|light`. Browser-rendered captures публикуются отдельно. В current completion
снимке показан существующий compact notice; proposed completion получен кликом по `Стоп`.

| Viewport | CURRENT RestTimer | PROPOSED countdown | PROPOSED overtime | PROPOSED completion |
| --- | --- | --- | --- | --- |
| 320 px | [Dark](screenshots/browser/320-dark-baseline.png) · [Light](screenshots/browser/320-light-baseline.png)<br>[Dark complete](screenshots/browser/320-dark-baseline-completed.png) · [Light complete](screenshots/browser/320-light-baseline-completed.png) | [Dark](screenshots/browser/320-dark-proposed-countdown.png) · [Light](screenshots/browser/320-light-proposed-countdown.png) | [Dark](screenshots/browser/320-dark-proposed-overtime.png) · [Light](screenshots/browser/320-light-proposed-overtime.png) | [Dark](screenshots/browser/320-dark-proposed-completed.png) · [Light](screenshots/browser/320-light-proposed-completed.png) |
| 360 px | [Dark](screenshots/browser/360-dark-baseline.png) · [Light](screenshots/browser/360-light-baseline.png)<br>[Dark complete](screenshots/browser/360-dark-baseline-completed.png) · [Light complete](screenshots/browser/360-light-baseline-completed.png) | [Dark](screenshots/browser/360-dark-proposed-countdown.png) · [Light](screenshots/browser/360-light-proposed-countdown.png) | [Dark](screenshots/browser/360-dark-proposed-overtime.png) · [Light](screenshots/browser/360-light-proposed-overtime.png) | [Dark](screenshots/browser/360-dark-proposed-completed.png) · [Light](screenshots/browser/360-light-proposed-completed.png) |
| 393 px | [Dark](screenshots/browser/393-dark-baseline.png) · [Light](screenshots/browser/393-light-baseline.png)<br>[Dark complete](screenshots/browser/393-dark-baseline-completed.png) · [Light complete](screenshots/browser/393-light-baseline-completed.png) | [Dark](screenshots/browser/393-dark-proposed-countdown.png) · [Light](screenshots/browser/393-light-proposed-countdown.png) | [Dark](screenshots/browser/393-dark-proposed-overtime.png) · [Light](screenshots/browser/393-light-proposed-overtime.png) | [Dark](screenshots/browser/393-dark-proposed-completed.png) · [Light](screenshots/browser/393-light-proposed-completed.png) |
| 430 px | [Dark](screenshots/browser/430-dark-baseline.png) · [Light](screenshots/browser/430-light-baseline.png)<br>[Dark complete](screenshots/browser/430-dark-baseline-completed.png) · [Light complete](screenshots/browser/430-light-baseline-completed.png) | [Dark](screenshots/browser/430-dark-proposed-countdown.png) · [Light](screenshots/browser/430-light-proposed-countdown.png) | [Dark](screenshots/browser/430-dark-proposed-overtime.png) · [Light](screenshots/browser/430-light-proposed-overtime.png) | [Dark](screenshots/browser/430-dark-proposed-completed.png) · [Light](screenshots/browser/430-light-proposed-completed.png) |
| Desktop 1280 px | [Dark](screenshots/browser/1280-dark-baseline.png) · [Light](screenshots/browser/1280-light-baseline.png)<br>[Dark complete](screenshots/browser/1280-dark-baseline-completed.png) · [Light complete](screenshots/browser/1280-light-baseline-completed.png) | [Dark](screenshots/browser/1280-dark-proposed-countdown.png) · [Light](screenshots/browser/1280-light-proposed-countdown.png) | [Dark](screenshots/browser/1280-dark-proposed-overtime.png) · [Light](screenshots/browser/1280-light-proposed-overtime.png) | [Dark](screenshots/browser/1280-dark-proposed-completed.png) · [Light](screenshots/browser/1280-light-proposed-completed.png) |

Browser captures are local Brave Chromium renders of this static prototype with synthetic data. They are
`DISCOVERY_EVIDENCE`, not production AFTER evidence. They do not prove physical iPhone/Safari,
Telegram Mini App, VoiceOver or production behavior.

## Поведение, которое макет фиксирует

- Start происходит один раз после принятого завершения рабочего подхода.
- `+30 сек` и `+60 сек` двигают только плановый deadline; они не меняют `Факт` и не заменяют
  `planned_rest_seconds` измеренным значением.
- Достижение нуля даёт одно уведомление, но не terminal state: `Факт` продолжает расти.
- Inline `Стоп` фиксирует явную отметку пользователя и не отмечает следующий подход.
- После inline `Стоп` панель переходит в compact completion state; постоянная дополнительная
  строка не появляется, а `Скрыть` повторяет существующий current RestTimer affordance.
- `Пропустить` остаётся отдельным действием и не создаёт достоверный measured interval.
- После выбранного hard cutoff при resume/reload/reconnect сессия становится `unknown`, display
  elapsed прекращается; UI не считает бесконечно после ухода пользователя.
- Forgotten-stop допускает отдельные действия `Завершить сейчас`, `Исправить время` или
  `Не учитывать`; коррекция ограничена `started_at…now` и помечается отдельно.

## Review-проверки

Выполнены для статического пакета:

- 320/360/393/430/1280 × Dark/Light;
- countdown, overtime и completion, включая длинный текст `Далее`;
- отсутствие горизонтального overflow, выхода compact action из top row и перекрытия нижней
  навигации;
- сохранение текущей панели и трёх нижних действий;
- proposed active panel height равна current RestTimer: около 110 px mobile и 64 px desktop;
- click-path `Стоп` → completion, доступное имя `Завершить отдых`, 44×44 targets, видимый focus
  intent, reduced motion и forced-colors intent в CSS.

Остаются owner/runtime проверки после отдельного implementation approval:

- Chromium и WebKit на реальном runtime/TMA, safe-area, `visualViewport`, background/reload,
  offline, multi-tab и notification lifecycle;
- физический iPhone/Safari, VoiceOver и реальная Telegram Mini App — `NOT_VERIFIED`;
- точный copy compact action и выбор одной threshold policy A/B — owner decision;
- implementation, real AFTER Dark/Light evidence, owner visual acceptance, merge и deploy.

Для повторной генерации SVG без зависимостей:

```text
node docs/ux-proposals/issue-960/review/generate-mockups.mjs
```

Для браузерных PNG используется локальный `playwright-cli` capture script, который не подключает
сеть и не использует пользовательские данные:

```text
playwright-cli run-code --filename=docs/ux-proposals/issue-960/review/capture-browser-screenshots.js
```
