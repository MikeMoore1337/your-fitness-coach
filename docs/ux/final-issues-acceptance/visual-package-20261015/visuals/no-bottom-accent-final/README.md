# Финальная визуальная правка #978 - без нижней лаймовой полосы

**Решение владельца:** убрать яркую лаймовую грань снизу **в обеих темах**; ранее принятые изменения PR #1000 не менять.

## Итоговый вариант

- Выбранный ответ распознаётся по изменённому фону, нейтральной рамке и выбранной нативной радиокнопке.
- В Dark и Light `border-bottom-color` совпадает с `border-top-color`, толщина снизу **1 px**, без отдельной полосы.
- В `box-shadow` выбранной опции нет лаймового акцента `rgb(178, 245, 32)`. Радиокнопка остаётся лаймовой.
- Входные значения, ввод сна в часах, действия одной строкой, выход из формы, API и данные не менялись.

## Повторная проверка после устранения нижнего рельефа (393 px)

Отдельно для выбранных ответов в двух группах формы убран `box-shadow`, содержащий нижний декоративный рельеф. Общие токены оформления других элементов не менялись. Цвет и скругление выбранной поверхности, нейтральная рамка, текст и лаймовая нативная радиокнопка сохранены.

| Браузер | Тема | Вся форма | «Как спалось?» | «Как себя ощущали?» |
| --- | --- | --- | --- | --- |
| Chromium | Dark | [PNG](chromium-wellbeing-actions-393-dark.png) | [PNG](chromium-wellbeing-selected-sleep-393-dark.png) | [PNG](chromium-wellbeing-selected-mood-393-dark.png) |
| Chromium | Light | [PNG](chromium-wellbeing-actions-393-light.png) | [PNG](chromium-wellbeing-selected-sleep-393-light.png) | [PNG](chromium-wellbeing-selected-mood-393-light.png) |
| WebKit | Dark | [PNG](webkit-wellbeing-actions-393-dark.png) | [PNG](webkit-wellbeing-selected-sleep-393-dark.png) | [PNG](webkit-wellbeing-selected-mood-393-dark.png) |
| WebKit | Light | [PNG](webkit-wellbeing-actions-393-light.png) | [PNG](webkit-wellbeing-selected-sleep-393-light.png) | [PNG](webkit-wellbeing-selected-mood-393-light.png) |

Playwright: 4/4 адресных сценария, Chromium/WebKit. Проверены 320/360/390/393/430 px, обе темы, оба выбранных ответа; `box-shadow: none`, одинаковый верхний и нижний цвет рамки, сохранение нативных индикаторов и кнопок действий в одной строке. Отдельно успешны typecheck, lint и build. Это локальные скриншоты на синтетических данных, не доказательство работы на физическом iPhone.

## Одновременное сравнение Dark и Light на 390 px

| Браузер | Тёмная тема - выбранное | Светлая тема - выбранное | Полный экран Dark | Полный экран Light |
|---|---|---|---|---|
| Chromium | [PNG](chromium-selected-390-dark.png) | [PNG](chromium-selected-390-light.png) | [PNG](chromium-full-390-dark.png) | [PNG](chromium-full-390-light.png) |
| WebKit | [PNG](webkit-selected-390-dark.png) | [PNG](webkit-selected-390-light.png) | [PNG](webkit-full-390-dark.png) | [PNG](webkit-full-390-light.png) |

## Измерения

- [Chromium JSON, 320/360/390/430 px, обе темы](chromium-computed-320-430.json)
- [WebKit JSON, 320/360/390/430 px, обе темы](webkit-computed-320-430.json)

Адресные Playwright-тесты проверяют отсутствие яркой нижней грани и лаймовой тени, сохранность native-radio semantics и геометрию двух кнопок на одной строке.

**Ограничения:** не проверялись реальные iPhone/Safari, native Telegram, VoiceOver. Скриншоты сделаны на синтетических данных. PR #1000 остаётся Draft до отдельного owner approval. Merge, deploy и закрытие Issues не выполнялись.

Это **единственный актуальный вариант** для повторной визуальной приёмки #978. Ранее утверждённые изменения #979 и остальных частей #978 пересматривать не требуется.
