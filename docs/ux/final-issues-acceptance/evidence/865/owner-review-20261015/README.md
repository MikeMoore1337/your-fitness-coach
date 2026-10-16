# #865 — owner-review proposal: верхняя область Progress

Это один законченный визуальный proposal перед production-реализацией. Он изолирован в
`docs/ux/final-issues-acceptance/evidence/865/owner-review-20261015/`, не импортируется приложением
и не меняет production TS/CSS, API, расчёты или соседние задачи.

## Решение, вынесенное на предварительное согласование

- **Общий title-row:** «Прогресс» и компактная однострочная «О показателях» всегда остаются в
  одном верхнем ряду.
- **Раскрытие:** пояснение и ссылка переходят в собственную строку полной ширины heading-блока;
  они больше не сжимаются до правой колонки и не перекрывают заголовок.
- **Desktop:** title-блок слева и выбор периода справа образуют одну верхнюю композицию; форма
  «Свой период» растёт только внутри своей колонки, а отчёт остаётся под периодом.
- **Даты:** в proposal текст полей выровнен от начала и имеет отдельное место под календарь;
  `01.01.2025` и `30.01.2025` видны целиком. Это визуально фиксирует ожидаемый результат,
  а не утверждает ещё выполненную production-проверку.
- **Система:** сохранены YFC lime/black/white, Oswald/Inter, selected-state SegmentedControl,
  текущие touch targets и фирменные радиусы.

Раскрытый кадр намеренно показывает сложное сочетание: help раскрыт и «Свой период» открыт.
Свёрнутый кадр показывает штатный 30-дневный период. Полная автоматизированная матрица четырёх
сочетаний состояний остаётся обязательной частью последующей реализации.

## Пакет для просмотра

Кадры сняты из изолированного HTML-прототипа в Chromium с реальными viewport-размерами. Один
Light-пакет и один Dark-пакет покрывают representative endpoints диапазонов: 320/430px mobile и
1280/1440px desktop. При реализации матрица будет расширена до 320/360/393/430 и
1280/1440/1920/2560 в Chromium и WebKit.

### Light

| Surface | Closed | Expanded + custom period |
| --- | --- | --- |
| Mobile 320px | [PNG](mockups/chromium-320-light-closed.png) | [PNG](mockups/chromium-430-light-expanded-custom.png) |
| Desktop 1280px | [PNG](mockups/chromium-1280-light-closed.png) | [PNG](mockups/chromium-1440-light-expanded-custom.png) |

### Dark

| Surface | Closed | Expanded + custom period |
| --- | --- | --- |
| Mobile 320px | [PNG](mockups/chromium-320-dark-closed.png) | [PNG](mockups/chromium-430-dark-expanded-custom.png) |
| Desktop 1280px | [PNG](mockups/chromium-1280-dark-closed.png) | [PNG](mockups/chromium-1440-dark-expanded-custom.png) |

Source: [prototype.html](prototype.html) · [prototype.css](prototype.css).

## Что нужно решить владельцу

1. Одобрить или отклонить именно эту композицию верхней области для дальнейшей реализации.
2. Подтвердить, что раскрытая строка пояснения должна оставаться отдельной полноширинной строкой
   под title-row на mobile и heading-блоком слева на desktop.
3. Подтвердить, что полная видимость дат слева в полях «Свой период» соответствует ожидаемой
   локальной форме.

Это согласование макета не разрешает merge, deploy, закрытие Issue или выход из Draft. После
одобрения потребуется отдельный implementation commit, DOM-геометрия, проверка видимости текста
внутри `input`, Chromium/WebKit и новый реальный AFTER-пакет.

## Scope / coverage #865

Этот proposal адресует только верхнюю область, раскрытие и связанную с ней форму периода. Уже
подтверждённые ранее пункты #865 — верхняя навигация разделов, компактный обзор, выбранные
периоды, truthful no-data/insufficient handling и переходы в подразделы — не переобъявляются
завершёнными этим макетом. Owner visual acceptance, release и closeout Issue остаются отдельными
воротами; #873/#874/#823/#867 не входят в scope.
