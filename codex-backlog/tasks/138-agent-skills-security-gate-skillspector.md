# [Task 138] Agent Skills Security Gate / NVIDIA SkillSpector integration

- **Статус:** owner-selected, not started
- **Приоритет:** P0 / agent security and delivery governance
- **Тип:** implementation / external static-semantic security scanner integration + delivery gate
- **Основная роль:** `implementer`
- **Дополнительные роли lifecycle:** `qa-verifier`
- **Рекомендуемые skills:** `$security-engineer`, `$platform-engineer`, `$python-engineer`, `$qa-engineer`, `$technical-writer`
- **Условные skills:** `$llm-engineer` только если реализация изменяет provider/routing/prompt semantics за пределами documented SkillSpector CLI contract; `$privacy-engineer` только если фактический diff вводит новую передачу содержимого skills/telemetry или иной privacy/data-egress boundary
- **Зависимости:** hard dependencies нет; реализация начинается от текущего delivery/pre-push
  contract в `master`

<!-- task-session
executable: true
concurrency: exclusive-write
owner_gate: explicit-launch
integration: task-pr-to-master
-->

## Граница текущего прохода

Создание этого файла только регистрирует и проектирует задачу. На текущем проходе запрещены
установка SkillSpector, изменения CI, pre-push, `.agents`, application-кода, ролей и skills,
а также запуск implementation lifecycle новой task. Реализация начинается только после отдельной
явной команды owner.

## Исключение публикации

По отдельному явному разрешению владельца от 2026-09-04 этот task-файл публикуется в `master`,
несмотря на обычную owner-only границу `codex-backlog/tasks/**`. Исключение относится только к
этому файлу и не распространяется на другие backlog tasks, findings, manifests или operational
workpapers. Оно не разрешает реализацию task, установку SkillSpector или изменения delivery surface
на текущем проходе.

## Tracked publication closeout contract

Поскольку этот task-файл является tracked publication exception, его нельзя переносить после merge
в ignored `codex-backlog/tasks/done/` обычной локальной archive-операцией: это оставит deletion
tracked source в canonical worktree и нарушит последующие `doctor`/delivery checks. До terminal
production success implementation PR этой task обязан выполнить exact tracked `git mv` файла в
`codex-backlog/tasks/done/138-agent-skills-security-gate-skillspector.md`; узкое исключение для
этого единственного archive path закреплено в `.gitignore`. До merge нужно воспроизвести текущий
controller finish/closeout contract из canonical worktree и доказать clean status, tracked archive
destination и успешный backlog check. Если текущий helper не принимает pre-archived tracked task,
его существующий archive/closeout path следует минимально адаптировать и покрыть тестом; broad
unignore, отдельная archive-инфраструктура и silent deletion не допускаются.

## Цель

Внедрить NVIDIA SkillSpector как внешний статический/семантический security scanner для агентной
поверхности YFC и встроить его в существующий scope-aware delivery contract. Scanner должен
усиливать review безопасности `.agents`, не становясь новым YFC skill, новой role, meta-agent или
orchestrator и не превращая каждый обычный application PR в тяжёлый CI run.

Результат должен давать два различимых режима:

1. быстрый deterministic gate без LLM для локального/pre-push использования и автоматической
   проверки релевантных agent-surface изменений;
2. расширенный semantic audit с LLM только для добавления внешнего skill, существенного изменения
   существующего skill и периодического полного аудита `.agents`.

Оба режима должны честно показывать область, версию scanner, режим анализа, полноту проверки,
verdict, findings и ошибки. Ни один режим не должен маскировать неполную или неуспешную проверку
под `SAFE`.

## Что проверить в начале реализации

Перед установкой или фиксацией команд implementer обязан заново сверить официальную документацию,
исходный код CLI и release metadata для выбранной pinned-версии. Snapshot ниже отражает проверку
на 2026-09-03 и не освобождает от повторной верификации: upstream может изменить команды,
provider names, exit codes, формат baseline или правила рекурсивного сканирования.

