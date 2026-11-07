# #953 — объяснимые рекомендации питания

Это макет на вымышленных данных, а не работающая функция. Основа — существующие компоненты и токены YFC на `dev` `266a1e9366e85e061923bc428134868d13f90da6` и компактный дневник из #1433. Общий экран дневника не переработан.

[HTML-макет](preview.html) использует стили и шрифты этого checkout. Для взаимодействия откройте его через локальный HTTP-сервер из корня репозитория; панель сверху переключает состояния, тему и режим. Данные в макете не сохраняются и API не вызывается. Снимки ниже показывают только область изменяемого компонента без панели макета.

## Что предлагается

- Отчёт называет период и покрытие: в примере 4 из 5 завершённых дней ниже действовавших тогда целей; незавершённые и пропущенные дни не входят в сравнение.
- В дневнике по-прежнему видны два варианта и доступно раскрытие остальных. В плане показан весь список, как в действующем режиме.
- Перед подтверждением таблица показывает итог до выбора, вклад выбранного количества и итог после него. Неизвестная клетчатка остаётся `—`; цель, её версия и источник показаны отдельно.
- Заданный пользователем предел демонстрируется отдельно: при превышении кнопка подтверждения недоступна, количество можно изменить. Если сведений о предпочтениях и ограничениях нет, макет этого не скрывает.
- Изменение данных после проверки требует обновить расчёт. Добавление в план не означает, что еда съедена; незавершённый день не входит в сравнение завершённых дней отчёта.

Показанные числа — только пример: 1 200 + 180 = 1 380 ккал, белок 85 + 18 = 103 г, жиры 45 + 6 = 51 г, углеводы 110 + 12 = 122 г. Для клетчатки итог неизвестен, так как значение продукта неизвестно.

## Галерея

Chromium, окно **393 × 844** и **1280 × 900 CSS px**; снимки показывают всю область компонента.

| Состояние | 393 Dark | 393 Light | 1280 Dark | 1280 Light |
| --- | --- | --- | --- | --- |
| Отчёт и объяснение | [открыть](evidence/chromium-393-dark-report-diary.png) | [открыть](evidence/chromium-393-light-report-diary.png) | [открыть](evidence/chromium-1280-dark-report-diary.png) | [открыть](evidence/chromium-1280-light-report-diary.png) |
| Варианты дневника | [открыть](evidence/chromium-393-dark-choices-diary.png) | [открыть](evidence/chromium-393-light-choices-diary.png) | [открыть](evidence/chromium-1280-dark-choices-diary.png) | [открыть](evidence/chromium-1280-light-choices-diary.png) |
| Все варианты дневника | [открыть](evidence/chromium-393-dark-choices-expanded-diary.png) | [открыть](evidence/chromium-393-light-choices-expanded-diary.png) | [открыть](evidence/chromium-1280-dark-choices-expanded-diary.png) | [открыть](evidence/chromium-1280-light-choices-expanded-diary.png) |
| Варианты плана | [открыть](evidence/chromium-393-dark-choices-plan.png) | [открыть](evidence/chromium-393-light-choices-plan.png) | [открыть](evidence/chromium-1280-dark-choices-plan.png) | [открыть](evidence/chromium-1280-light-choices-plan.png) |
| Проверка дневника | [открыть](evidence/chromium-393-dark-preview-diary.png) | [открыть](evidence/chromium-393-light-preview-diary.png) | [открыть](evidence/chromium-1280-dark-preview-diary.png) | [открыть](evidence/chromium-1280-light-preview-diary.png) |
| Проверка плана | [открыть](evidence/chromium-393-dark-preview-plan.png) | [открыть](evidence/chromium-393-light-preview-plan.png) | [открыть](evidence/chromium-1280-dark-preview-plan.png) | [открыть](evidence/chromium-1280-light-preview-plan.png) |
| Превышен заданный предел | [открыть](evidence/chromium-393-dark-limit-diary.png) | [открыть](evidence/chromium-393-light-limit-diary.png) | [открыть](evidence/chromium-1280-dark-limit-diary.png) | [открыть](evidence/chromium-1280-light-limit-diary.png) |
| Данные изменились | [открыть](evidence/chromium-393-dark-stale-diary.png) | [открыть](evidence/chromium-393-light-stale-diary.png) | [открыть](evidence/chromium-1280-dark-stale-diary.png) | [открыть](evidence/chromium-1280-light-stale-diary.png) |
| Нет подходящих вариантов | [открыть](evidence/chromium-393-dark-empty-diary.png) | [открыть](evidence/chromium-393-light-empty-diary.png) | [открыть](evidence/chromium-1280-dark-empty-diary.png) | [открыть](evidence/chromium-1280-light-empty-diary.png) |
| Нет цели | [открыть](evidence/chromium-393-dark-no-target-diary.png) | [открыть](evidence/chromium-393-light-no-target-diary.png) | [открыть](evidence/chromium-1280-dark-no-target-diary.png) | [открыть](evidence/chromium-1280-light-no-target-diary.png) |
| Результат дневника | [открыть](evidence/chromium-393-dark-result-diary.png) | [открыть](evidence/chromium-393-light-result-diary.png) | [открыть](evidence/chromium-1280-dark-result-diary.png) | [открыть](evidence/chromium-1280-light-result-diary.png) |
| Результат плана | [открыть](evidence/chromium-393-dark-result-plan.png) | [открыть](evidence/chromium-393-light-result-plan.png) | [открыть](evidence/chromium-1280-dark-result-plan.png) | [открыть](evidence/chromium-1280-light-result-plan.png) |

Проверка на **320 × 720**: [Dark](evidence/chromium-320-dark-preview-diary.png) · [Light](evidence/chromium-320-light-preview-diary.png).

## Проверки и ограничения

Локальный Chromium сделал 50 снимков. Автоматически проверены отсутствие горизонтального переполнения на 320/393/1280 px, пересчёт примера при изменении количества, раскрытие дневниковых вариантов, полный список плана и блокировка/разблокировка кнопки при изменении количества относительно заданного предела. Это проверки макета, не API и не базы данных.

WebKit, реальный Telegram WebView, физические устройства, экранные дикторы и системный zoom 200% для макета не проверялись. Состояния загрузки, ошибок сервера и реальной записи будут проверяться при реализации. Наличие известного источника данных не означает подтверждённой персональной или медицинской точности.

**Решение владельца:** принять этот пакет как визуальный контракт для реализации #953 либо указать конкретные изменения. Одобрение макета не означает приёмку работающего интерфейса, merge или production release.
