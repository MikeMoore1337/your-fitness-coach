# Product V11 #848 - безопасное уточнение ручного аудита PostgreSQL

Дата: 20 октября 2026 года. Реализация: workflow `.github/workflows/production-capacity-audit.yml`. Это **ручной, доступный только владельцу и только для чтения** запуск в GitHub Actions, а **не обязательный production preflight** и не самостоятельное разрешение на развёртывание.

## Изменения

Аудит дополнен только обезличенными числовыми наблюдениями:

- `POSTGRES_SUPERUSER_RESERVED_CONNECTIONS` и `POSTGRES_RESERVED_CONNECTIONS` (на PostgreSQL ниже 16 значение второго параметра принимается равным 0; на PostgreSQL 16+ неизвестное значение остаётся `UNAVAILABLE`);
- `POSTGRES_USABLE_NON_RESERVED_CONNECTIONS` - `max_connections - superuser_reserved_connections - reserved_connections`;
- `POSTGRES_UNRESERVED_HEADROOM` - консервативная разность usable capacity и текущего количества процессов из `pg_stat_activity`, **не** projected rollout budget;
- `POSTGRES_DECLARED_YFC_SESSIONS` - количество сессий с точным именем приложения из утверждённого набора YFC;
- `POSTGRES_NON_YFC_SESSIONS` - остальные сессии, включая те, у которых имя не указано;
- `POSTGRES_UNATTRIBUTED_SESSIONS` - подмножество остальных сессий с пустым/NULL `application_name`.

`application_name` заявляет клиент подключения и **не доказывает** его идентичность. Сборщик не приписывает неизвестные сессии YFC. Числа разных SQL-операторов могут отражать слегка разные мгновения времени, поэтому аудит не заменяет единый атомарный снимок production.

Результат всегда содержит `POSTGRES_BUDGET_VERDICT=NOT_VERIFIED`. Даже `PRODUCTION_CAPACITY_PROBE=PASS` означает только, что read-only host probe завершился; он не даёт разрешение на миграцию, запуск candidate, backup или изменение инфраструктуры. Ошибка PostgreSQL или неполная видимость возвращают `UNAVAILABLE`, а не ноль.

## Валидация

Добавлены регрессии в `tests/test_release_safeguards.py` на наличие числовых полей, версионно-зависимых reservation, точной статической allowlist меток приложений, отсутствие действий по изменению production и проверку malformed session counts. При несогласованных `total / declared_yfc / unattributed` возвращается `UNAVAILABLE`, а не `PASS`.

## Выполнение

Запуск - только через штатную страницу GitHub Actions **Production capacity audit** в ветке `master` от имени владельца. Требуются существующие защищённые секреты среды production; новые токены, ключи и сервисы не добавляются.

Аудит не запускается автоматически при merge, не изменяет production environment, контейнеры или PostgreSQL и не сохраняет секреты в лог. Этот PR относится только к `.github/`, `tests/`, `docs/`, поэтому согласно `scripts/deployment_scope.py` должен классифицироваться как **no-deploy**.

## Что по-прежнему блокирует #848

- Независимый trusted collector из Draft PR #1122 ещё не развёрнут и не проверен на реально работающих контейнерах.
- Точные pools/replicas, фактическая атрибуция и распределение соединений по фазам развёртывания ещё не доказаны.
- Числовой резерв и его источник должны быть отдельно одобрены владельцем.
- Production-gate перед backup/migration/candidate пока не активирован.
- Обязательный успешный read-only dry run с достоверным окружением отсутствует.

Следовательно, этот ручной аудит даёт **дополнительную диагностику для решения #848, но не снимает production-блокировку** и не разрешает слияние ожидающих PR #1126/#1131.