На момент snapshot upstream показывал release `v2.11.0` и наблюдаемый commit/tag prefix
`b724108`. В реализации нельзя использовать плавающий `main`, незакреплённый `pip install`,
непроверенный latest или только короткую строку версии: нужно разрешить release в immutable
commit/source hash, закрепить его и проверить `skillspector --version`.

Проверенные для этого проектирования upstream-контракты:

- CLI сканирует single skill/directory и поддерживает входные Markdown skill files, архивы и
  Git-based sources; output formats включают `terminal`, `json`, `markdown` и `sarif`;
- `scan` поддерживает `--no-llm`, `--format`, `--output`, `--show-suppressed`, baseline-related
  options и `--recursive`; для каталога с несколькими skill directories нужно отдельно проверить,
  нужен ли `--recursive` в pinned-версии;
- текущий exit contract: `0` означает завершённый результат без score выше порога и может
  включать `SAFE` или `CAUTION`, `1` используется для `DO_NOT_INSTALL`/высокого risk score и
  может также использоваться при `--fail-on-incomplete`, `2` означает scanner/input/internal
  error. Поэтому wrapper обязан разбирать JSON verdict и completeness, а не доверять одному exit
  code;
- upstream поддерживает SARIF 2.1.0 и JSON с машиночитаемым `risk_assessment.recommendation`
  и metadata анализа; точные поля нужно зафиксировать тестами pinned-версии;
- документированный Codex provider в текущем upstream называется `codex_cli` и выбирается через
  `SKILLSPECTOR_PROVIDER=codex_cli`; он рассчитан на установленный и уже авторизованный локальный
  Codex CLI, а не на обязательный новый API key. Реализация обязана подтвердить этот контракт по
  pinned release и не добавлять новый платный provider как обязательный prerequisite;
- `--no-llm` не запускает LLM-анализ, но не следует трактовать его как zero-network guarantee:
  текущий trust model допускает передачу dependency coordinates в OSV.dev для dependency checks;
- SkillSpector по текущей документации не исполняет содержимое проверяемого skill, но сам scanner
  не является sandbox и не доказывает безопасность runtime-поведения агента;
- текущая upstream-документация прямо предупреждает, что non-English content может хуже покрываться
  pattern-based проверками. Русскоязычные и смешанные skills/references YFC нельзя считать
  серьёзно проверенными только после успешного `--no-llm`.

Допустимые upstream-факты, команды и поля должны быть зафиксированы в implementation evidence
с ссылкой на конкретный immutable release. Если pinned release расходится со snapshot, task
следует актуальному release contract, а устаревшие команды/поля не сохраняются «для совместимости»
без доказанной необходимости.

## Архитектурные ограничения

Обязательные ограничения:

- SkillSpector остаётся внешним scanner, а не частью YFC agent architecture.
- Не создавать `.agents/skills/skillspector` и вообще не описывать SkillSpector как новый YFC
  skill.
- Не создавать новую role. Не создавать `security-reviewer`, `skillspector-agent`, meta-agent,
  orchestrator или отдельный MCP/tool owner для запуска scanner.
- Не расширять существующую agent architecture без concrete contract need. Текущие roles и skills
  переиспользуются; их дублирование является дефектом task.
- Не сканировать frontend/backend или весь application repository. По умолчанию scanner получает
  только явно разрешённую agent surface.
- Не добавлять безусловный тяжёлый GitHub Actions job на каждый PR.
- Не добавлять параллельную delivery/pre-push инфраструктуру, второй источник scope/verdict,
  независимый duplicate wrapper или несвязанный набор CI rules.
- Не добавлять runtime dependency SkillSpector в frontend/backend/bot и не передавать ему secrets,
  production credentials, Telegram tokens, SSH keys или реальные user data.

Все новые файлы, настройки и команды реализации должны быть минимальными, version-controlled,
reviewable и объяснять, почему они принадлежат именно security gate.

## Режим A: быстрый deterministic gate без LLM

Минимальное намерение локального gate выражается upstream-командой:

