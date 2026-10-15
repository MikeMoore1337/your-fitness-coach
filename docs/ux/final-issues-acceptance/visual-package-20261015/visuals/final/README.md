# YFC - PR #1000, финальный визуальный пакет после замечаний (15.10.2026)

Это дополняющий пакет к [первоначальному отчёту](../../README.md). Состояние до исправлений: a8b8b3ad25e3cdd77fa6f74fadf11f26a8082501. Новые ссылки на SHA будут действительны после публикации.

**Статус: на визуальную оценку.** Код проверен локально, но итоговый owner approval не выдавался. Merge/deploy/close запрещены.

## Что исправлено

- Прогресс: текстовый горизонтальный переключатель без стрелок. На 393 px сохранены начальный обзор и крайняя вкладка История, выбранная через фокус и скролл.
- Самочувствие: Сохранить отметку имеет лаймовый фон, Удалить - красный destructive фон. Native unchecked радио - нейтральные и пустые; checked - с лаймовым акцентом и нижней гранью.
- Действия формы на 320/360/390/430 px в одну строку в Chromium/WebKit, обе темы. JSON содержит реальные размеры.
- Сон вводится в часах; API по-прежнему хранит минуты. Unit подтверждает точное преобразование 1..1440 минут туда и обратно.
- Проверены фактические шрифты, размеры, начертания, высоты строк и существующие типографические токены в Progress, Today, Wellbeing и Quick Add.

## Прогресс 393 px

| Браузер | Тема | Обзор | Последняя История | Прямая ссылка / обновление |
|---|---|---|---|---|
| chromium | dark | [Открыть](progress-393-initial-dark-chromium.png) | [Открыть](progress-393-history-dark-chromium.png) | [Открыть](progress-393-history-direct-dark-chromium.png) |
| chromium | light | [Открыть](progress-393-initial-light-chromium.png) | [Открыть](progress-393-history-light-chromium.png) | [Открыть](progress-393-history-direct-light-chromium.png) |
| webkit | dark | [Открыть](progress-393-initial-dark-webkit.png) | [Открыть](progress-393-history-dark-webkit.png) | [Открыть](progress-393-history-direct-dark-webkit.png) |
| webkit | light | [Открыть](progress-393-initial-light-webkit.png) | [Открыть](progress-393-history-light-webkit.png) | [Открыть](progress-393-history-direct-light-webkit.png) |

## Самочувствие, Dark/Light: выбранные радиокнопки и два действия

| Ширина | Chromium Dark | Chromium Light | WebKit Dark | WebKit Light |
|---|---|---|---|---|
| 320 px | [Открыть](chromium-wellbeing-actions-320-dark.png) | [Открыть](chromium-wellbeing-actions-320-light.png) | [Открыть](webkit-wellbeing-actions-320-dark.png) | [Открыть](webkit-wellbeing-actions-320-light.png) |
| 360 px | [Открыть](chromium-wellbeing-actions-360-dark.png) | [Открыть](chromium-wellbeing-actions-360-light.png) | [Открыть](webkit-wellbeing-actions-360-dark.png) | [Открыть](webkit-wellbeing-actions-360-light.png) |
| 390 px | [Открыть](chromium-wellbeing-actions-390-dark.png) | [Открыть](chromium-wellbeing-actions-390-light.png) | [Открыть](webkit-wellbeing-actions-390-dark.png) | [Открыть](webkit-wellbeing-actions-390-light.png) |
| 430 px | [Открыть](chromium-wellbeing-actions-430-dark.png) | [Открыть](chromium-wellbeing-actions-430-light.png) | [Открыть](webkit-wellbeing-actions-430-dark.png) | [Открыть](webkit-wellbeing-actions-430-light.png) |

## Подтверждённая геометрия/цвета кнопок

