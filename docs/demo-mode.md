# Демо-режим

Демо-режим показывает в Web и Mobile Web три подготовленных сценария без регистрации и без записи в
пользовательские таблицы: `Тренировка`, `Питание и прогресс` и `Работа тренера`. Точка входа есть
в hero лендинга и в отдельной секции с явным объяснением границы. Сценарии работают внутри
ограниченного production `AppShell`, поэтому посетитель видит ту же навигацию, семантические токены
и базовые разделы, что и в обычном кабинете.

## Архитектурная граница

- публичный frontend route — `/demo`;
- публичный API — `/api/v1/demo/sessions` и дочерние endpoints текущей demo session;
- capability всегда явно равна `demo` и передаётся отдельным заголовком `X-Demo-Session`;
- demo token не является access/refresh token и не принимается authenticated endpoints;
- state хранится только в памяти backend-процесса, разделён криптографически случайным token,
  истекает через 30 минут и сбрасывается при restart процесса;
- token хранится в `sessionStorage` текущей вкладки. Он не попадает в `localStorage`, cookies,
  query string, analytics или account state;
- fixtures детерминированы, не содержат реальных снимков пользователей и имеют версию
  `demo-curated-v2`.

Демо доступно только как браузерный продуктовый маршрут. Если `/demo` открыт как подписанный Telegram
Mini App launch, frontend до авторизации удаляет оставшиеся demo credentials и переводит запуск в
обычный `/app`. Demo UI, demo navigation и demo mutations в TMA не открываются.

## Единая production-поверхность

`/demo` не содержит отдельного кабинета с упрощёнными экранами. `DemoCabinet` отвечает только за
границу демо, выбор сценария, reset, route и conversion, а продуктовый компонентный tree остаётся
общим:

| Поверхность | Общий компонент | Разница в демо |
| --- | --- | --- |
| Сегодня и тренировка | `MiniAppPage` → `TodayDashboard` | Изолированный demo transport и подготовленные данные |
| План и программы | `MiniAppPage` → `TemplatesList`, `SchedulePanel`, `ProgramBuilder` | Просмотр; управление отключено capability registry |
| Питание | `MiniAppPage` → `NutritionPage`/diary/food controls | Изменения живут только в текущей demo session |
| Прогресс и история | `MiniAppPage` → `ProgressExperience` | Чтение подготовленных production-shaped DTO |
| Профиль | `MiniAppPage` → текущая profile composition | Account/profile writes отключены и отображаются read-only |
| Тренер | `CoachPage` и его `ClientAnalytics`/feedback | Три curated клиента; комментарий сохраняется только в demo session |

Production authenticated runtime продолжает ходить в обычный API. Demo runtime отправляет тот же
`path`/`method`/body в один явный server-side transport endpoint с `X-Demo-Session`; это не
перехват `fetch`, service worker или подмена глобального API. Навигационные ссылки production tree
в демо преобразуются только в allowlisted `/demo` routes. `Продолжить` не вызывает product action:
он лишь открывает, прокручивает или фокусирует реальную production-поверхность.

Capability boundary для текущего демо:

| Capability | Поведение |
| --- | --- |
| Workout и nutrition | Разрешены безопасные переходы и изменения в session-scoped state |
| Coach feedback | Разрешён комментарий к выбранному клиенту и тренировке в session-scoped state |
| Progress writes, profile, programs и catalog | Read-only/disabled с объяснением в той же поверхности |
| Coach management, invites, notifications, Telegram/OAuth, exports, deletes, providers и AI jobs | Не вызываются; серверный allowlist отвечает безопасным отказом |

Таким образом, demo token является только транспортным контекстом и не превращается в
`Authorization`, cookie, account identity или доступ к production user/account/coach tables.

## Ограниченный кабинет и маршрут

Allowlist кабинета включает `Сегодня`, `План`, `Питание`, `Прогресс` и подготовленный контекст клиента
для сценария тренера. Сценарий сопровождается компактным встроенным маршрутом из четырёх шагов:
`План → Тренировка → Результат → Прогресс`, `Дневник → Продукт → Итог → Прогресс` или
`Клиент → Результат → Комментарий → Готово`. Навигация по разделам остаётся свободной, а маршрут
предлагает только следующий причинно связанный шаг и может быть скрыт с возможностью повторного
открытия.