```text
skillspector scan .agents/skills --no-llm
```

Для текущего CLI каталог с несколькими skills, вероятно, требует явного `--recursive`; итоговую
команду implementer обязан выбрать и проверить для pinned release. Предпочтительный machine-readable
вариант должен быть эквивалентен следующему только после такой проверки:

```text
skillspector scan .agents/skills --recursive --no-llm --format json --output <report.json>
```

Если upstream baseline не поддерживает multi-skill recursive scan, нельзя скрыть это ограничение:
нужно либо выполнять отдельные per-skill scans с корректным baseline, либо использовать aggregate
scan без неподдержанного baseline и задокументировать решение.

Deterministic gate должен:

- работать локально на Windows developer environment и в Linux CI в рамках существующего
  supported toolchain;
- быть пригодным для текущего local/pre-push/delivery gate, а не для отдельного ручного workflow;
- не вызывать LLM provider и не требовать новую платную API key;
- сохранять только минимальное machine-readable evidence в уже принятой task-scoped структуре,
  не записывать raw reports в репозиторий и не раскрывать чувствительные значения в логах;
- разбирать JSON (или строго проверенный альтернативный format), проверять scanner version, scope,
  completeness, recommendation и findings, а также согласованность exit code;
- возвращать отдельное состояние `NOT_APPLICABLE` для не затронутой agent surface, а не запускать
  scanner на application-only изменениях;
- fail closed при missing executable, unsupported arguments, malformed output, incomplete scan,
  exit `2` или иной несогласованности, не превращая проблему установки/сканера в `SAFE`;
- не выдавать более сильную гарантию, чем даёт static/no-LLM анализ.

`--no-llm` является быстрым deterministic security signal, а не полной security approval. Для
русскоязычных или mixed-language instructions серьёзный review обязан назначать semantic/manual
анализ согласно режиму B, даже если deterministic scan завершился с `SAFE`.

## Режим B: расширенный semantic audit с LLM

Semantic audit запускается только при одном из явно зафиксированных событий:

- добавляется новый skill, включая новый внутренний YFC skill; для русскоязычного или
  mixed-language skill semantic/manual review обязателен, даже если deterministic scan завершён
  с `SAFE`;
- добавляется новый внешний/third-party skill;
- существенно меняется существующий skill: инструкции, tool/MCP behavior, install/dependency
  guidance, remote links/downloads, permission requests, credential handling, safety/review
  controls или иная security-relevant часть, а не только formatting;
- owner запускает периодический полный аудит `.agents`.

Режим B не должен превращаться в обязательный LLM job на каждый PR и не должен запускаться для
обычного frontend/backend изменения.

Предпочтительный provider:

```text
SKILLSPECTOR_PROVIDER=codex_cli
```

Использование `codex_cli` разрешено только при подтверждённой поддержке pinned release, наличии
локального авторизованного Codex CLI и явном понимании того, какие scanner-eligible файлы уходят
провайдеру. Новый платный API/provider не является обязательным и не должен появляться в CI
только ради этой task. Secrets и auth state должны оставаться вне Git и вне evidence/logs.

Если semantic provider не настроен, недоступен, вернул incomplete result или его контракт
изменился, результат должен быть `NOT_RUN`/`SCANNER_ERROR`, а не `SAFE`. Для события, где semantic
review обязателен, acceptance/delivery agent change нельзя объявлять завершённым без отдельного
явного review decision. Это не разрешает молча откатываться к одному `--no-llm`.

В CI semantic audit по умолчанию не выполняется. Для него нужен отдельный owner-triggered/manual
или периодический путь, который использует тот же pinned wrapper и policy, но не разрастается в
новую агентную инфраструктуру.

## Agent-surface scope и CI trigger

Сначала составить inventory фактически загружаемых/исполняемых как instructions agent files и
проверить, какие из них SkillSpector действительно умеет сканировать. Минимальная начальная
allowlist:

- `.agents/skills/**` — обязательно рассматривать как relevant;
- `.agents/references/**` — включать только если проверка текущего threat surface докажет, что
  references реально являются инструкциями/входом scanner или могут менять security behavior
  agent skills;
- остальные `.agents/**` — включать только при таком же воспроизводимом доказательстве; нельзя
  добавлять весь каталог «на всякий случай»;
- root `AGENTS.md`, application paths и произвольные документы не становятся trigger/scanner input
  без отдельного documented threat-surface решения.

После inventory зафиксировать одну authoritative функцию/матрицу scope, которую используют
pre-push и CI. Проверить минимум следующие сценарии:

| Изменение | SkillSpector behavior |
| --- | --- |
| Только `frontend/**`, `backend/**`, `bot/**` или иные application-only paths | scanner job/step не создаётся и не запускается |
| Изменение `.agents/skills/**` | deterministic gate запускается; semantic audit определяется типом изменения |
| Изменение `.agents/references/**` | запускается только если этот путь вошёл в доказанную allowlist |
| Изменение другого `.agents/**` | не запускается без documented threat-surface justification |
| Полный периодический аудит | отдельный owner-triggered путь, не обычный PR job |

GitHub CI должен использовать существующий workflow/checks contract или его минимальное расширение:

- relevant-path detection выполняется до SkillSpector step/job;
- application-only PR не получает дополнительного работающего SkillSpector job и не тратит runner
  на scanner;
- `NOT_APPLICABLE` корректно учитывается текущим required `checks`, не становясь fake security
  pass для relevant changes;
- missing/failed scanner, malformed report, unsupported provider или incomplete coverage не могут
  стать skipped/success через условие job;
- не дублировать path lists и verdict mapping в нескольких workflow/scripts; authoritative scope и
  policy должны иметь одну понятную точку владения;
- не добавлять новый standalone workflow, если текущий CI может выразить conditional step/job в
  существующем контракте без заметного роста сложности.

## Интеграция с текущим delivery/pre-push contract

Текущий `master` уже содержит CI-equivalent local gate, scope-aware pre-push flow, exact-HEAD/evidence
contract и authoritative `scripts/ci_contract.py` / `scripts/pre_push_gate.py`, ранее введённые в
рамках Task 135. Task 135 является историческим контекстом, а не hard dependency: реализация должна
начинаться с inspection текущего `master` и минимально расширять существующие contracts только если
это подтвердит нужный extension point.

Обязательные свойства интеграции:

- pre-push и CI используют один pinned version, wrapper/config, scope decision и verdict policy;
- application-only push не запускает SkillSpector;
- relevant agent push запускает deterministic gate до candidate delivery;
- semantic audit остаётся opt-in для перечисленных событий и не маскируется под pre-push
  deterministic success;
- scanner evidence встраивается в существующую machine-readable gate evidence, а не создаёт
  вторую систему статусов/lease/closeout;
- exact HEAD, clean worktree, existing task lease/provenance и fail-closed semantics Task 135
  сохраняются;
- отсутствие tool binary/версия drift/неполный результат — явный failed/blocked gate;
- не менять release/production flow и не ослаблять authoritative GitHub CI.

## Policy результатов SkillSpector

Exit code сам по себе не является policy. Wrapper обязан нормализовать upstream output в отдельное
состояние YFC и сохранить исходный verdict/exit code для review.

| Upstream result | YFC policy |
| --- | --- |
| `SAFE` + complete scan + согласованные output/version/scope | `PASS`: deterministic security gate пройден; semantic/manual limitations всё равно записаны |
| `CAUTION` + complete scan | `REVIEW_REQUIRED`: не блокировать автоматически только из-за warning, но обязательно показать findings и потребовать review/disposition для нового или изменённого skill; это не должно незаметно считаться полной security approval |
| `DO_NOT_INSTALL`, `CRITICAL` или `HIGH` finding, либо score/verdict, который pinned policy классифицирует как критический | `BLOCKED`: принятие/delivery нового или изменённого skill запрещено до исправления и повторной проверки; обычная suppression не превращает критический finding в `SAFE` |
| exit `2`, internal/scanner error, missing binary, invalid JSON, unsupported provider/flag, version drift, incomplete/partial scan | `SCANNER_ERROR`/`NOT_RUN`: fail closed для required agent-surface change; никогда не трактовать как `SAFE` |
| relevant scope не затронут | `NOT_APPLICABLE`: scanner не запускается; это допустимый результат только для application-only/non-relevant изменения |