| Браузер | Тема | Ширина | Save background | Delete background | Top Save / Delete (px) | Overflow |
|---|---|---:|---|---|---|---|
| chromium | dark | 320 | rgb(178, 245, 32) | rgb(239, 116, 116) | 1441.95 / 1441.95 | Нет |
| chromium | dark | 360 | rgb(178, 245, 32) | rgb(239, 116, 116) | 1005.95 / 1005.95 | Нет |
| chromium | dark | 390 | rgb(178, 245, 32) | rgb(239, 116, 116) | 1299.58 / 1299.58 | Нет |
| chromium | dark | 430 | rgb(178, 245, 32) | rgb(239, 116, 116) | 1281.20 / 1281.20 | Нет |
| chromium | light | 320 | rgb(178, 245, 32) | rgb(185, 56, 56) | 1441.95 / 1441.95 | Нет |
| chromium | light | 360 | rgb(178, 245, 32) | rgb(185, 56, 56) | 989.95 / 989.95 | Нет |
| chromium | light | 390 | rgb(178, 245, 32) | rgb(185, 56, 56) | 961.58 / 961.58 | Нет |
| chromium | light | 430 | rgb(178, 245, 32) | rgb(185, 56, 56) | 1281.20 / 1281.20 | Нет |
| webkit | dark | 320 | rgb(178, 245, 32) | rgb(239, 116, 116) | 1067.77 / 1067.77 | Нет |
| webkit | dark | 360 | rgb(178, 245, 32) | rgb(239, 116, 116) | 1003.77 / 1003.77 | Нет |
| webkit | dark | 390 | rgb(178, 245, 32) | rgb(239, 116, 116) | 959.42 / 959.42 | Нет |
| webkit | dark | 430 | rgb(178, 245, 32) | rgb(239, 116, 116) | 959.08 / 959.08 | Нет |
| webkit | light | 320 | rgb(178, 245, 32) | rgb(185, 56, 56) | 1067.77 / 1067.77 | Нет |
| webkit | light | 360 | rgb(178, 245, 32) | rgb(185, 56, 56) | 1003.77 / 1003.77 | Нет |
| webkit | light | 390 | rgb(178, 245, 32) | rgb(185, 56, 56) | 959.42 / 959.42 | Нет |
| webkit | light | 430 | rgb(178, 245, 32) | rgb(185, 56, 56) | 960.08 / 960.08 | Нет |

[Chromium bounds JSON](chromium-wellbeing-action-bounds.json) · [WebKit bounds JSON](webkit-wellbeing-action-bounds.json)

## Матрица фактической типографики

Значения получены через getComputedStyle на 393 px, не выведены из макетов. Oswald предназначен для display, Inter - для body. Разница масштаба заголовков Today и Progress является существующим решением страниц, не нарушением совпадения текстовых ролей.

