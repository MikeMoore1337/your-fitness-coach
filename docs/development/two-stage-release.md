# YFC: интеграция через dev до выпуска в production

Решение владельца от 26.10.2026, Platform #1266. `master` остаётся production-веткой, сохраняет существующий post-CI автоматический деплой. Никаких новых VPS, платных API или публичного DEV.

## Маршрут изменений

```text
feature/* --PR + required checks--> protected dev (GitHub)
                                      |
                                      | exact SHA -> local Windows Docker YFC DEV
                                      | real iPhone Safari / private Tailscale
                                      | RBAC, UI and business scenarios / owner acceptance
                                      v
                              PR dev -> master
                                      |
                                      | required checks + owner-approved merge
                                      v
                           protected master + CI
                                      |
                                      v
                          existing production auto-deploy
```

**Git branch `dev` и Windows DEV — разные вещи.** Слияние PR в GitHub само по себе не обновляет локальный Windows Docker: сейчас удалённый агент Windows недоступен. Не устанавливайте публичный self-hosted runner и не включайте Tailscale Funnel ради этой схемы.

## Первая синхронизация (завершена 27.10.2026)

Старая защищённая ветка `dev` отставала от `master` примерно на 2094 коммита. Первоначальный bootstrap проведён через [PR #1267](https://github.com/MikeMoore1337/your-fitness-coach/pull/1267): merge SHA `50fe1295c0f1f34f649306a90aec63c454a342ee`, [post-push CI #40448240592](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/40448240592) завершён успешно. Production при этом не обновлялся.

На этапе bootstrap временно использовалась строго ограниченная база сравнения CSS для `lime-edges`. После первоначального слияния исключение стало недостижимым и удалено из CI и `ci_contract.py`. Для всех последующих PR применяется обычная проверка без подмены базы. Проверка источника PR в `master`, обязательный `checks` и master-only deployment сохранены.

Диагностический `changed_paths` для больших diff ограничен по размеру, но классификация CI по-прежнему использует полный список изменённых файлов.

## Обычная разработка

1. Создать ветку `feature/*` **от актуальной `origin/dev`**. Не создавать её от `master`, чтобы не потерять ещё не выпущенные изменения.
2. Открыть PR из `feature/*` **в `dev`**. Дождаться зелёного `checks`, выполнить ревью, затем объединить. При смене базы PR событие `edited` запускает CI заново с новой базой. Слияние feature в `dev` **не выпускает ничего в production**.
3. GitHub CI запускается также на `push dev`. Зафиксировать точный `dev` SHA после successful CI.
4. Запустить именно эту ревизию на изолированном Windows DEV. Сохранить ручные данные и PostgreSQL volume. Пройти `/health/ready`, `py -3.14 scripts/verify_dev_roles.py`, проверки UX на физическом iPhone (включая сотовую сеть) и конкретные сценарии изменённых фич.
5. После приёмки остановить слияния новых PR в `dev` на время промоушена; открыть **один PR `dev → master`**, убедиться, что его head SHA равен принятому SHA, `checks` зелёный. В описании указать доказательства локальной приёмки.
6. Только после решения владельца объединить PR в `master`; существующая `.github/workflows/deploy.yml` автоматически деплоит успешный CI на `master`. Проверить production verify и зафиксировать выпуск.
7. Продолжить обычные PR в `dev`. Не возвращать `dev` назад и не делать force-push.

## Windows: не стирать локальную базу

Путь `D:\Pet-projects\yfc-dev` уже используется отдельной dev-веткой из PR #1238. Переключаться на `dev` **только после того, как bootstrap завершён и PR #1238 объединён в `dev`**. Не переписывать локальные незакоммиченные изменения и не делать `reset`.

```powershell
Set-Location D:\Pet-projects\yfc-dev
git status --short                    # должен быть пустым
git fetch origin dev
git switch -c dev --track origin/dev  # только если локальной ветки dev ещё нет
.\scripts\dev.ps1 -Action start
py -3.14 scripts/verify_dev_roles.py
```

При последующих обновлениях:

```powershell
Set-Location D:\Pet-projects\yfc-dev
git status --short
git pull --ff-only origin dev
.\scripts\dev.ps1 -Action start
py -3.14 scripts/verify_dev_roles.py
git rev-parse HEAD
```

Перед промоушеном проверить, что `git rev-parse HEAD` совпадает с проверенным `origin/dev` и head PR в `master`. **Не выполнять `dev.ps1 reset`**, `docker compose down -v` или `git reset --hard`.

## Правила безопасности

- Production workflow остаётся привязанным к `master`, не к `dev`. `workflow_dispatch` для ручных работ требует существующей отдельной проверки provenance/owner authorisation.
- `master`: PR только из защищённой ветки `dev` того же GitHub-репозитория. Этот инвариант проверяется в обязательном CI job `checks`.
- Не допускать auto-merge `dev → master`: требуется ручное решение владельца после физической проверки.
- Существующие правила branch protection, required checks и обзоры оставлять включёнными. Проверить ручные bypass права в GitHub Rulesets: любые прямые изменения `master` вне PR должны быть исключены.
- Одновременно изменяемые миграции PostgreSQL проверять на отдельной DEV базе, не подмешивать данные production.
- При сбое DEV исправить в feature-ветке и повторить PR; production не затрагивать. Аварийный hotfix — сначала через `dev` или отдельный явно одобренный owner emergency gate.