Критерии `CRITICAL`/`HIGH` должны быть сопоставлены с актуальным pinned SkillSpector output и
проверены тестами. Не зашивать в YFC устаревший список rule IDs или pattern counts без source
evidence. Любой `CAUTION` требует анализа человеком/reviewer, но не может использоваться как
автоматический blanket rejection: reviewer должен отличить accept-with-rationale, fix-required,
или escalation к owner.

Отдельно запретить safety bypass в policy:

- нельзя сделать relevant check зелёным через `continue-on-error`, unconditional skip,
  подавление exit code, пустой/подменённый report или удаление fixture;
- baseline/suppression не отменяет блокирующий verdict без предусмотренного task-specific security
  decision и повторяемого evidence;
- scanner error и отсутствие semantic provider не должны быть переписаны как `CAUTION` или `SAFE`.

## Baseline и suppressions для подтверждённых false positive

На snapshot upstream поддерживает baseline в YAML/JSON, текущую baseline schema version `2`,
`scanner_version`, rule/path/fingerprint-oriented entries и обязательное объяснение `reason`;
missing или malformed baseline должен приводить к error. Pinned release обязан быть перепроверен,
а фактическая schema — закреплена тестом.

Правила YFC:

- baseline/suppressions включать только при доказанном false positive, а не для уменьшения числа
  warnings перед merge;
- хранить один минимальный version-controlled baseline в выбранном documented месте вне scan input,
  если это нужно для корректной рекурсивной проверки;
- каждая запись должна быть максимально узкой: конкретный rule/fingerprint и path/message scope,
  с коротким объяснением, owner/reviewer, датой и review/expiry metadata там, где это допускает
  upstream schema или adjacent review registry;
- запрещены глобальные wildcard-ignore, path-less blanket suppression, отключение всей rule family
  и baseline «по всем текущим findings»;
- не suppress `CRITICAL`/`HIGH` для автоматического пропуска delivery. Подтверждённый спорный
  critical finding требует отдельного security/owner decision и всё равно не может исчезнуть из
  отчёта;
- suppression должна оставаться видимой в обычном diff/review, проверяться на malformed/stale
  entries и пересматриваться при смене scanner version, rule set или исходного skill;
- при unsupported baseline для recursive multi-skill scan использовать только поддержанный
  per-skill вариант или явно отказаться от baseline, не добавляя самодельный «совместимый» флаг;
- shipped baseline SkillSpector не включать автоматически без проверки происхождения и содержимого.

## Минимальная threat model

Security review task должна начать с активов и trust boundaries: `.agents` и task artifacts —
security-sensitive instructions/config; developer workstation и CI runner — разные execution
boundaries; SkillSpector и выбранный LLM/OSV provider — external components; Codex CLI auth и
environment — секретная boundary. Static/semantic scanning является defense-in-depth и не заменяет
review происхождения, least privilege и безопасное исполнение.

