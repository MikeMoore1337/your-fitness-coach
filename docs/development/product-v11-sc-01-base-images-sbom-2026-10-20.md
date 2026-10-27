# Product V11 — V11-SC-01: базовые образы и SBOM

Дата подготовки: 2026-10-20
Issue: [#851](https://github.com/MikeMoore1337/your-fitness-coach/issues/851)
Родительская задача: [#814](https://github.com/MikeMoore1337/your-fitness-coach/issues/814)
Исходный `origin/master`: `847ba6dea37c300cbd6a2389584c71cf2e25bad4`

## Статус

- `IMPLEMENTED_AND_EXACT_HEAD_VERIFIED`: Dockerfile-контракт, CI-генерация CycloneDX/SPDX,
  provenance и реальные backend/bot SBOM проверены на exact-head CI run `39477264926`.
- `READY_FOR_RELEASE_APPROVAL`: технические критерии #851 выполнены на текущем exact head;
  это не меняет Draft-состояние PR и не заменяет owner/release approval.
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

## Совместимость с PR #1122

- Read-only `git merge-tree` для текущих голов PR показывает, что изменения в
  `backend/Dockerfile` объединяются автоматически: сохраняются digest и запрет mutable
  `apt-get upgrade` из #1137 и `COPY` trusted collector из #1122.
- Изменения #1122 в `.github/workflows/deploy.yml` добавляют trusted runtime tooling и не
  пересекаются с SBOM-steps #1137. PostgreSQL safety gate #848 не ослабляется.
- Есть обычный текстовый конфликт в `tests/test_deployment_contract.py`: обе ветки добавляют
  свои группы тестов. При интеграции нужно сохранить обе группы; переносить весь Draft #1122
  в #1137 не требуется.
- Совместимость подтверждена как анализ веток, а не как объединённый или production-запуск:
  PR #1122 остаётся Draft, Issue #848 — открытым owner-gated условием.

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
   `linux/amd64` и `org.opencontainers.image.revision == github.sha`. В PR-контексте
   `github.sha` — проверяемый merge commit; PR head фиксируется отдельно в evidence ниже;
2. сохраняет существующее блокирующее Trivy-сканирование `CRITICAL,HIGH` до публикации;
3. тем же pinned Trivy action `v0.73.0` создаёт:
   - `.artifacts/runtime/sbom/<image>/sbom.cyclonedx.json`;
   - `.artifacts/runtime/sbom/<image>/sbom.spdx.json`;
4. `scripts/validate_image_sbom.py` проверяет непустой JSON, обязательные поля формата,
   непустые component/package lists, lowercase SHA-256 image digest, image ID,
   архитектуру, равенство OCI revision исходному полному Git SHA, SHA-256 обоих SBOM и
   secret-shaped поля/значения;
5. на `master` публикует только просканированный образ, получает registry digest и загружает
   его по immutable reference. Image/config ID должен совпасть с просканированным локальным
   образом; OCI revision и архитектура повторно проверяются. Ошибка или несовпадение блокируют job;
6. сохраняет исходный BuildKit sidecar как `build-provenance.json` и повторно валидирует
   `provenance.json` с фактическим published digest. Docker load/push может изменить представление
   manifest, поэтому равенство этих двух manifest digest не предполагается;
7. после успешных проверок публикует SBOM и sidecars как artifact с retention 14 дней.
   `provenance.json` содержит immutable `image.ref`, registry `image.digest`, проверенный
   `image.local_image_id`, архитектуру, OCI/source revision и хэши двух SBOM. В PR без push
   sidecar описывает только BuildKit export; production evidence из него не выводится.

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

## Exact-head CI и реальные артефакты

Проверка выполнена 2026-10-20 на [CI run `39477264926`](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39477264926):

- PR head: `dc261707c60149fcb8cdca4c434e7911cc05955c`;
- base `master`: `09ea49ac7a2ea441815c100e8d6ac078cde122aa`;
- проверяемый PR merge commit и `github.sha` сборки: `7209bf5b5e9874f7f6b249a81b31850a874a8a57`;
- aggregate `checks`: `SUCCESS`; Python/frontend, Docker backend/bot, Trivy, deployment/workflow
  contracts, CodeQL, security audit и smoke checks: `SUCCESS`. Неприменимые weekly/extended
  cross-browser и private Allure jobs были `SKIPPED` по scope-router, а не скрыты.

| Image | BuildKit digest | Local image ID | Components/packages | CycloneDX SHA-256 | SPDX SHA-256 |
| --- | --- | --- | --- | --- | --- |
| backend | `sha256:151609441c425eeb5036a0cc56eaa40946f57fb977687720e455ca1b4afba6b8` | `sha256:282ddcd9299f802124482a68253198838624ebb3369f91adc2836a5e3d0279d0` | 1299 / 1300 | `80aedda0b3c4b981ecd8c27cd2962a52abd74f80e2e4b7345c58330b2c581d62` | `fde8fd75c0876a344f3bc48f5478210cf26787541df5a576e637294c43571f99` |
| bot | `sha256:c4c32f3bcf21b81c2e6e9cf2c6e8a3f04d9520e1993ce68a59ce74bab28e6b3f` | `sha256:4c48d4afa70d97562e31e4b9ba16dfe78fe24b374bf6121bcc79de29c9432fc0` | 1135 / 1136 | `88189481d02e8d8e58d80f631ef39cb2c2686668bc162262e85ee79306147406` | `07e31e692c4613999d2b68db9a4ae7dac5576c58ec60025d2f45221f63f0dfd9` |

В обеих SBOM `source_revision` и `oci_revision` равны merge commit `7209bf5…`, архитектура
`linux/amd64`, а `provenance.json` повторно провалидирован локально на скачанных файлах.
Артефакты: [backend SBOM](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39477264926/artifacts/12291185053),
[bot SBOM](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39477264926/artifacts/12288724500).
Проверка secret-shaped полей/значений не выявила credential-shaped entries; совпадения
`secret-service` являются именами пакетов. Blocking Trivy `CRITICAL,HIGH` завершился успешно.

PR CI не публикует GHCR-образы, поэтому published registry digest для production — `NOT_RUN`,
а приведённые digest — реальные BuildKit digest локально загруженных образов CI.

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

- `115 passed` для deployment/image/SBOM contract tests;
- Ruff format/check для изменённых Python-файлов;
- `scripts/ci_contract.py run-group image-contract`;
- `scripts/ci_contract.py run-group deployment-contract`;
- повторная валидация реальных backend/bot CycloneDX/SPDX файлов и их SHA-256 provenance.

Расширенный локальный набор дал `147 passed` и один environment-specific failure в
`tests/test_production_provenance.py::test_reconcile_changes_only_existing_metadata` на
Windows/sandbox; этот файл не изменён PR, а соответствующий exact-head Python job прошёл.
Локальный Docker Engine недоступен, поэтому локальная сборка не выполнялась; реальная сборка
и Trivy подтверждены exact-head CI. Production smoke, published GHCR verification, live
PostgreSQL capacity, merge и release approval намеренно не выполнялись.
