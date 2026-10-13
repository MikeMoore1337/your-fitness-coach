# #970 — пакет owner review для мобильного отчёта

Это proposal, а не production implementation и не AFTER-доказательство. Подготовлено от актуального `origin/master` на synthetic data; пользовательские фотографии, замеры и профили не использовались.

## Контекст и границы

- Issue: [#970](https://github.com/MikeMoore1337/your-fitness-coach/issues/970).
- Base SHA: `11cff463834fd41c1392d646f6baaf361ac9bebc`.
- Не переоткрывается закрытый #874.
- API, БД, факты, даты, происхождение цели, Б/Ж/У, PDF/ReportLab и privacy boundaries не меняются.
- Desktop и A4 PDF сохраняют текущую таблицу.

## Предлагаемый вариант B

На ширине 320–430 px каждая запись цели становится одной доступной записью с явными подписями:

1. верхняя строка — дата действия и источник;
2. значения — `Ккал` и `Белок / жиры / углеводы`;
3. длинные названия переносятся по границам контейнера, но слова не режутся;
4. числовые значения остаются фактическими и табличными по цифрам;
5. empty и one-record состояния сохраняют текущую семантику.

Это минимальная мобильная адаптация существующей информации. Вариант не меняет алгоритм, контракт API или печатную композицию. После явного owner approval реализация должна переиспользовать текущие YFC tokens, цвета Dark/Light и доступные touch/focus states.

## Визуальный пакет

Макет выполнен в существующем чёрный/лаймовый и белый/лаймовый языке YFC, с синтетическими значениями:

| Движок / тема | Макет |
| --- | --- |
| Chromium 393, Dark | [PNG](mockups/option-b-chromium-393-dark.png) |
| Chromium 393, Light | [PNG](mockups/option-b-chromium-393-light.png) |
| WebKit 393, Dark | [PNG](mockups/option-b-webkit-393-dark.png) |
| WebKit 393, Light | [PNG](mockups/option-b-webkit-393-light.png) |

Исходник макета: [970-option-b.html](mockups/970-option-b.html).

## Owner decision required

Подтвердить или отклонить вариант B для мобильной ширины. Альтернатива A — оставить таблицу и добавить доступный горизонтальный overflow с минимальными ширинами; она меньше меняет композицию, но требует горизонтального жеста.

До явного выбора не создаётся production implementation #970, не обновляются visual goldens и не меняется PDF. После выбора потребуются реальные AFTER для 320/360/393/430, Dark/Light, Chromium/WebKit, empty/one-record/populated/long-content, browser print PDF и required CI.

`PROPOSAL_ONLY=true`
`OWNER_DESIGN_APPROVAL=PENDING`
`PRODUCTION_CODE_CHANGED=false`
`MERGE=false`
`DEPLOY=false`