| Threat | Что проверять и какой остаточный риск зафиксировать |
| --- | --- |
| Prompt injection | Инструкции, заставляющие агента игнорировать system/task/review controls, менять приоритеты или выполнять attacker goal; static/semantic findings плюс manual adversarial review. Scanner не доказывает устойчивость к новой формулировке injection. |
| Hidden/malicious instructions | HTML/comments, zero-width/unicode obfuscation, encoded text, поздние/малозаметные paragraphs и инструкции, скрытые в references/assets; проверять отображаемый и raw content, не полагаться на один pattern. |
| Credential/token/SSH/env exfiltration | Запросы читать env, `.env`, SSH keys, cloud/GitHub/Telegram tokens, cookies или отправлять их наружу; искать exfiltration sinks/URLs и проверять, что scanner/provider/logs сами не получают secrets. |
| Arbitrary shell/code execution | `curl | sh`, произвольные shell/Python/PowerShell commands, создание persistence или запуск локальных файлов; scanner не должен исполнять skill, а reviewer проверяет реалистичный runtime abuse. |
| Unsafe `exec` / `eval` / `subprocess` / `os.system` | Code blocks, helper scripts и tool guidance с dynamic command construction, untrusted input и broad permissions; static match не заменяет review quoting, allowlist и process boundary. |
| Remote code download/execution | `curl`, `wget`, `Invoke-WebRequest`, remote `git/pip/npm`, install hooks и dynamic downloads; требовать pinned provenance/hash, no blind execution и явное user/reviewer consent. |
| Supply-chain threats | Typosquatted skill/provider/dependency, unpinned versions, mutable URLs/branches, binary payloads, unknown maintainer and transitive dependencies; фиксировать source, immutable revision, license/provenance и re-scan policy. |
| Excessive permissions | Требования доступа к filesystem, network, browser/session, secrets, Docker, GitHub, MCP или production; сравнивать с минимально необходимым scope и не выдавать скрытые credentials. |
| Scope escalation | Инструкции менять production, deploy/release, auth, CI rules, safety policy, другие tasks или пользовательские данные без declared authorization; review должен отделять task scope от escalation. |
| Memory/context poisoning | Запись ложных фактов или инструкций в persistent memory/context, попытка подменить backlog/owner decisions и закрепить вредное состояние; не разрешать auto-write и проверять provenance/approval. |
| MCP/tool poisoning | Подмена tool descriptions, MCP server instructions, untrusted tool output или рекомендации отключить confirmations; provider run должен быть без лишних tools/MCP, а skill — reviewed как untrusted instruction. |
| Отключение safety/review controls | Инструкции игнорировать pre-push/CI, скрывать findings, удалять logs/evidence, пропускать owner approval, отключать sandbox/confirmation или использовать `--no-verify`; такие patterns минимум review-required, а связанные critical/high findings блокируют. |

Для каждой находки reviewer/QA возвращает severity, attack scenario, affected trust boundary,
concrete remediation и verification method. Не объявлять scanner coverage доказательством отсутствия
угрозы.

## Языковое ограничение YFC

В YFC есть русскоязычные и mixed-language skills/references. Поэтому task прямо запрещает
формулировку «`--no-llm` прошёл — skill безопасен» для серьёзного security review. Реализация
должна:

- определить, какие static rules/patterns pinned SkillSpector действительно понимают на русском;
- добавить русскоязычные и mixed-language benign/malicious fixtures, не подменяя исходный язык
  автоматическим переводом;
- для нового/существенно изменённого русскоязычного skill назначать semantic/manual review;
- сохранять limitation в документации и report metadata;
- не считать англоязычную rule coverage доказательством полной защиты от русскоязычных
  prompt injection, exfiltration или safety bypass.

## Воспроизводимость и supply chain scanner

Установка выполняется только в будущей реализации, не сейчас. Implementer должен выбрать один
канонический, воспроизводимый Windows/Linux installation path на базе уже поддержанного toolchain
репозитория, без добавления SkillSpector в runtime dependencies YFC. Обязательны:

- pinned upstream release и immutable commit/source or package hash;
- lock/manifest/config, из которого другой developer и CI получают ту же версию;
- проверка checksum/signature/provenance настолько, насколько это поддерживает upstream и текущая
  platform policy;
- `skillspector --version`/equivalent version evidence в gate output;
- отсутствие floating `main`, `latest`, unpinned VCS ref и silent fallback на другую версию;
- отсутствие secrets в install command, environment committed files, logs или artifacts;
- понятный fail-closed результат при невозможности воспроизводимо установить/запустить scanner;
- отдельная проверка Windows developer environment и Linux CI, если текущий delivery workflow
  использует обе платформы.

