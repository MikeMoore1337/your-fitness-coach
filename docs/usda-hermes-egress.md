# USDA FoodData Central через Hermes VPS

Назначение: ограниченный исходящий маршрут для запросов USDA из backend YFC, если
основной VPS получает HTTP 403 от upstream по сетевой причине. Это не публичный
прокси и не изменение маршрутов остальных приложений.

## Схема

```text
YFC backend -> socks5h://host.docker.internal:1082
            -> SSH fit-usda-tunnel.service (основной YFC VPS)
            -> SSH user usda-tunnel (Hermes VPS)
            -> api.nal.usda.gov:443 (HTTPS)
```

- SSH-сервис `fit-usda-tunnel.service` управляется systemd, автоматически восстанавливается.
- На стороне Hermes SSH-аккаунт `usda-tunnel` имеет `PermitOpen api.nal.usda.gov:443`,
  только локальное TCP-перенаправление, без пароля, интерактивной оболочки и доступа к другим адресам.
- Туннель слушает исключительно Docker host gateway `172.17.0.1:1082`.
  Firewall YFC разрешает доступ только из внутренних сетей приложения.
  Постоянное правило хранится в `/etc/nftables.conf`.
- Закрытый ключ SSH находится только на VPS YFC, в `/root/.ssh/fit_usda_tunnel_ed25519`.
  Данные ключа, USDA API-ключ и приватные запросы не допускаются в Git или журналирование.
- URL прокси задаётся на backend через `USDA_FDC_PROXY_URL`.
  Другие провайдеры и OAuth его не используют.
- `USDA_FDC_API_KEY` и `FOOD_USDA_ENABLED` задаются только в корневом
  `/srv/yfc/fit-mini-app/.env`. Release workflow переносит этот файл в новую ревизию.
- USDA работает как внешний fallback, не как обязательная зависимость дневника.
  При отказе туннеля сохраняются локальные продукты, Open Food Facts и ручной ввод.

## Проверка (не печатать секреты)

На основном VPS:

```bash
systemctl is-active fit-usda-tunnel.service
ss -lnt | grep '172.17.0.1:1082'
curl --proxy socks5h://172.17.0.1:1082 -sS --max-time 12 \
  -o /dev/null -w '%{http_code}\\n' \
  'https://api.nal.usda.gov/fdc/v1/foods/list?api_key=DEMO_KEY'
docker exec fit-mini-app-backend-1 python -c \
  'import socket; socket.create_connection(("host.docker.internal",1082),3).close(); print("OK")'
```

Ожидание: systemd `active`, код 200 для DEMO_KEY, сокет из контейнера доступен.
Отдельно проверить авторизованный поиск русских продуктов в YFC и результат
`provider_statuses` для `usda_fdc`. Проверка DEMO_KEY не подтверждает пользовательский ключ.

## Диагностика и откат

- Ошибка `connection refused` или timeout: состояние systemd, порт 1082,
  firewall, SSH-хост Hermes, наличие имени `host.docker.internal` в контейнере.
- HTTP 429: ограничение API, не увеличивать частоту повтора.
- HTTP 403 от USDA: проверить сетевой маршрут и ключ, не записывая его в логи.
- Откат: отключить `FOOD_USDA_ENABLED=false` в корневом `.env`, выполнить
  контролируемое пересоздание backend; другие источники и локальные данные сохраняются.
- Не открывать порт 1082 на публичном интерфейсе, не использовать туннель OAuth,
  не расширять SSH `PermitOpen` на произвольные адреса.

Подключение дополнительных источников и изменение лицензий данных - отдельные задачи.