| Браузер | Тема | Компонент | Family | Font size | Weight | Line height | Роль/токен |
|---|---|---|---|---:|---:|---:|---|
| chromium | dark | Progress / page title | Oswald | 30px | 700 | 34.5px | --font-display + mobile page scale + --line-height-tight |
| chromium | dark | Progress / section selector | Inter | 15px | 600 | 22.5px | --font-body + --font-size-body + --font-weight-medium |
| chromium | dark | Today / page title | Oswald | 48px | 700 | 64.8px | --font-display + existing Today hero scale |
| chromium | dark | Today / primary workout title | Oswald | 32px | 800 | 32.96px | --font-display + existing workout density scale |
| chromium | dark | Quick Add / sheet title | Oswald | 20px | 600 | 23px | --font-display + 1.25rem section density + --font-weight-medium + --line-height-tight |
| chromium | dark | Quick Add / action label | Inter | 16px | 600 | 24px | --font-body + --font-size-body-lg + --font-weight-medium + --line-height-body |
| chromium | dark | DailyWellbeing / field label | Inter | 15px | 600 | 17.25px | --font-body + --font-size-body + --font-weight-medium + --line-height-tight |
| chromium | dark | DailyWellbeing / radio group legend | Inter | 15px | 700 | 22.5px | --font-body + --font-weight-strong + --line-height-body |
| chromium | dark | DailyWellbeing / primary action | Inter | 16px | 700 | 24px | --font-body + --font-size-body-lg + --font-weight-strong + --line-height-body |
| chromium | light | Progress / page title | Oswald | 30px | 700 | 34.5px | --font-display + mobile page scale + --line-height-tight |
| chromium | light | Progress / section selector | Inter | 15px | 600 | 22.5px | --font-body + --font-size-body + --font-weight-medium |
| chromium | light | Today / page title | Oswald | 48px | 700 | 64.8px | --font-display + existing Today hero scale |
| chromium | light | Today / primary workout title | Oswald | 32px | 800 | 32.96px | --font-display + existing workout density scale |
| chromium | light | Quick Add / sheet title | Oswald | 20px | 600 | 23px | --font-display + 1.25rem section density + --font-weight-medium + --line-height-tight |
| chromium | light | Quick Add / action label | Inter | 16px | 600 | 24px | --font-body + --font-size-body-lg + --font-weight-medium + --line-height-body |
| chromium | light | DailyWellbeing / field label | Inter | 15px | 600 | 17.25px | --font-body + --font-size-body + --font-weight-medium + --line-height-tight |
| chromium | light | DailyWellbeing / radio group legend | Inter | 15px | 700 | 22.5px | --font-body + --font-weight-strong + --line-height-body |
| chromium | light | DailyWellbeing / primary action | Inter | 16px | 700 | 24px | --font-body + --font-size-body-lg + --font-weight-strong + --line-height-body |
| webkit | dark | Progress / page title | Oswald | 30px | 700 | 34.5px | --font-display + mobile page scale + --line-height-tight |
| webkit | dark | Progress / section selector | Inter | 15px | 600 | 22.5px | --font-body + --font-size-body + --font-weight-medium |
| webkit | dark | Today / page title | Oswald | 48px | 700 | 64.800003px | --font-display + existing Today hero scale |
| webkit | dark | Today / primary workout title | Oswald | 32px | 800 | 32.959999px | --font-display + existing workout density scale |
| webkit | dark | Quick Add / sheet title | Oswald | 20px | 600 | 23px | --font-display + 1.25rem section density + --font-weight-medium + --line-height-tight |
| webkit | dark | Quick Add / action label | Inter | 16px | 600 | 24px | --font-body + --font-size-body-lg + --font-weight-medium + --line-height-body |
| webkit | dark | DailyWellbeing / field label | Inter | 15px | 600 | 17.25px | --font-body + --font-size-body + --font-weight-medium + --line-height-tight |
| webkit | dark | DailyWellbeing / radio group legend | Inter | 15px | 700 | 22.5px | --font-body + --font-weight-strong + --line-height-body |
| webkit | dark | DailyWellbeing / primary action | Inter | 16px | 700 | 24px | --font-body + --font-size-body-lg + --font-weight-strong + --line-height-body |
| webkit | light | Progress / page title | Oswald | 30px | 700 | 34.5px | --font-display + mobile page scale + --line-height-tight |
| webkit | light | Progress / section selector | Inter | 15px | 600 | 22.5px | --font-body + --font-size-body + --font-weight-medium |
| webkit | light | Today / page title | Oswald | 48px | 700 | 64.800003px | --font-display + existing Today hero scale |
| webkit | light | Today / primary workout title | Oswald | 32px | 800 | 32.959999px | --font-display + existing workout density scale |
| webkit | light | Quick Add / sheet title | Oswald | 20px | 600 | 23px | --font-display + 1.25rem section density + --font-weight-medium + --line-height-tight |
| webkit | light | Quick Add / action label | Inter | 16px | 600 | 24px | --font-body + --font-size-body-lg + --font-weight-medium + --line-height-body |
| webkit | light | DailyWellbeing / field label | Inter | 15px | 600 | 17.25px | --font-body + --font-size-body + --font-weight-medium + --line-height-tight |
| webkit | light | DailyWellbeing / radio group legend | Inter | 15px | 700 | 22.5px | --font-body + --font-weight-strong + --line-height-body |
| webkit | light | DailyWellbeing / primary action | Inter | 16px | 700 | 24px | --font-body + --font-size-body-lg + --font-weight-strong + --line-height-body |

[Computed typography Chromium](chromium-typography-computed.json) · [Computed typography WebKit](webkit-typography-computed.json)

## Проверки

- Unit 15/15 PASS, весь диапазон хранения 1..1440 минут.
- TypeScript, ESLint/Russian UI guard, Vite production build: PASS.
- E2E: Chromium/WebKit 20/20 PASS, повторная съёмка 393 px 4/4 PASS.
- Радиокнопки не рисуются через CSS-псевдоэлементы, нативная input семантика сохранена.
- Состояние на настоящем iPhone/Safari, Telegram, VoiceOver, системной клавиатуре и реальных данных: NOT_VERIFIED.
- Required CI обновлённого head подтверждать отдельно после push; не выдавать локальную зелёную матрицу за GitHub CI.

## Ссылки

- [HTML-галерея](gallery.html) · [SHA256-манифест](manifest.json)
- [Draft PR #1000](https://github.com/MikeMoore1337/your-fitness-coach/pull/1000)
- [Независимый технический комментарий](https://github.com/MikeMoore1337/your-fitness-coach/pull/1000#issuecomment-6183586473)

Визуальный аппрув предоставить только для конечного пакета. Merge/deploy отдельно.