Все разделы читают один связный snapshot. Подготовленный fixture содержит четыре недели истории
тренировок, расписание активной программы, подходы, веса и объём, заполненные и неполные дни
питания, динамику объёма, замеры и регулярность. Сценарий тренера содержит три вымышленных состояния:
`Алексей` — стабильная динамика, `Мария` — пропуски и нерегулярность, `Иван` — регулярность без
изменения объёма. Подтверждённая тренировка меняет факты прогресса, добавленный продукт меняет
дневной итог и его отражение в прогрессе, а комментарий тренера существует только до конца текущей
demo session. Остальные разделы production-кабинета в demo navigation отсутствуют.

Постоянная граница показывает `Демо-режим · данные не сохраняются`, выбор сценария, `Начать заново`
и `Выйти из демо`. Верхняя граница не дублируется в боковой навигации. После meaningful action и
завершения маршрута появляется conversion-блок с заголовком `Готово. Вы посмотрели основной
сценарий`, кнопками `Начать со своими данными` и `Попробовать другой сценарий`. Перед переходом к
login удаляются все demo credentials; после регистрации или входа открывается чистый `/app` без
переноса fixture state.

На desktop боковой rail фиксирован по высоте viewport: центральная навигация прокручивается отдельно,
а utility-блок с `Тема` и `Выйти из демо` остаётся видимым. В rail нет повторного заголовка кабинета,
отдельной сессии или avatar. Переключатель в верхней границе использует полные значения
`Тренировка|Питание и прогресс|Работа тренера`; на Mobile Web он остаётся доступным в потоке, а
пункт нижней навигации называется `Сценарии`. Технические слова `fixture`, `snapshot` и названия
внутренних контрактов не выводятся посетителю.

Текущий production deployment сохраняет ровно одного активного backend worker, поэтому process-local store даёт
предсказуемую ephemeral isolation без schema и migration. Если topology станет multi-worker,
маршрутизацию или общий ephemeral store нужно решить отдельной architecture task до увеличения
числа workers; перенос state в production user tables запрещён.

## Разрешённые действия

Demo API использует allowlist переходов:

- `self_training`: открыть план, начать тренировку, заполнить и подтвердить каждый подход,
  использовать rest/next переходы, завершить занятие полностью или через подтверждение неполного
  результата и открыть Progress;
- `nutrition`: открыть дневник, добавить подготовленный недавний продукт, открыть дневной итог и
  показатели;
- `trainer`: выбрать одно из трёх подготовленных состояний и сохранить короткий контекстный
  комментарий до конца demo session;
- любой сценарий: получить текущее состояние и вернуть fixture через reset.

Неизвестные и прямые попытки вызвать приглашение, notification, provider, export, delete,
link/unlink или другое внешнее/account действие получают `403`. Demo endpoints не зависят от БД,
бота, email, notification worker или food provider.

## Срок жизни и восстановление

Reload, background/foreground и повторное открытие в той же вкладке читают то же состояние, пока
session действительна. `410 Gone` означает, что TTL истёк или backend был перезапущен; интерфейс
предлагает начать новую изолированную session. Reset возвращает исходный fixture и продлевает TTL.
Одновременные вкладки получают независимые tokens и не видят изменения друг друга.

В Web и Mobile Web используется один component tree. `/demo` не оборачивается в
`AuthProvider`/`AuthGate`, а raw Telegram `initData` никогда не отправляется в demo API. Подписанный
TMA launch является только безопасной границей перехода в обычный авторизованный продукт.

## Проверка

Backend tests покрывают determinism, isolation, concurrent sessions, связность cabinet snapshot,
reset, expiry, forbidden actions, direct production API attempts и отсутствие записей в `User`.
Frontend unit tests покрывают credential-free requests, route allowlist, expiry recovery и
disabled/explanation state. Continuous Playwright smoke `frontend/tests/e2e/demo-mode.spec.ts`
проверяет три сценария в Mobile Web, viewport-матрицу `360/390/430/768/1280×720/1366×768/1440×900/1920×1080`,
fixed rail, safe-area geometry, keyboard, reload/reset, Light/Dark, reduced motion и error states.
Отдельная negative-проверка подтверждает, что подписанный TMA launch не открывает demo UI и не
вызывает demo API.

Landing и demo публикуют privacy-safe события без PII и значений тренировок: источник выбора на
лендинге (`hero` или `section`), выбранный сценарий, старт/скрытие/повторное открытие/завершение
маршрута, meaningful action, переход к своим данным и выбор другого сценария.

Browser viewport не является проверкой реального устройства; само демо в Telegram Android/iOS не
поддерживается по продуктовому решению.
