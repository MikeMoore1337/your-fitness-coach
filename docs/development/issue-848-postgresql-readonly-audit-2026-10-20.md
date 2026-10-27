# #848 — отдельная read-only проверка PostgreSQL (20.10.2026)

Связано с [Issue #848](https://github.com/MikeMoore1337/your-fitness-coach/issues/848) и Phase B [PR #1122](https://github.com/MikeMoore1337/your-fitness-coach/pull/1122).

## Назначение

Уже существующий запускаемый владельцем `.github/workflows/production-capacity-audit.yml` получает дополнительные **числовые диагностические поля**. Он не запускает rollout, не меняет состояние PostgreSQL, не заменяет доверенный сборщик из #1122 и не открывает доступ к секретам.

Существующие условия: только владелец репозитория, `refs/heads/master`, защищённое окружение `production`, SSH с known_hosts, ограниченное время удалённых команд, удаление временного ключа в любом случае. Прежние показатели и контракты продолжают действовать.

## Поля

| Вывод | Источник/смысл |
|---|---|
| `POSTGRES_SUPERUSER_RESERVED_CONNECTIONS` | Текущий `superuser_reserved_connections` |
| `POSTGRES_RESERVED_CONNECTIONS` | `reserved_connections` для PostgreSQL 16+, а до 16 — документированный 0 |
| `POSTGRES_USABLE_NON_RESERVED_CONNECTIONS` | `max_connections - superuser_reserved - reserved` |
| `POSTGRES_UNRESERVED_HEADROOM` | usable minus текущие сессии; **не прогноз на стадии rollout** |
| `POSTGRES_DECLARED_YFC_SESSIONS` | Число `pg_stat_activity` с именами приложений из фиксированного перечня |
| `POSTGRES_NON_YFC_SESSIONS` | Total minus declared YFC: включает неатрибутированные |
| `POSTGRES_UNATTRIBUTED_SESSIONS` | Сессии с пустым `application_name`; **подмножество non-YFC** |
| `POSTGRES_BUDGET_VERDICT` | Всегда `NOT_VERIFIED` |

Данные берутся только read-only SQL без вывода `datname`, `usename`, `client_addr`, текста запросов, ключей или строк подключения. В `stdout` выводятся только агрегаты и фиксированные метки. Декларируемый `application_name` не является криптографическим доказательством принадлежности, а старые экземпляры YFC могут использовать иные имена. Поэтому эти поля **нельзя** трактовать как надёжную атрибуцию.

Ошибочный, недоступный или несовместимый вывод PostgreSQL преобразуется в `UNAVAILABLE`. Обработка троек счётчиков отвергает отрицательные, несогласованные, нечисловые и неожиданные значения. Замеры `current_connections` и агрегат `session_counts` выполняются в двух разных SELECT; они могут относиться к немного разным моментам. Это ещё одна причина не использовать аудит как блокирующую проверку.

## Неподтверждённые сведения

- Фактические выводы на сервере, PostgreSQL 16 configuration, работающий pooler и внешние клиенты: `NO_DATA`.
- Количество процессов/реплик на этапе перекрытия blue/green и остаточный запас с margin: `NOT_PROVEN`.
- Политика допустимого `safety_headroom_connections`: не задана владельцем.
- Trusted collector Phase B и интеграция в deployment gate: отдельный нерелизный PR #1122, до этого обновления не проверялись на production.

## Приёмка

Регрессионные тесты в `tests/test_release_safeguards.py` проверяют контракт числовых полей, сохранение read-only SQL и отсутствие выдуманного `PASS`; отдельно параметризованы корректные и некорректные входные счётчики. Дополнительно применяются штатные GitHub workflow validation / CI.

**Классификация:** изменение лишь `.github/workflows/*`, `tests/*` и `docs/*` — без изменённого application image. После успешной проверки допустимо слить отдельно от #1122 по обычному GitHub Flow **без production deploy**, сохранив текущий ручной запуск по инициативе владельца. Не запускать ручной аудит автоматически и не объявлять #848 закрытой из-за этого изменения.