Для semantic mode разрешается только уже авторизованный provider, предпочтительно documented
`codex_cli`; новый платный API, production credentials и real user data не являются допустимым
обязательным prerequisite.

## Тестовая стратегия и evidence

Добавить минимальные deterministic tests на общий wrapper/contract и не запускать реальный платный
LLM provider в CI. Покрыть:

- SAFE + complete, CAUTION + complete, DO_NOT_INSTALL/critical/high, exit `2`, missing binary,
  unsupported flag/provider, malformed JSON, contradictory exit/verdict, version drift и incomplete
  scan;
- path classifier: application-only PR не вызывает SkillSpector; `.agents/skills/**` вызывает;
  `.agents/references/**` и другие `.agents/**` следуют documented allowlist;
- semantic trigger: any new skill (including internal), new external skill, security-relevant
  substantial change и periodic full audit;
  formatting-only/application-only change не запускает LLM mode;
- malicious fixture, который гарантированно детектируется pinned SkillSpector как минимум по
  выбранному critical/high security scenario; тест не должен быть пустым grep-only substitute;
- benign YFC skills, включая русскоязычный/mixed-language benign fixture, проходят deterministic
  policy без необъяснимого blanket suppression;
- русскоязычный/mixed-language malicious fixture показывает documented limitation или требует
  semantic/manual review, а не создаёт ложную гарантию `SAFE`;
- baseline schema version, valid narrow suppression, malformed/stale suppression, out-of-scope
  wildcard и попытка suppress critical/high;
- pre-push/delivery evidence, current exact-HEAD/provenance semantics и GitHub `checks` behavior;
- Windows command/path/exit handling и Linux CI command/path/exit handling там, где это относится
  к существующему workflow;
- provider contract через deterministic fake/mock CLI shim или equivalent test seam без реальных
  credentials; отдельно документировать, как owner запускает настоящий semantic audit локально.

Каждый test должен проверять не только exit code, но и normalized state, scope, completeness,
scanner version, report path/redaction и отсутствие запуска в non-relevant PR. Raw security reports
хранятся только в canonical `.artifacts/` task locations и не коммитятся.

## Документация и затронутая поверхность

Реализация должна обновить документацию ровно настолько, насколько меняется фактический workflow:

- `.agents/README.md` — только если нужно объяснить безопасный lifecycle добавления/изменения
  skills и boundary внешнего scanner;
- существующую документацию delivery/pre-push/CI — только в соответствующем русском разделе;
- короткую runbook-инструкцию для local deterministic gate, opt-in semantic audit, verdict policy,
  baseline review, Russian-language limitation и troubleshooting;
- upstream links с pinned-version evidence, а не пересказ всей документации NVIDIA.

Не создавать новый `.agents/skills` или role documentation для SkillSpector. Не коммитить raw audit
reports, credentials или private provider output.

## Definition of Done

Task считается выполненной только когда одновременно подтверждено:

- [ ] SkillSpector имеет зафиксированную/pinned версию с immutable provenance, а не floating
      `main/latest`.
- [ ] Есть один воспроизводимый способ установки для Windows developer environment и Linux CI,
      соответствующий текущему YFC workflow.
- [ ] Есть локальный deterministic scan без LLM с проверенным для pinned release invocation,
      machine-readable output и fail-closed handling.
- [ ] Существующий pre-push/delivery gate использует scanner там, где затронута relevant agent
      surface; параллельная delivery infrastructure не создана.
- [ ] CI запускает проверку только при relevant `.agents` changes по documented allowlist.
- [ ] Обычные application-only PR не получают дополнительного SkillSpector job и не запускают
      scanner.
- [ ] Есть opt-in semantic audit для любого нового skill (включая внутренний YFC skill; для
      русского/mixed-language текста semantic/manual review обязателен), нового внешнего skill,
      существенного изменения existing skill и периодического полного `.agents` аудита.
- [ ] Проверена актуальная поддержка `codex_cli`; уже авторизованный Codex CLI предпочтён, а новый
      платный API не стал обязательным.
