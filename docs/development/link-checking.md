# Проверка ссылок

В репозитории есть два разных контура:

- `scripts/check_links.py` — дешёвая детерминированная проверка локальных Markdown/HTML/source
  ссылок, файлов, якорей и публичных route references;
- `scripts/check_seo_surface.py` — отдельная проверка live SEO-поверхности: canonical pages,
  `robots.txt`, `sitemap.xml`, indexation headers и публичных sitemap URLs.

## Локальная проверка

Из корня репозитория:

```powershell
python scripts/check_links.py
```

Режим по умолчанию не делает сетевых запросов. Он проверяет относительные пути, локальные
web-assets, query/fragment, GitHub-style slug для Markdown-заголовков, явные HTML `id`/`name`,
опубликованные пути из `frontend/src/content/publicContent.json`, Markdown в `codex-backlog/` и
статические `href`/`to` в публичном/landing source. Ссылки от корня на assets из `frontend/public`
и PWA manifest
проверяются как локальные файлы.
Приватные маршруты (`/app`, `/coach`, `/admin`, `/login` и другие) не запрашиваются без авторизации.

В отчёте есть source path, строка, обезличенный адрес, класс результата и команда повторного
запуска. Значения query-параметров, credentials, токены и персональные URL не выводятся.

## Внешние ссылки

Внешний режим запускается отдельно и остаётся отчётным:

```powershell
python scripts/check_links.py --external --timeout 5 --max-external-urls 50 --max-per-host 5
```

В обязательном CI используется только дешёвый детерминированный локальный hook из
`.pre-commit-config.yaml`:

```powershell
python scripts/check_links.py
```

Проверяются только public `http(s)` URLs, последовательно (concurrency=1). Redirect считается
успешным; `404/410` — подтверждённой
ошибкой; `403/429`, timeout, сетевой сбой и `5xx` получают `deferred` и не превращаются в
случайный обязательный CI-fail. `file:`, `javascript:`, `data:`, `ftp:`, `mailto:`, loopback/
private hosts, FatSecret personal exports, URL credentials, sensitive query parameters и API/auth
resources исключаются до network boundary.

Для ручной unauthenticated проверки ссылок на публичном host можно дополнительно передать:

```powershell
python scripts/check_links.py --public-base-url https://your-fitness-coach.ru
```

Это не подставляет auth и не заменяет `check_seo_surface.py`. Production URL не используется в
обязательном CI; для CI и локальной проверки применяется local-only режим.

## Почему не lychee

`lychee` — зрелый Rust CLI для Markdown/HTML/website links с Windows/Linux binaries и
Apache-2.0/MIT licensing. Он полезен для широкого внешнего обхода, но не знает YFC-specific
разделение public/private routes, исключения FatSecret/API и безопасную redaction диагностики.
Добавление отдельного бинарного инструмента или GitHub Action ради этого контура увеличило бы
supply-chain и нестабильность внешней сети без необходимой пользы, поэтому зависимость не
добавлялась.
