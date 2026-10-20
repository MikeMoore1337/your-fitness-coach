# Product V11 — V11-SC-01: базовые образы и SBOM

Дата подготовки: 2026-10-20
Issue: [#851](https://github.com/MikeMoore1337/your-fitness-coach/issues/851)
Родительская задача: [#814](https://github.com/MikeMoore1337/your-fitness-coach/issues/814)
Исходный `origin/master`: `847ba6dea37c300cbd6a2389584c71cf2e25bad4`

## Статус

- `IMPLEMENTED_LOCALLY`: Dockerfile-контракт, CI-генерация CycloneDX/SPDX и проверка
  provenance добавлены в отдельной ветке.
- `TECHNICALLY_READY`: выставляется только после успешного exact-head PR Checks и проверки
  реальных артефактов сборки. До этого локальная оценка — `NOT_VERIFIED`.
- `PRODUCTION_NOT_VERIFIED`: production deploy в рамках #851 не выполняется. Gate #848,
  owner approval, merge и release остаются отдельными условиями.

## Исходное состояние и недостатки

На исходном `master`:

1. `backend/Dockerfile` использовал `node:24-alpine` и `python:3.14-slim` только по тегу.
2. `bot/Dockerfile` использовал `python:3.14-slim` только по тегу.
3. Оба Dockerfile выполняли `apt-get update && apt-get upgrade --yes`; это позволяло
   незаметно менять содержимое сборки между одинаковыми исходными ревизиями.
4. CI уже выполнял блокирующее Trivy-сканирование финальных контейнеров, но не публиковал
   backend/bot SBOM в CycloneDX/SPDX и не связывал SBOM с digest финального образа и Git SHA.
5. PR [#1122](https://github.com/MikeMoore1337/your-fitness-coach/pull/1122) затрагивает
   `backend/Dockerfile` и deploy workflow. Поэтому контракт образов добавлен в общий
   `deployment_contract.py`, а SBOM-изменения изолированы в `ci.yml` и новом валидаторе.

## Проверенные базовые образы

Значения ниже получены 2026-10-20 из manifest index публичного Docker Registry v2 для
официальных образов Docker Hub; SHA в Dockerfile не являются предположениями.

| Dockerfile | Runtime | Immutable reference (manifest index) | `linux/amd64` child | `linux/arm64` child |
| --- | --- | --- | --- | --- |
| `backend/Dockerfile` | Node 24 Alpine | `node:24-alpine@sha256:44fce696f38ba8c987c4db89954051000bbd05ffd8d8659ba15ed4a8602e937f` | `sha256:429bdfbc204b4eabc6438e6d34e4e9d8dd2ca1df8289bcd78cdd3c5db387b7a5` | `sha256:5b12456322560dcf9342f7339662bccf8c5665cf0732a8ec8363687aa93c5277` |
| `backend/Dockerfile`, `bot/Dockerfile` | Python 3.14 slim | `python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170` | `sha256:cfe2e24a75302a15934d37c2d86412893c0aa934dc3a97cbb439d04c01890ca9` | `sha256:7f47c8ffd4e70e88f7326b68e7df95109597ef66023a1052b7d1ec18390d2604` |

Источники тегов и manifest metadata: [официальный `node` image](https://hub.docker.com/_/node/tags?name=24-alpine)
и [официальный `python` image](https://hub.docker.com/_/python/tags?name=3.14-slim).
Основные поколения среды не менялись: Node 24 и Python 3.14. Существующий digest
`ghcr.io/astral-sh/uv:0.11.32` сохранён без изменений.

`FROM` теперь требует ожидаемый digest, а контракт отклоняет tag-only references для
этих runtime и любое `apt-get upgrade`. Регрессии покрыты
`tests/test_deployment_contract.py`.

## Политика системных обновлений

- `bot` не устанавливает системные пакеты, поэтому бесполезный `apt-get update` удалён.
- `backend` выполняет только необходимый `apt-get update` и ограниченный
  `apt-get install --no-install-recommends`; blind `apt-get upgrade` удалён.
- Исправления ОС поступают через новый проверенный digest базового образа. Обновление
  выполняется отдельным PR с повторной сборкой, Trivy и проверкой provenance.
- Версии пакетов Debian, устанавливаемых `apt-get install`, остаются разрешаемыми
  репозиторием. Это явно отмечено в Dockerfile: для требования byte-for-byte replay нужен
  отдельный owner-approved переход на датированный Debian snapshot; в #851 такой новый
  источник или сервис не добавляется.
- Плановая проверка digest — не реже одного раза в 14 дней; критическое исправление —
  экстренный PR в течение 24 часов после подтверждения доступности исправленного образа.
  Renovate/Dependabot и новые внешние сервисы не используются.

## SBOM и provenance-контракт

Для `backend` и `bot` job `containers` теперь:

1. загружает финальный образ локально через BuildKit и проверяет его digest, image ID,
   `linux/amd64` и `org.opencontainers.image.revision == github.sha`;
2. сохраняет существующее блокирующее Trivy-сканирование `CRITICAL,HIGH` до публикации;
3. тем же pinned Trivy action `v0.73.0` создаёт:
   - `.artifacts/runtime/sbom/<image>/sbom.cyclonedx.json`;
   - `.artifacts/runtime/sbom/<image>/sbom.spdx.json`;
4. `scripts/validate_image_sbom.py` проверяет непустой JSON, обязательные поля формата,
   непустые component/package lists, lowercase SHA-256 image digest, image ID,
   архитектуру, равенство OCI revision исходному полному Git SHA, SHA-256 обоих SBOM и
   secret-shaped поля/значения;
5. публикует SBOM и `provenance.json` как artifact с retention 14 дней. Sidecar содержит
   `image.ref`, `image.digest`, `image.local_image_id`, `image.architecture`,
   `image.oci_revision`, `image.source_revision` и хэши двух SBOM;
6. после публикации на `master` проверяет, что digest GHCR равен digest, полученному на
   этапе сборки. Несовпадение останавливает job.

Пути артефактов не содержат переменных окружения, токенов, cookies, персональных или
медицинских данных. Репозиторное Trivy-сканирование `vuln,misconfig,secret` остаётся
отдельным blocking gate.

## Плановое обновление

1. Получить новый manifest index и child manifests из официального Docker Registry для
   `node:24-alpine` и/или `python:3.14-slim`; записать index и обе поддерживаемые архитектуры
   в этот документ.
2. Изменить только digest в соответствующем Dockerfile; не возвращать mutable tag и не
   добавлять `apt-get upgrade`.
3. Выполнить локальные contract/SBOM tests и открыть PR. Exact-head CI должен выполнить
   фактическую сборку backend и bot, runtime checks, blocking Trivy, CycloneDX/SPDX,
   provenance и upload artifacts.
4. Проверить artifact `provenance.json`: digest, revision и SHA файлов должны соответствовать
   тому же CI run. Для production пригоден только образ с проверенным exact Git SHA и
   опубликованным digest.
5. Merge/deploy выполняются только обычным GitHub flow после всех применимых gates; #848
   не заменяется этой проверкой.

## Экстренное обновление и откат

Экстренное обновление следует тем же шагам, но с приоритетным PR и полным exact-head CI.
Если новый образ не проходит сборку, Trivy, runtime contract или provenance, PR не сливается.

До production сохраняется предыдущий commit/digest как проверенная точка отката. Откат —
это обычный revert PR либо owner-authorized `workflow_dispatch` существующего `deploy.yml`
с `operation=rollback`, активной ревизией и причиной. Нельзя переписывать mutable tags,
подменять digest вручную или использовать непроверенный CI artifact. Existing deploy
workflow сам проверяет provenance и digest образов перед передачей на host; production
операция в этой задаче не запускалась.

## Выполненные и непроверенные проверки

Локально в изолированной ветке выполнены:

- `15 passed` для deployment/image/SBOM contract tests;
- Ruff format/check для изменённых Python-файлов;
- `scripts/ci_contract.py run-group image-contract`;
- `scripts/ci_contract.py run-group deployment-contract`;
- YAML parse `.github/workflows/ci.yml`.

`NOT_VERIFIED` до exact-head GitHub run: реальная Docker-сборка backend/bot, фактическое
содержимое CycloneDX/SPDX artifacts, published GHCR digest и успешные обязательные GitHub
Actions. Локальный Docker Engine в среде разработки недоступен. Production smoke,
production compatibility и release approval намеренно не выполнялись.