- [ ] Malicious fixture гарантированно детектируется pinned scanner/policy.
- [ ] Benign YFC skills, включая релевантные русскоязычные/mixed-language examples, проходят без
      необъяснимого global ignore.
- [ ] False-positive baseline/suppression policy документирована, version-controlled, minimal,
      объяснена и пригодна для review.
- [ ] `SAFE`, `CAUTION`, `DO_NOT_INSTALL`/critical verdict, `NOT_APPLICABLE`, `NOT_RUN` и
      scanner/internal error различаются машиночитаемо.
- [ ] Критические/high findings блокируют delivery нового/изменённого skill.
- [ ] Некритические findings требуют review/disposition, но не превращаются в безусловный отказ.
- [ ] Scanner failure, malformed output, missing binary и incomplete coverage не маскируются как
      успешная проверка.
- [ ] Ограничение русскоязычных инструкций явно описано; одного `--no-llm` не объявлено
      достаточной гарантией серьёзного security review.
- [ ] Threat model покрывает prompt injection, hidden/malicious instructions, credential/token/SSH/env
      exfiltration, arbitrary shell/code execution, unsafe `exec`/`eval`/`subprocess`/`os.system`,
      remote code download/execution, supply-chain threats, excessive permissions, scope escalation,
      memory/context poisoning, MCP/tool poisoning и инструкции по отключению safety/review controls.
- [ ] Проверены Windows developer environment и Linux CI там, где это относится к текущему
      workflow.
- [ ] `.agents` documentation обновлена ровно настолько, насколько требуется фактическим change.
- [ ] Существующие roles/skills переиспользованы; `.agents/skills/skillspector`, новая role,
      meta-agent и orchestrator не создавались.
- [ ] CI/delivery не стал заметно сложнее без обоснованной security/supply-chain причины; scope,
      trigger и verdict policy имеют один понятный источник истины.
- [ ] Для этого tracked publication exception final implementation PR выполняет exact tracked
      rename в `codex-backlog/tasks/done/138-agent-skills-security-gate-skillspector.md` либо
      минимально поддержанный существующим helper эквивалент, а controller finish/archive оставляет
      canonical worktree clean; ignored post-merge deletion не используется.
- [ ] Целевые tests, `git diff --check`, backlog/policy checks и применимый lifecycle review/QA
      завершены с evidence; production deploy не выполнялся как часть самой task без отдельного
      release contract.

## Out of scope

- установка или запуск SkillSpector в рамках создания этой task;
- изменения `.github/workflows`, `.pre-commit-config.yaml`, `scripts/ci_contract.py`,
  `scripts/pre_push_gate.py` или любых других implementation files на текущем проходе;
- сканирование всего YFC application repository;
- runtime sandbox, dynamic execution proof, automatic skill installation или automatic remediation;
- обязательный новый paid LLM/API provider;
- создание новых YFC roles/skills, meta-agent, orchestrator или MCP server;
- broad CI/release refactor, unrelated dependency upgrade и изменение production infrastructure.

## Upstream references

- [NVIDIA SkillSpector README](https://github.com/NVIDIA/SkillSpector/blob/main/README.md)
- [NVIDIA SkillSpector `pyproject.toml`](https://github.com/NVIDIA/SkillSpector/blob/main/pyproject.toml)
- [NVIDIA SkillSpector CLI source](https://github.com/NVIDIA/SkillSpector/blob/main/src/skillspector/cli.py)
- [NVIDIA SkillSpector suppression documentation](https://github.com/NVIDIA/SkillSpector/blob/main/docs/SUPPRESSION.md)
- [SkillSpector `v2.11.0` release](https://github.com/NVIDIA/SkillSpector/releases/tag/v2.11.0)
- [NVIDIA guide: Scanning Agent Skills](https://docs.nvidia.com/skills/scanning-agent-skills)

Upstream links используются как starting evidence; implementation обязана зафиксировать точный
immutable source/version, по которому реально выполнены команды и тесты.
