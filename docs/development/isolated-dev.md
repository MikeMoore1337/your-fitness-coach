# Изолированный DEV YFC (Issue #1237)

Это отдельный локальный контур разработки, не production и не публичный staging.

## Локальный запуск

Требуется Docker Compose v2. Не запускайте контейнеры на действующем VPS YFC, пока задача #1237 не получила проверенный capacity GO.

```bash
python3 scripts/bootstrap_dev_env.py
docker compose --env-file .env.dev -f compose.dev.yml config --quiet
docker compose --env-file .env.dev -f compose.dev.yml up -d --build backend
docker compose --env-file .env.dev -f compose.dev.yml ps
```

В Windows замените Python-команду на `py -3.14 scripts/bootstrap_dev_env.py`.
Проверка `config --quiet` не выводит секреты.

Откройте http://127.0.0.1:18080/login и выберите роль: клиент (2001), тренер (1002) или администратор (1001). Текущий `dev-login` создаёт тренера при первом входе. Реалистичные связанные данные клиента и тренера остаются отдельным этапом #1237.

Для остановки без удаления тестовой БД:

```bash
docker compose --env-file .env.dev -f compose.dev.yml down
```

## Границы изоляции

`compose.dev.yml` является самостоятельным Compose-файлом. Никогда не объединяйте его с production `docker-compose.yml`. DEV имеет отдельную PostgreSQL, том, сеть, образ и случайные секреты. Нет бота, worker и реальных внешних публикаций. Порт привязан только к localhost, PWA отключена.

Пока `/api/v1/auth/dev-login` принимает клиентские поля ролей. **Не публиковать DEV в интернете** до добавления серверного списка фиксированных учётных записей и отдельного входного контроля (VPN / Cloudflare Access).

## Решение по VPS

26.10.2026 чтение Linux `/proc/meminfo` из sandbox Hermes BRC на YFC VPS показало приблизительно 1.92 ГиБ RAM всего, 0.65 ГиБ доступно и 2 vCPU. Это предварительные данные **из контейнера**, а не проверенный снимок всех контейнеров и PostgreSQL хоста. Размещение DEV на том же VPS остаётся `HOLD`. Не менять production-окружение и не ослаблять его пороги ради запуска DEV.

Развёртывание PR до merge и наполнение фикстурами выполняются следующими этапами #1237. Публикация этого файла сама по себе не является запуском DEV.
