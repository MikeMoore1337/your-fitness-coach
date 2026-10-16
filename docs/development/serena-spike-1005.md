# Serena MCP: доказательное исследование для YFC

Issue: [#1005](https://github.com/MikeMoore1337/your-fitness-coach/issues/1005)<br>
Исходная ревизия: `474d920d29e373043d4216586095ad7c90f7eb2e` (`origin/master`, 2026-10-16)<br>
Дата проверки: 2026-10-16 (Europe/Moscow)
Режим: read-only исследование; Serena не устанавливалась и к Codex не подключалась.

## Решение

**DEFER: сейчас ничего не устанавливать и не подключать.**

Serena закрывает реальный класс задач — LSP-based поиск символов, ссылок,
реализаций, диагностики и безопасных symbol-level изменений. Но для YFC это пока
не доказанное улучшение относительно `rg`/прямого чтения исходников и локального
Graphify. Одновременно Serena добавляет отдельный пакет и language-server
зависимости, проектное состояние `.serena`, потенциальные записи/команды и
отдельные вопросы GPL-лицензии, сетевого egress и Windows/Linux-воспроизводимости.

Текущая рекомендация владельцу: оставить существующий стек обязательным для
исследований и разработки, а Serena рассматривать только как отдельный,
owner-approved пилот с заранее заданными критериями ниже. Это не является
утверждением, что Serena хуже; сравнительный запуск Serena не выполнялся.

## Границы и исходные данные

- Изменён только этот документ; application code, CI, deploy и production не
  затрагивались.
- Исследование выполнено в независимом worktree от свежего `origin/master`.
- Исходный commit одинаков для всех локальных сценариев: `474d920...`.
- Graphify был уже установлен: `graphify 0.9.63`. При bootstrap создан только
  игнорируемый локальный индекс в `.artifacts/shared/graphify/`; это не новый
  источник operational truth.
- Serena не обнаружена в PATH, в `%USERPROFILE%\\.serena` и в локальной конфигурации.
  Установка, активация, индексация YFC и подключение MCP намеренно не выполнялись.
- Проверены конфигурация `.codex/config.toml`, документация development/agent tools,
  `AGENTS.md`, локальный код и тесты. GitHub остаётся источником Issue/PR/Checks.

Локальная проверка Windows filesystem показала для worktree обычные ACL: владелец
`DESKTOP-U6JEQP9\\Mike`, у пользователя — `FullControl`, у sandbox-группы —
`ReadAndExecute`; shell-доступ Codex к этому managed worktree потребовал
разрешённого elevated read/write шага. Это ограничение текущего хоста, а не
доказательство разрешений Serena. Так как Serena не запущена, её фактические
filesystem permissions, sandbox и сетевой профиль остаются `NO_DATA`.

Проверка `Get-Command serena` и поиск `.serena`, `.mcp.json`, `mcp.json` в
worktree ничего не вернули. Это подтверждает отсутствие локального подключения,
но не заменяет аудит будущего MCP client config.

## Что уже есть в YFC

| Возможность | Текущий инструмент | Практический результат | Ограничение |
|---|---|---|---|
| Точный текстовый поиск и переход к файлу | Codex Desktop + терминал `rg` | Быстро находит определения, строки вызова, URL, fixtures и тестовые данные | Не понимает динамический dispatch и не строит полный call graph |
| Локальная навигация по коду | Graphify `0.9.63`, `scripts/graphify_yfc.py` | AST-граф, `explain`, `path`, `affected`, `query`, диагностика; без передачи исходников во внешний сервис | Вывод может быть широким, inferred, неоднозначным или обрезанным; direct source verification обязательна |
| Документация внешних библиотек | Context7 (`https://mcp.context7.com/mcp`) | Получены публичные официальные сведения о Serena без передачи кода YFC | Не анализирует репозиторий и не даёт точных token/latency counters |
| Browser/E2E диагностика | Playwright CLI и canonical `@playwright/test` | Можно проверять локальный dev/demo/test runtime | В этом spike не нужна: изменение UI/runtime не выполнялось |
| GitHub/Actions provenance | GitHub Issue, PR, Checks, Actions | Есть reproducible SHA и release path | Не заменяет semantic code navigation |

`docs/graphify-development.md` прямо ограничивает Graphify локальным code-only
анализом и требует сверять результат с исходниками и тестами. Это важное отличие
от предположения, будто сам граф доказывает поведение приложения.

Свежий code-only bootstrap Graphify дал: 1498 code files, 3363 пропущенных
non-code files (401 docs, 2960 images), 15 070 nodes, 52 697 raw edges,
47 585 valid candidate edges, 5112 dangling endpoint edges и 52 self-loops.
После post-build было 15 511 nodes и 47 879 edges, без post-build error.
Артефакты были игнорируемыми: `graph.json` 26 277 711 bytes и `manifest.json`
365 698 bytes. Эти числа описывают один локальный индекс, не качество Serena и
не runtime-структуру приложения.

## Воспроизводимые сценарии

Все времена ниже — один замер wall-clock для отдельного процесса PowerShell с
`System.Diagnostics.Stopwatch`; это диагностические значения, а не benchmark.
Повторяемость на другом хосте не гарантируется. Для Graphify использовался один
и тот же свежий файл `.artifacts/shared/graphify/graph.json`.

### S1. Определение функции, класса и всех использований

Цель: `get_user_timezone_name`.

```powershell
rg -n "get_user_timezone_name" backend frontend bot tests
graphify explain "get_user_timezone_name" --graph .artifacts/shared/graphify/graph.json
```

| Проверка | Результат |
|---|---|
| `rg` | 44 строки в 14 файлах; определение в `backend/fitminiapp_api/core/timezone.py`, вызовы в coach, food diary, CRM, cardio, wellbeing, nutrition, hydration, progress/report и других сервисах |
| Graphify | `EXIT=0`, `1649.3 ms`; узел `timezone.py:25`, degree 29, показаны 20 связей и ещё 9 |
| Пропущенные связи | Оба подхода не доказывают runtime-динамику, reflection, конфигурационные строки и поведение внешнего scheduler; `rg` не различает символ и одноимённый текст, Graphify не заменяет чтение callers |
| Ошибки | Нет |
| Токены/лимиты | `NO_DATA`; у `rg` нет token counter, Graphify не возвращал фактическое потребление токенов |

В этом сценарии Graphify дал более структурированный список связей, а `rg` был
измеримо быстрее в данном запуске (`112.1 ms`), но это не доказательство общего
преимущества какого-либо инструмента.

### S2. Цепочка API → service → ORM

Цель: daily wellbeing endpoint и его модель.

```powershell
graphify query "What is the path from the daily wellbeing API endpoint to its service and ORM model?" --graph .artifacts/shared/graphify/graph.json --budget 2000
graphify explain current_daily_wellbeing --graph .artifacts/shared/graphify/graph.json
graphify explain get_daily_wellbeing --graph .artifacts/shared/graphify/graph.json
graphify explain DailyWellbeingCheckIn --graph .artifacts/shared/graphify/graph.json
graphify path current_daily_wellbeing backend_fitminiapp_api_models_daily_wellbeing_dailywellbeingcheckin --graph .artifacts/shared/graphify/graph.json
rg -n "daily_wellbeing|current_daily_wellbeing|get_daily_wellbeing|DailyWellbeingCheckIn" backend frontend
```

Фактическая цепочка, подтверждённая прямым чтением:

`backend/fitminiapp_api/api/v1/check_ins.py` →
`backend/fitminiapp_api/services/daily_wellbeing.py` →
`backend/fitminiapp_api/models/daily_wellbeing.py` →
`backend/alembic/versions/0069_daily_wellbeing_check_ins.py`.

Связанные контракты и эффекты находятся также в
`backend/fitminiapp_api/schemas/daily_wellbeing.py`,
`frontend/src/shared/api/schema.d.ts`,
`frontend/src/features/wellbeing/DailyWellbeingCheckIn.tsx` и account
export/report/delete services.

| Проверка | Результат |
|---|---|
| Широкий Graphify query | `EXIT=0`, `2414.9 ms`; найдено 2299 nodes, вывод обрезан: `TRUNCATED`, показано 70 из 2299 при budget 2000 |
| Узкие Graphify queries | route `1806.8 ms`, service `1563.6 ms`; модель без полного ID — `EXIT=1`, `Ambiguous: matches 3 nodes`; полный ID path — `EXIT=0`, `2029.0 ms`, путь 2 hops с `[INFERRED]` |
| Найдено direct source | Endpoint, service transaction/validation, ORM constraints, migration, schemas, frontend contract/component и export/report/delete callers |
| Пропущено Graphify path | 2-hop путь не показал migration, schema, frontend contract и часть строковых/export side effects; без прямого поиска результат был бы неполным |
| Ошибки | Обоснованная диагностическая ошибка неоднозначности символа; широкий query обрезан |
| Время direct traversal | `NO_DATA`: отдельный полный wall-clock замер для чтения исходников не сохранялся |
| Токены/лимиты | `NO_DATA`; `--budget 2000` — лимит вывода Graphify, не фактический счётчик токенов |

Вывод: Graphify полезен как указатель на короткую call-chain, но не как
единственный контрактный или migration-impact анализ.

### S3. Зависимости React-компонента

Цель: общий `WeekStrip`.

```powershell
graphify explain WeekStrip --graph .artifacts/shared/graphify/graph.json
rg -n "WeekStrip" frontend/src frontend/tests
```

Результат Graphify: `frontend/src/shared/ui/WeekStrip.tsx:169`, `EXIT=0`,
`1763.8 ms`, degree 13. Найдены семь consumer-компонентов
(`TodayDashboard`, `NutritionDiary`, `CoachOperationsPanel`, `NutritionReport`,
`MealPlanner`, `GroceryList` и связанные импорты) и unit test.

Прямой поиск: `EXIT=0`, `50.8 ms`, 23 строки в 8 файлах — те же consumers,
сам компонент и `frontend/tests/unit/shared/ui/WeekStrip.test.tsx`.

Graphify не показал из этих symbol edges CSS/text contracts, prop semantics,
responsive behavior, runtime API data или все string-based test fixtures.
Изменение компонента поэтому требует чтения consumer props, shared tokens,
тестов и визуальной проверки; в рамках spike рефакторинг не выполнялся.

### S4. Влияние небольшого рефакторинга

Цель: оценить потенциальную область изменения `normalize_user_text` без внесения
самого рефакторинга.

```powershell
graphify affected normalize_user_text --graph .artifacts/shared/graphify/graph.json --depth 3
rg -n "normalize_user_text|classify_message|detect_chat_locale|inspect_chat_output" backend frontend tests
```

Graphify: `EXIT=0`, `1277.7 ms`, 22 direct/transitive nodes и 219 строк вывода;
цепочка включает safety/classification, chat service, adaptation, AI Coach API,
memory/context-related callers и тестовые узлы. `rg`: `EXIT=0`, `142.5 ms`,
4 прямых literal matches для helper-а. Таким образом, Graphify лучше подсветил
транзитивный call graph, а `rg` быстрее подтвердил фактические места текста.

Ограничения: `affected` не доказывает, что изменение семантики безопасно для
prompt-injection защиты, локализации, provider payloads или поведения тестов;
полный runtime/e2e и mutation test не выполнялись. Прямого теста, импортирующего
`normalize_user_text`, не найдено: существующие проверки в основном API/behavior
уровня (`backend/tests/test_ai_coach*.py` и fixtures).

### S5. Поиск связанных тестов

Цель: daily wellbeing component/model и связанные проверки.

```powershell
graphify explain frontend/src/features/wellbeing/DailyWellbeingCheckIn.tsx::DailyWellbeingCheckIn --graph .artifacts/shared/graphify/graph.json
graphify explain backend/fitminiapp_api/models/daily_wellbeing.py::DailyWellbeingCheckIn --graph .artifacts/shared/graphify/graph.json
graphify explain backend/tests/test_daily_wellbeing.py --graph .artifacts/shared/graphify/graph.json
rg -n "daily_wellbeing|DailyWellbeingCheckIn|current_daily_wellbeing" backend/tests frontend/tests
```

Graphify queries завершились успешно (`1526.2 ms`, `1654.8 ms`, `1516.6 ms`)
и показали component/model/test imports и account export/delete связи. `rg`
завершился за `47.3 ms`, 41 строка в 6 файлах:

- `backend/tests/test_daily_wellbeing.py`;
- `frontend/tests/unit/features/wellbeing/DailyWellbeingCheckIn.test.tsx`;
- `frontend/tests/unit/features/dashboard/TodayDashboard.test.tsx`;
- `frontend/tests/e2e/daily-wellbeing.spec.ts`;
- `frontend/tests/e2e/fixtures/platform-api.ts`;
- `frontend/tests/e2e/demo-mode.spec.ts`.

Graphify пропускает часть endpoint-string/mock-fixture связей, потому что они не
являются надёжными symbol edges. Прямой поиск лучше для completeness по URL,
fixture и snapshot-строкам. Ошибок не было; token counters — `NO_DATA`.

### S6. Потенциальные побочные эффекты изменения

Цель: `get_user_timezone_name` и локальная дата/время.

```powershell
graphify affected get_user_timezone_name --graph .artifacts/shared/graphify/graph.json --depth 3
rg -n "get_user_timezone_name" backend frontend bot tests
```

Graphify: `EXIT=0`, `987.8 ms`, 222 строки вывода / 219 affected entries.
Прямой `rg`: 44 строки в 14 файлах. Потенциальные зоны проверки — coach agenda
и CRM, cardio, daily wellbeing, food diary, hydration, nutrition plans,
progress/reports, reminders/notifications, program flows, AI context,
exports/handoffs и их tests.

Ни один инструмент не доказывает сам по себе корректность DST, naive/aware
datetime, пользовательской timezone, scheduled job и данных в PostgreSQL.
Это список для risk-based тестов, а не разрешение менять helper. Токены —
`NO_DATA`; фактическая runtime-регрессия не запускалась.

## Доступные измерения и честные ограничения

| Метрика | Результат |
|---|---|
| Serena latency/accuracy | `NO_DATA`: сервер не установлен и не подключён |
| Serena token usage/limits | `NO_DATA`: не было запуска и счётчика |
| Codex/`rg` token usage | `NO_DATA`: сообщения, файлы, вызовы и match lines не являются token measurement |
| Graphify token usage | `NO_DATA`: `--budget 2000` ограничил вывод одного query, фактический token counter не возвращён |
| Context7 token usage/limits | `NO_DATA`: ответы не содержали счётчика |
| Linux execution | `NO_DATA`: официальный compatibility review выполнен, реальный Linux runtime не запускался |
| Windows execution | Локально проверены только текущие YFC tools; Serena не запускалась |

Поэтому этот документ не утверждает, что Serena быстрее, экономнее или точнее.
Достоверные числа выше относятся только к конкретным локальным Graphify/`rg`
процессам и их wall-clock запуску.

## Serena по официальной документации

Источники: [official README](https://github.com/oraios/serena),
[tools](https://oraios.github.io/serena/01-about/035_tools.html),
[installation](https://oraios.github.io/serena/02-usage/010_installation.html),
[running/transport](https://oraios.github.io/serena/02-usage/020_running.html),
[configuration](https://oraios.github.io/serena/02-usage/050_configuration.html),
[workflow](https://oraios.github.io/serena/02-usage/040_workflow.html),
[memories](https://oraios.github.io/serena/02-usage/045_memories.html),
[security](https://oraios.github.io/serena/02-usage/070_security.html),
[privacy](https://oraios.github.io/serena/01-about/070_privacy.html),
[language support](https://oraios.github.io/serena/01-about/020_programming-languages.html),
[license](https://oraios.github.io/serena/01-about/060_license.html).

- Serena предоставляет symbol-level retrieval/edit/refactoring через LSP или
  JetBrains backend: declaration, references, implementations, diagnostics,
  rename и symbol body operations. Это функциональное пересечение с частью
  Graphify, но не результат YFC benchmark.
- LSP backend документирован как менее богатый, чем JetBrains backend для
  dependencies/type hierarchy. Для Python/TypeScript нужны language-server и
  runtime-зависимости; документация допускает их загрузку при активации.
- Официальные материалы указывают Python `>=3.11,<3.15`, что совместимо с
  текущим YFC Python 3.14 по диапазону, но реальный Serena runtime не проверен.
  Для TypeScript нужен Node/npm language-server. Реальная Linux-проверка —
  `NO_DATA`.
- Версии и поставка нельзя считать автоматически стабильными: официальный
  `pyproject.toml` в текущей ветке main показывает `2.0.1.dev0`, а официальный
  MCP registry `server.json` указывает опубликованный `serena-agent 1.5.3`.
  Любой будущий пилот должен явно pin-ить одну версию и отдельно подтвердить
  её license/lockfile/provenance.
- Приложение Serena и MCP/tooling в официальной документации лицензированы
  GPL-3.0-or-later; SolidLSP указан как MIT. Это требует отдельной legal/owner
  проверки перед распространением или обязательным использованием в компании.
- Конфигурация поддерживает `read_only`, `excluded_tools`, `ignored_paths`,
  project/global config и stdio/local HTTP режимы. Эти флаги — hardening controls,
  а не доказательство безопасности по умолчанию.
- Официальная модель memories предусматривает проектные `.serena/memories` и
  global memories, onboarding и maintenance. Это конфликтует с правилом YFC не
  добавлять постоянную память или второй operational source of truth без прямого
  owner approval. Даже если memory можно отключить, это должно быть явно
  проверено в отдельном пилоте.

## Безопасность и эксплуатационные риски

Статус оценки: `NEEDS_MANUAL_VALIDATION` для гипотетического будущего Serena
pilot; подтверждённых уязвимостей YFC от этого read-only исследования нет.

1. **Filesystem и secrets.** Serena выполняет чтение/запись файлов и может
   выполнять shell commands, если соответствующие tools доступны. `.gitignore`
   не является sandbox: `.env`, credentials, private docs и `.artifacts` надо
   явно исключать и не монтировать в проектную область. На текущем запуске
   ничего из приватных файлов Serena не получала.
2. **Network/egress.** stdio/local transport предпочтительнее. HTTP с
   несвязанным host может открыть MCP наружу. Language-server dependencies могут
   загружаться через uv/npm. Официальная privacy policy заявляет отсутствие
   передачи project/personal data на внешние серверы, но это vendor statement,
   не результат независимого сетевого теста. У Serena также описана anonymous
   usage reporting; его состояние в YFC не проверялось.
3. **Persistent state.** `.serena` и global `%USERPROFILE%\\.serena` создают
   дополнительные caches/memories и риск утечки/дрейфа контекста. Это не должно
   появляться в YFC без явного решения владельца и явного `no-memories`/
   `no-onboarding` hardening.
4. **Windows.** Документация Serena рекомендует native line endings и
   `core.autocrlf=true` во избежание больших diff. В этом YFC worktree сейчас
   `core.autocrlf=false`; менять это ради spike нельзя. Это конкретный риск
   шумных изменений и ложного результата review.
5. **Supply chain и maintenance.** Увеличиваются package/LSP surface, uv/npm
   downloads, версии language servers, OS-specific setup, лицензирование и
   ответственность за обновление. Serena не может стать обязательным CI gate
   без нового owner-approved решения.

### Минимальная конфигурация только для будущего owner-approved пилота

Это не выполненная настройка, а условия допуска:

- exact pinned Serena release, package hashes/provenance и license review;
- отдельный non-production worktree/container с read-only project config;
- stdio only, без публичного HTTP host и без production credentials;
- `excluded_tools` для shell/write/memory/dashboard по минимально нужному scope;
- `no-memories` и `no-onboarding`, проверка отсутствия `.serena`/global memory;
- explicit ignored paths для `.env*`, keys, `.artifacts`, private docs и caches;
- allowlisted dependency egress только после owner/security review;
- отдельные Windows и Linux runs с сохранёнными версиями и diff checks.

## Сложность обслуживания и критерии отмены

Сейчас стоимость Serena равна нулю: нет зависимости, конфигурации, индекса или
обновления. При внедрении добавятся package/LSP lifecycle, cache cleanup,
Windows/Linux drift, memory policy, security review, legal review и обучение
команды. Это существенная постоянная стоимость для инструмента, который пока не
показал измеримый выигрыш на YFC scenarios.

Внедрение можно обсуждать только если отдельный пилот, одобренный владельцем,
покажет на том же commit и на тех же 4–6 сценариях:

- меньше подтверждённых пропусков, чем у `rg` + Graphify + direct source review;
- воспроизводимый результат на Windows и Linux;
- приемлемую latency с повторными замерами, а не одним удачным запуском;
- доступные реальные counters для token/limit claims либо честный `NO_DATA`;
- отсутствие secret/private-source egress, неконтролируемых writes и persistent
  memory;
- приемлемую GPL/supply-chain/maintenance оценку.

Отменить пилот следует при любом подтверждённом доступе к secrets/private
payloads, непреднамеренной записи вне scope, невозможности отключить memory,
неприемлемом license/egress риске, регрессии line endings или отсутствии
существенного преимущества после повторных замеров.

## Rollback

Для текущего решения rollback не нужен: Serena не была установлена и YFC не
изменён. Если будущий пилот будет отдельно разрешён и окажется неприемлемым:

1. остановить MCP client/server и удалить его connection из isolated client config;
2. удалить только pinned Serena tool и её language-server dependencies в том же
   isolated environment;
3. удалить только созданные pilot `.serena`/cache после сохранения audit evidence;
4. закрыть/удалить только pilot branch/config changes; не менять YFC runtime,
   production secrets, `master`, Graphify или Issue history;
5. проверить `git status`, exact SHA и отсутствие untracked secrets.

Никакого merge, deploy, production rollback или автоматического закрытия Issue
этот spike не выполняет.

## Фактические вызовы Context7

Выполнены ровно два read-only вызова по публичной документации:

1. `resolve_library_id` для `Serena` с запросом об official MCP documentation
   для semantic code navigation/configuration. Получены `/oraios/serena` и
   `/websites/oraios_github_io_serena`.
2. `query_docs` для `/websites/oraios_github_io_serena` с вопросом о
   `ignored_paths`, read-only mode, language-server indexing, transport и
   persistent project memories.

В запросы не передавались исходники YFC, приватные файлы, secrets или user data.
Context7 не вернул token/limit counters: `NO_DATA`.

## Итог для #1005

- Решение: **DEFER**.
- Устанавливать или подключать Serena сейчас не нужно.
- Graphify и `rg` уже покрывают исследованные navigation/impact задачи, если
  результат проверяется прямым чтением исходников и тестов.
- Наиболее полезная будущая проверка — не ещё один документ, а короткий
  owner-approved, isolated, version-pinned comparative pilot с заранее
  зафиксированными acceptance/stop conditions.
- Документ не доказывает Serena accuracy, speed, token savings, Linux behavior,
  package hash/provenance или absence of network egress, потому что такой запуск
  намеренно не выполнялся.
