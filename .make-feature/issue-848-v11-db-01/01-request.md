# Original request

Your Fitness Coach — Product V11-DB-01: PostgreSQL Connection Budget & Fail-closed Preflight

Репозиторий: https://github.com/MikeMoore1337/your-fitness-coach
Issue: https://github.com/MikeMoore1337/your-fitness-coach/issues/848
Родитель: #814
Зависимость: #815
Основная ветка: master
Приоритет: P0

## Разрешение владельца

После активации V11 разрешаю:

- read-only исследование PostgreSQL topology;
- безопасную подготовку connection budget model;
- реализацию и тестирование fail-closed preflight в изолированном окружении;
- создание отдельной ветки и Draft PR.

Не разрешаю менять параметры production PostgreSQL, выполнять production rollout, перезапускать контейнеры или использовать неизвестные значения как подтверждённый бюджет.

## Цель

Защитить YFC от исчерпания PostgreSQL connections при deployment, миграциях, запуске worker и blue/green rollout.

В первую очередь нужно установить фактические границы доступной ёмкости, затем реализовать корректную проверку.

## 1. Исходные данные

Изучи #848, #815, актуальный master, SQLAlchemy engine setup, Docker Compose и deployment scripts.

Исходный статический baseline:

- pool_size = 10;
- max_overflow = 20;
- pool_timeout = 30 секунд;
- nominal ceiling = 30 соединений на engine.

Это НЕ production budget. Фактическая потребность зависит от количества процессов и реплик.

## 2. Read-only inventory

Определи из доступных разрешённых источников:

- PostgreSQL max_connections;
- reserved connections;
- наличие pooler;
- число backend процессов;
- число worker процессов;
- количество blue/green экземпляров;
- migration/setup connections;
- bot/другие потребители соединений;
- rollout overlap;
- rollback concurrency;
- существующие pool timeouts;
- уже занятые соединения.

Сначала исследуй репозиторий и доступные обезличенные operational evidence.

Если прямые production-запросы или SSH требуют отдельного разрешения — не выполняй их. Подготовь минимальный набор read-only команд и перечисли недостающие данные.

Не записывай secrets, connection strings, персональные данные или дампы.

## 3. Расчёт connection budget

Разработай явную модель:

1. Статическая максимальная потребность каждого процесса.
2. Совокупный максимум в steady state.
3. Максимум при blue/green overlap.
4. Дополнительная потребность migrations/setup.
5. Резерв PostgreSQL.
6. Прочие известные consumers.
7. Требуемый safety headroom.

Используй корректные worst-case значения и обоснованные допущения.

Не фиксируй произвольный safety margin как окончательный production-контракт.

При неизвестной критической величине результат должен быть UNKNOWN/BLOCKED, а не PASS.

## 4. Реализация preflight

Разработай scoped fail-closed проверку, способную:

- получать эффективную topology/configuration;
- вычислять безопасный бюджет;
- определять запас под rollout;
- различать PASS, BLOCKED и UNKNOWN;
- блокировать опасный deployment stage;
- не допускать случайного bypass;
- выдавать понятную диагностику;
- не раскрывать credentials.

Интегрируй проверку в поддерживаемую архитектуру deployment так, чтобы до отдельного разрешения production-поведение не менялось.

Если безопасная подготовительная интеграция невозможна без реального production topology — ограничь изменения независимым модулем, тестами и документированной точкой будущего подключения.

## 5. Тестирование

Покрой:

- нормальную конфигурацию с достаточным бюджетом;
- исчерпание connection budget;
- неизвестный max_connections;
- отсутствующие pool settings;
- несколько worker/backend replicas;
- blue/green overlap;
- миграции;
- rollback;
- PostgreSQL connection failure;
- неверные configuration values;
- недопустимый bypass;
- корректную последовательность preflight и deployment stages.

Используй mock/synthetic PostgreSQL и воспроизводимые данные.

Не выполняй опасные production stress tests.

## 6. Ограничения параллельной работы

#819 и #849 выполняются независимо.

Не изменяй backup/restore code, тестовые framework без необходимости и unrelated CI.

Не создавай PgBouncer либо другую инфраструктуру без доказанной необходимости.

## 7. Результаты

Подготовь:

- connection-budget model;
- таблицу подтверждённых и неизвестных параметров;
- безопасный preflight;
- тесты;
- documented rollout gate;
- rollback и failure behavior;
- точный список данных, необходимых для финальной production-проверки.

Создай отдельную ветку и Draft PR.

## Финальный отчёт

Выведи:

- что реально VERIFIED;
- что остаётся NO_DATA;
- worst-case calculation;
- результаты тестов;
- Draft PR и CI;
- можно ли активировать fail-closed gate;
- остаётся ли production rollout BLOCKED;
- какие конкретно owner approvals нужны.

Не выполняй merge/deploy и не закрывай #848, пока production connection budget не доказан и не принят.
