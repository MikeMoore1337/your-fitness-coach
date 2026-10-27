# Методика оценки Codex Desktop по принятому результату

Статус: методика для Issue [#1007](https://github.com/MikeMoore1337/your-fitness-coach/issues/1007), а не проведённое сравнение моделей.

Снимок источника: `origin/master` = `2ed3b5d236ad08ade1b74a11c25d33c231d9057d` на 2026-10-16. Документ не меняет приложение, CI, release-путь или optional agent harness.

## Решение

Сохраняем текущую конфигурацию Codex Desktop. У проекта пока нет достоверного task-level измерения времени работы модели, токенов или стоимости, поэтому нельзя честно назвать модель-победитель или заявить экономию. `scripts/agent_harness.py` и `scripts/agent_flow.py` остаются необязательными помощниками для воспроизводимых проверок и маршрутизации; они не становятся системой измерения, мониторингом, контроллером или вторым источником истины.

Будущий эксперимент имеет смысл только при одновременном наличии:

- одинакового зафиксированного baseline SHA, требования и набора проверок;
- одинаково подтверждённого качества результата;
- task-level времени/лимитов/стоимости, если требуется вывод о цене;
- минимум трёх сопоставимых задач на модель. Это практический порог для решения, а не статистическое доказательство.

До этого результатом является `INSUFFICIENT_SAMPLE` или `NO_DATA`, а не рейтинг.

## Что именно измеряется

Главный объект сравнения — цена качественно принятой задачи: сколько проверяемой работы потребовалось до технически готового результата и сколько коррекций понадобилось после первой реализации. Скорость сама по себе не компенсирует дефект, пропущенную авторизацию, английский новый UI-текст, регрессию или незакрытый DoD.

| Метрика | Как считать | Достоверность сейчас |
| --- | --- | --- |
| Время до технического результата | `t_technical_ready - t_task_start`, где обе точки берутся из фактического Codex Desktop task event; отдельно фиксируются baseline и exact PR head | `NO_DATA`, если Desktop не отдаёт task-level точки; Issue/PR timestamps — только lifecycle-прокси |
| Время до успешного обязательного CI | `checks_completed - checks_started` по конкретному Actions run ID и exact head SHA | `PARTIAL`: API/интерфейс GitHub хранит эти поля, но использованный wrapper вернул только статус/результат run, поэтому длительность этого исследования не измерена |
| Коррекции после первой реализации | число и содержание изменений после зафиксированного `first_implementation`; отдельно отмечать исправление требования, теста, дефекта и косметику | `AVAILABLE` при ручной event-классификации; число коммитов само по себе не метрика коррекций |
| Acceptance criteria | таблица `criterion -> evidence -> status`; критерий считается принятым только при прямом доказательстве | `AVAILABLE`, но требует ревью; текст PR не заменяет независимое доказательство |
| Дефекты и регрессии | только воспроизведённый дефект, failure в проверке или подтверждённое production/device наблюдение с ID/ссылкой | `AVAILABLE` для фактов; зелёный CI не доказывает отсутствие дефектов |
| Итерации PR и rerun CI | PR timeline, commits, review threads и Actions run IDs; cancelled/rerun не смешивать с исправлением продукта | `PARTIAL`: доступно по GitHub, но не все timeline-поля выдаёт текущий connector |
| Существенные ошибки | классифицировать найденные в review/проверках ошибки по severity и причине; не считать все комментарии ошибками | `AVAILABLE` при наличии review/failure evidence |
| Пропуски security, localization и DoD | отдельный чек-лист обязательных границ; один пропуск делает trial некачественным независимо от времени | `AVAILABLE` через CI и ручную проверку |
| Owner intervention | только явно зафиксированные запросы, решения и повторные указания владельца | `PARTIAL`: отсутствие комментария не означает отсутствие работы владельца |
| Токены, лимиты и стоимость задачи | task-level telemetry Codex Desktop или официальный экспорт с attribution к конкретной задаче | `NO_DATA`; account aggregate, число сообщений и число коммитов не являются заменой |

### Три разных состояния результата

1. **Техническая готовность** — exact PR head известен, обязательный aggregate `checks` зелёный, acceptance matrix закрыта доказательствами, известных дефектов нет или они явно отмечены.
2. **Owner acceptance** — владелец явно принял результат и все требуемые визуальные, hardware, privacy, legal или destructive gates.
3. **Production release** — PR смержен в защищённый `master`, для этого exact master SHA прошли Actions deploy/smoke и есть release evidence.

Зелёный CI, открытый PR или merge не доказывают следующие состояния автоматически. В частности, физические iPhone/Safari, native Telegram и VoiceOver остаются `NOT_VERIFIED`, пока не проведена соответствующая проверка.

## Правила честного измерения

- `NO_DATA` означает, что источник данных отсутствует или не позволяет приписать значение конкретной задаче. `NOT_RUN` — проверка не выполнялась. `NOT_VERIFIED` — проверка нужна, но прямого доказательства нет.
- Время от создания Issue до PR, число сообщений, коммитов или изменённых строк нельзя выдавать за активное время Codex.
- Account-level quota snapshot можно сохранить только как контекст доступности лимита; нельзя приписывать его #1007, вычислять стоимость одной задачи или заявлять экономию.
- PR/Issue являются частью GitHub-native traceability. Локальный файл, fingerprint, lease, очередь, база, архив или task mirror не добавляются.
- Для методики достаточно SHA, Issue/PR/Actions IDs, URL, timestamp, количества, статусов и редактированных категорий ошибок. Не сохраняются prompt/transcript, private chats, secrets, PII или payload пользователя.
- Результат эксперимента публикуется только после проверки exact head и required Checks. Незавершённые параллельные задачи используются лишь как явно помеченные примеры.

## Повторяемый протокол

1. Зафиксировать baseline SHA, ветку, дату, тип задачи, допустимые файлы и обязательные проверки.
2. До запуска записать одинаковый challenge packet: требование, текущий симптом/входные данные, ожидаемый результат, ограничения и критерии отказа.
3. Запустить одну модель/конфигурацию на одной задаче. Записать task-level `t_start`, если источник действительно его отдаёт.
4. Отдельно отметить первое применённое изменение, первый targeted test result и первый PR head. Не считать Issue->PR рабочим временем.
5. Выполнить минимальные targeted checks, затем обязательный CI. Записать run ID, exact head, статусы и доступные timestamps.
6. Проверить acceptance matrix, security, Russian UI copy, доступность, регрессии и ограничения hardware/device. Для недоступных проверок сохранить `NOT_VERIFIED`.
7. Отметить все коррекции после первой реализации и причину каждой. Rerun/cancelled run записывать отдельно.
8. Получить owner acceptance, если она нужна, и только затем отдельно рассматривать merge/release. Непрошенный merge, deploy или закрытие Issue не является частью эксперимента.

## Малые сценарии

Сценарий ниже — заранее фиксируемый challenge packet. Его нельзя считать выполненным без exact PR/commit и CI evidence. #1014 и #1006 не входят в выборку: это параллельные незавершённые задачи.

| Сценарий | Зафиксированный baseline и вход | Ожидаемый результат | Проверки и измерения | Ограничение |
| --- | --- | --- | --- | --- |
| Анализ первопричины дефекта | исторический снимок #914, base PR [#1011](https://github.com/MikeMoore1337/your-fitness-coach/pull/1011) = `6233dc62ab6c0d2b5758c79eebccd07a7daeda18`; вход — описание race/lifecycle таймера и доступный код baseline | объяснить механизм отказа, дать минимальное воспроизведение или targeted test и безопасный план изменения | наличие root-cause evidence, regression test/diff, targeted CI; отдельно фиксировать отсутствие physical-device proof | исторический пример, не новый запуск и не доказательство времени модели |
| Python API test | `2ed3b5d236ad08ade1b74a11c25d33c231d9057d`; `backend/tests/test_h10_identity_authorization.py`, endpoint `/api/v1/me`; вход — запрос без требуемого `jti`/auth boundary | добавить один изолированный тест, который подтверждает отказ невалидной auth-сессии и не меняет runtime-контракт | targeted pytest, quality и required `checks`; diff не должен менять endpoint/схему | тестовая задача, не разрешение ослаблять trusted-server authorization |
| React/Vitest test | `2ed3b5d236ad08ade1b74a11c25d33c231d9057d`; `frontend/tests/unit/app/AuthGate.test.tsx`; вход — выбранный заранее сценарий безопасного redirect с сохранением deep link | добавить один focused regression assertion; существующая русская copy, composition и navigation semantics сохраняются | Vitest, typecheck, lint, build, required `checks`; отдельно отметить browser/device status | unit-test evidence не заменяет browser, Telegram или VoiceOver evidence |
| PR review | frozen exact head, например open Draft PR [#1015](https://github.com/MikeMoore1337/your-fitness-coach/pull/1015) = `c7a666950f89eaa4588852e4ae93c49bff470efe` | структурированный review: severity, file/line, evidence, missed acceptance/security/DoD; без записи в репозиторий | findings must be reproducible from the frozen diff and checks; отдельно учитывать false positives | #1015 — параллельный незавершённый пример, не финальный результат и не рейтинг модели |
| Безопасный локальный рефакторинг | `2ed3b5d236ad08ade1b74a11c25d33c231d9057d`; заранее выбранный pure helper и все его callers | сохранить поведение, API, данные, authorization и тестовые контракты при минимальном diff | targeted tests, quality, exact diff and required `checks`; записать post-first corrections | не расширять до dependency update, массового format или архитектурного изменения |

## Верифицируемые примеры GitHub-трассы

Эти строки показывают, какие факты уже доступны через GitHub. Они не являются A/B-измерением Codex и не доказывают, какая модель работала.

| Трасса | Факты | Что можно заключить |
| --- | --- | --- |
| [Issue #737](https://github.com/MikeMoore1337/your-fitness-coach/issues/737) и исторический PR [#738](https://github.com/MikeMoore1337/your-fitness-coach/pull/738) | закрытая задача про Agent Harness v11: bounded evals, derived reports, secret rejection и owner-reviewable learning candidates | harness — исторический источник bounded tooling; он не является task-level telemetry и не восстанавливается как controller |
| [PR #1015](https://github.com/MikeMoore1337/your-fitness-coach/pull/1015) | Draft/open; head `c7a666950f89eaa4588852e4ae93c49bff470efe`; 3 commits, 2 files; CI run `38796626919` = success; reviews/merge/release не подтверждены | технический CI-пример без owner acceptance и production release; не считать результатом сравнения |
| [PR #1012](https://github.com/MikeMoore1337/your-fitness-coach/pull/1012) | merged fix #914; head `a093d41eb825ac177b4e473b3bfe0700f7552ab9`; CI run `38785633153` = success; merge в `master` зафиксирован | техническая готовность и release-трасса различимы; hardware acceptance всё ещё нужно подтверждать отдельно |
| [PR #978](https://github.com/MikeMoore1337/your-fitness-coach/pull/978) | merged; head `07f6efb651aa4e9ba540357ddcb9f5f9c45e4105`; run `38698005257` = success, run `38697885104` = cancelled | cancelled/rerun нельзя автоматически считать дефектом продукта или ошибкой модели |
| [PR #979](https://github.com/MikeMoore1337/your-fitness-coach/pull/979) | closed unmerged Draft; head `bace7c8564b8f479022d837784c111902b105a55`; run `38581812416` = success | зелёный CI не доказывает merge, owner approval или release |
| [Issue #1007](https://github.com/MikeMoore1337/your-fitness-coach/issues/1007), [#1014](https://github.com/MikeMoore1337/your-fitness-coach/issues/1014), [#1006](https://github.com/MikeMoore1337/your-fitness-coach/issues/1006) | открытые инженерные задачи без завершённого результата на момент снимка | нельзя использовать их как подтверждение производительности или качества; #1014/#1006 исключены из выборки |

## Что исключается из сравнения

- задачи с разными baseline, требованиями, доступом к файлам или обязательными проверками;
- результат без exact head, green required `checks` или evidence matrix;
- synthetic activity, выдуманные scores, token estimates из текста ответа, commit count как proxy стоимости;
- green CI при пропущенной acceptance, security, localization, accessibility, hardware или legal проверке;
- cancelled run без доказанного продуктового failure;
- owner intervention, merge, deploy или закрытие Issue, если для этого не было отдельного разрешения;
- private logs, user chats, secrets, PII и любые новые persistent lifecycle records;
- незавершённые параллельные worktree/PR как будто это принятые результаты.

## Критерии выбора модели

Сначала применяется жёсткий quality gate: пропущенный критерий, security boundary, локализация, регрессия или неподтверждённое существенное утверждение делает попытку неприемлемой независимо от скорости. Среди принятых попыток сравниваются кортежи:

`(criteria accepted, post-first corrections, verified defects, CI iterations, owner interventions, task-level cost data)`.

Скалярный балл не вводится: при `NO_DATA` по стоимости он создавал бы ложную точность. Если task-level cost/time unavailable, вывод ограничивается качеством и GitHub lifecycle evidence. Практическое решение по текущему снимку — **оставить текущую конфигурацию и не объявлять победителя**.

## Шаблон будущей записи

```text
Issue/PR:
Baseline SHA:
Класс задачи:
Модель/reasoning: exact value или NO_DATA
Начало/конец Codex task: exact event или NO_DATA
Первое изменение:
Первый технический результат:
Required Checks: run ID, URL, exact head, started/completed или NO_DATA
Коррекции после первой реализации:
Acceptance matrix:
Проверенные дефекты/регрессии:
Security/localization/accessibility/device status:
Owner acceptance:
Master/release evidence:
Ограничения и пропуски данных:
```

Шаблон не требует нового мониторинга или обязательного workflow. Если поле недоступно, в нём сохраняется `NO_DATA`, а не оценка по косвенному признаку.

## Текущий итог исследования

- Подтверждено: GitHub даёт воспроизводимую трассу Issue → PR → exact head → Checks → merge/release IDs и позволяет разделить техническую готовность, owner acceptance и production release.
- Подтверждено: optional harness/flow ограничены локальной помощью и не являются источником lifecycle или cost truth.
- Частично доступно: Actions run status, job status, PR/commit counts и lifecycle timestamps; прямую длительность CI и активное время Codex для этого исследования не удалось извлечь через используемый интерфейс.
- `NO_DATA`: task-level tokens, quota attribution и стоимость #1007. Account aggregate, сообщения и коммиты для этого не подходят.
- `NOT_RUN`: новый A/B-прогон моделей и optional harness report. Эта задача создаёт методику и не подменяет её экспериментальными результатами.

### Источники

- [Issue #1007](https://github.com/MikeMoore1337/your-fitness-coach/issues/1007), [Issue #737](https://github.com/MikeMoore1337/your-fitness-coach/issues/737), [Issue #1014](https://github.com/MikeMoore1337/your-fitness-coach/issues/1014), [Issue #1006](https://github.com/MikeMoore1337/your-fitness-coach/issues/1006).
- [Agent Harness](../agent-harness.md), [Agent Flow](../agent-flow.md), [Optional agent tools](optional-agent-tools.md), [Issue governance](../ISSUE_GOVERNANCE.md).
- [PR #1015](https://github.com/MikeMoore1337/your-fitness-coach/pull/1015), [PR #1012](https://github.com/MikeMoore1337/your-fitness-coach/pull/1012), [PR #978](https://github.com/MikeMoore1337/your-fitness-coach/pull/978), [PR #979](https://github.com/MikeMoore1337/your-fitness-coach/pull/979).
- baseline: [`2ed3b5d`](https://github.com/MikeMoore1337/your-fitness-coach/commit/2ed3b5d236ad08ade1b74a11c25d33c231d9057d), data read on 2026-10-16.
