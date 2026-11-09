# Issue #885 — макет импорта питания

**Статус:** проектный визуальный пакет для согласования. Это не работающий импорт. Все продукты и результаты вымышлены, запросов к API нет. HTML-макет имитирует переходы и не читает файлы и ссылки. Приложение не изменялось.

Исходный `dev`: [`1d8dedab5d6e6e6b04edf44f9e53a2e4b579b741`](https://github.com/MikeMoore1337/your-fitness-coach/commit/1d8dedab5d6e6e6b04edf44f9e53a2e4b579b741). Задача: [#885](https://github.com/MikeMoore1337/your-fitness-coach/issues/885), эпик [#880](https://github.com/MikeMoore1337/your-fitness-coach/issues/880).

## Как смотреть

Скачайте и откройте [prototype.html](prototype.html) в браузере. Верхний переключатель показывает отдельные состояния и тему. Кнопки в нём показывают заранее заданные переходы: фактической загрузки, проверки или записи нет. Точка входа в дневник показана как упрощённый фрагмент, а не снимок готового приложения.

В каждом PNG показаны верх и низ состояния при прокрутке; поэтому неподвижная мобильная навигация видна на обоих кадрах. Все снимки сделаны с синтетическими данными.

| Пакет | Телефон 393 × 844 | Desktop 1280 × 800 |
|---|---|---|
| Точка входа, файл, ссылка, получение, проверка, предпросмотр, сопоставление | [Тёмная](review/01-flow-dark-393.png) · [светлая](review/01-flow-light-393.png) | [Тёмная](review/01-flow-dark-1280.png) · [светлая](review/01-flow-light-1280.png) |
| Подтверждение, ожидание, частичный и полный результат | [Тёмная](review/02-confirm-results-dark-393.png) · [светлая](review/02-confirm-results-light-393.png) | [Тёмная](review/02-confirm-results-dark-1280.png) · [светлая](review/02-confirm-results-light-1280.png) |
| Ошибки, повторная проверка и отмена | [Тёмная](review/03-errors-dark-393.png) · [светлая](review/03-errors-light-393.png) | [Тёмная](review/03-errors-dark-1280.png) · [светлая](review/03-errors-light-1280.png) |

Дополнительно: [320/360/393/430, тёмная тема](review/04-widths-dark.png), [те же размеры, светлая тема](review/04-widths-light.png); [WebKit, тёмная](review/05-webkit-dark.png) и [WebKit, светлая](review/05-webkit-light.png). Остальные таблицы — Chromium.

## Предлагаемый путь

1. Из строки «Импорт питания» в разделе питания открыть отдельный экран и выбрать файл либо ссылку. При неработающей ссылке предложить файл.
2. Показать получение и проверку, затем количество строк по исходам, фильтр и сведения без подстановки неизвестных значений.
3. Для спорной строки показать данные из источника и кандидата рядом, объяснить неизвестную массу и дать явный выбор. **Выбор совпадения для общего каталога на макете — целевой сценарий, сейчас `BLOCKED_DEPENDENCY`.** В текущем `dev` общий `resolve` относится к планированию записей дневника; его нельзя выдавать за разрешение конфликта каталога.
4. Перед записью отдельно показать возможную публикацию в общий каталог, повторное использование, пропуск и непубликуемые строки. Личная история в этой задаче не переносится.
5. После ответа отделить подтверждённые сервером результаты от строк, исключённых пользователем или не прошедших проверку. При потере ответа показать неизвестный результат; повторная проверка в макете предполагает тот же ключ и те же параметры подтверждения, а не новый импорт.

## Проверенные границы `dev`

| Возможность | Backend | Frontend | Основание |
|---|---|---|---|
| Файл CSV FatSecret | BLOCKED | MISSING | В [реестре адаптеров `dev`](https://github.com/MikeMoore1337/your-fitness-coach/blob/1d8dedab5d6e6e6b04edf44f9e53a2e4b579b741/backend/fitminiapp_api/services/nutrition_import_runner.py#L41) нет адаптера. [PR #1469](https://github.com/MikeMoore1337/your-fitness-coach/pull/1469) открыт как Draft. |
| Файл PDF | MISSING | MISSING | [Текущий draft принимает только CSV](https://github.com/MikeMoore1337/your-fitness-coach/blob/1d8dedab5d6e6e6b04edf44f9e53a2e4b579b741/backend/fitminiapp_api/services/nutrition_import_drafts.py#L133); парсер — [#913](https://github.com/MikeMoore1337/your-fitness-coach/issues/913). |
| Получение по URL | MISSING | MISSING | В [маршрутах импорта](https://github.com/MikeMoore1337/your-fitness-coach/blob/1d8dedab5d6e6e6b04edf44f9e53a2e4b579b741/backend/fitminiapp_api/api/v1/nutrition_imports.py#L149) нет приёма ссылки; транспорт — [#912](https://github.com/MikeMoore1337/your-fitness-coach/issues/912). |
| Черновик и предпросмотр | PARTIAL | MISSING | Общий движок и [предпросмотр каталога](https://github.com/MikeMoore1337/your-fitness-coach/blob/1d8dedab5d6e6e6b04edf44f9e53a2e4b579b741/backend/fitminiapp_api/services/nutrition_catalog_import.py#L796) существуют, но FatSecret-адаптер в `dev` не зарегистрирован. |
| Автоматическое сопоставление | PARTIAL | MISSING | [План каталога](https://github.com/MikeMoore1337/your-fitness-coach/blob/1d8dedab5d6e6e6b04edf44f9e53a2e4b579b741/backend/fitminiapp_api/services/nutrition_catalog_import.py#L419) содержит исходы и предложения; сквозной FatSecret-сценарий не подтверждён. |
| Ручной выбор продукта для каталога | BLOCKED | MISSING | [Общий resolve](https://github.com/MikeMoore1337/your-fitness-coach/blob/1d8dedab5d6e6e6b04edf44f9e53a2e4b579b741/backend/fitminiapp_api/services/nutrition_import_drafts.py#L213) строит план записи дневника. В плане каталога подтверждённого пользовательского разрешения такого конфликта не обнаружено. |
| Подтверждение каталога | PARTIAL | MISSING | [Отдельный catalog confirm](https://github.com/MikeMoore1337/your-fitness-coach/blob/1d8dedab5d6e6e6b04edf44f9e53a2e4b579b741/backend/fitminiapp_api/services/nutrition_catalog_import.py#L837) существует. Доступный в Draft адаптер #884 не получил прав и классификации для публикации. |
| Повтор подтверждения | PARTIAL | MISSING | Catalog confirm возвращает сохранённую квитанцию только для совпадающих ключа и отпечатка запроса. Сквозной сценарий с FatSecret и восстановление после потери ответа не проверены. |

CSV-ограничение текущего общего валидатора — [512 КБ](https://github.com/MikeMoore1337/your-fitness-coach/blob/1d8dedab5d6e6e6b04edf44f9e53a2e4b579b741/backend/fitminiapp_api/services/nutrition_import_validation.py#L17); ограничения будущего PDF не установлены. Не использовать обычный `/{draft_id}/confirm` для каталога: он создаёт записи дневника.

## Проверка макета

- Playwright 1.62.1; Chromium 151.0.7922.34 и WebKit 26.5; 19 состояний × 5 размеров × 2 темы × 2 движка = **380 комбинаций рендера**, без обнаруженного горизонтального overflow или перекрытия действий панелью при прокрутке к концу.
- В обоих движках проверены переход от точки входа, переключение вкладок клавиатурой, видимость поля ссылки после уменьшения окна до 393 × 500, фильтр, обязательный выбор для конфликта и отображение выбранного варианта на подтверждении. HTTP-запросов при проверке не зарегистрировано.
- Это локальная проверка **макета**, не E2E приложения, не подтверждение доступности по WCAG и не проверка серверного контракта. Реальные клавиатуры, физические iOS/Android, PWA и Telegram Mini App — `NOT_RUN`. Реальные файлы, ссылки и production — `NOT_RUN`.
- Независимое code/security review — `NOT_RUN`. PR, merge, deploy, изменение флагов и закрытие Issue не выполнялись.

## Решение владельца

Просьба оценить одним решением расположение точки входа, последовательность экранов, разрешение спорной строки, отдельное согласие на общий каталог и обработку ошибок в обеих темах и размерах. Ответ «Принимаю макет #885» утверждает показанное визуальное направление; неподтверждённые серверные возможности остаются блокирующими зависимостями. Визуальное решение не является разрешением на merge или deploy.
