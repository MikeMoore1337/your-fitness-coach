## Постоянная политика quality gates

Codex Code Review отключён и не используется как release gate, поскольку расходует Codex usage.
Качество подтверждают детерминированные CI/tests/static-analysis checks и явно требуемые
для конкретной task human/external gates. Отдельный LLM review verdict не требуется.
Автоматические GitHub reviews, вызов `@codex review`, ожидание connector/fresh reviewed SHA,
review rate-limit waits, usage-reset credit ради review и waiver отсутствующего review запрещены.
Отдельную Codex review-задачу, роль или subagent для перечитывания diff не создавать.
Implementer выполняет один ограниченный self-review в текущей рабочей сессии перед commit;
после исправления дефекта повторяет только affected checks. Нового full self-audit не требуется.

Normal path: implementation → targeted verification → self-review → commit/push → exact-head CI
→ PR → required GitHub checks → merge → deploy → production smoke/closeout.
Для PR-triggered CI PR открывается перед ожиданием его required checks.
Обязательны relevant targeted tests PASS, применимые lint/format/typecheck PASS,
required integration/e2e PASS, exact-head CI GREEN и aggregate GitHub status `checks` GREEN.
Известные unresolved BLOCKER/HIGH текущей реализации/QA блокируют завершение.
PR должен быть mergeable и соответствовать branch/ruleset policy; уже существующие review threads
нужно фактически исправить и resolved. Создавать новый Codex review для этого запрещено.
PR-only master, required checks, non-fast-forward protection, thread resolution и CI сохраняются.
Профильные security/legal/destructive/owner/human/external gates сохраняются по фактическому риску;
они не должны заменять отдельный LLM review под другим названием.
Следующую product task автоматически не запускать.

# GLOBAL_RULES - правила выполнения release backlog v17 resource-aware

Этот файл действует для завершённых и архивированных release tasks `75-80`, включая буквенные
подзадачи, owner-approved Pulse concepts pilot `75C`, завершённую UX-reset gate `115A` и
completed implementation tasks `116-118`, current product task `119`, а также
trigger-gated post-release pool `81-101` с буквенными подзадачами и owner-selected pending tasks
`107-111` и owner-selected governance task `127`. Completed tasks `00-73A`, включая буквенные
подзадачи, tasks `74A-75`, отдельно завершённые tasks `103-106`, `112-118` не переигрываются и хранятся в
`tasks/done/`.

Tasks `109-111` остаются owner-selected pending: Landing offer использует только factual claims и
approved security baseline task `108`; avatar сохраняет private-media lifecycle; Progress не
выдумывает данные из визуального референса. Каждая требует отдельного owner запуска.

## Structured artifact contract

All new ignored files belong to the canonical `.artifacts/` structure: task data lives under
`.artifacts/tasks/<TASK_ID>/{temporary,evidence,deliverables,logs}` and is described by its
`manifest.json`; reproducible caches, process temp files and test output use
`.artifacts/runtime/{cache,tmp,tests}`; reusable local assets use `.artifacts/shared/`; backups,
deployment evidence and recovery data use the protected `.artifacts/operations/{backups,deployments,recovery}`.
Controller-managed worktrees remain under `.artifacts/worktrees/` and are never removed by a
filesystem cleanup.

New producers must use `scripts/artifact_manager.py` or an already configured canonical path.
Legacy top-level paths are migration inputs only and must not receive new output. Run
`python scripts/artifact_manager.py --root .artifacts --repo-root . validate` to detect unknown
top-level paths and ad-hoc source references. Run `audit`/`dry-run` before cleanup; apply only the
exact owner-approved plan SHA after controller/worktree safety checks. `REVIEW`, active/dirty/
interrupted/unique-commit/recovery data, deliverables and operational backups are not generic
cleanup targets.

## Полный task lifecycle

Перед каждой task обязательно прочитать и выполнить `codex-backlog/TASK_EXECUTION_LIFECYCLE.md`.

Фраза владельца `полный task lifecycle` ссылается именно на этот контракт. Он выполняет только основную роль, core/conditional skills и дополнительные lifecycle-роли, которые явно применимы к текущей task, с конечными verification/QA шагами и одним логическим commit.

Lifecycle не расширяет scope task и не отменяет явно объявленные owner checkpoints, Trigger/evidence
gates, conditional/skip conditions, security/privacy rules или запрет внешних production actions
без разрешения. Если текущая task не содержит обязательного checkpoint, lifecycle автоматически
продолжает следующий разрешённый шаг после terminal success и не ждёт дополнительного owner prompt.
Нельзя создавать неявную остановку формулировкой «нужно подтверждение владельца» без конкретного
gate, evidence и точки остановки в task-файле.

## Skills: обязательный контракт выбора

Каждая current/pending task задаёт два уровня skills:

- `Рекомендуемые skills` - core skills primary role. Их открыть в начале.
- `Условные skills` - подключать **только** после фактического trigger из task. Не открывать заранее.

Перед работой Codex обязан:

1. прочитать корневой `AGENTS.md`;
2. открыть только core skills текущей task;
3. использовать их как профильные рабочие контракты;
4. открыть conditional skill только если inspection/diff подтверждает его trigger;
5. не расширять scope только потому, что skill описывает более широкую практику;
6. self-review выполняет primary writer в текущей сессии; для применимой QA использовать `$qa-engineer`;
7. для обычной QA ограничиваться применимым base skill роли и максимум 1-2 профильными skills текущего риска.

Маршрутизация по фактическому scope:

- `$frontend-engineer` - базовый skill обычной client-facing UI implementation. `$mobile-engineer` подключается при mobile keyboard/safe-area/viewport/lifecycle/touch/device-runtime риске, а не только потому, что UI виден на смартфоне.
- `$telegram-engineer` нужен только при изменении Telegram-specific API/runtime/adapter/initData/BackButton/safe-area/deep-link/real-client behavior. То, что shared UI показывается внутри TMA, само по себе не является trigger.
- `$accessibility-engineer` подключается отдельно при сложном/new interaction, подтверждённом accessibility finding или в dedicated hardening task. Базовые labels/focus/keyboard/touch требования остаются обязанностью frontend/mobile implementation.
- `$fitness-domain-reviewer` нужен, когда меняются fitness/nutrition/cardio/anthropometry формулы, семантика данных или интерпретация. Простое отображение уже утверждённых значений не требует отдельного доменного прохода.
- `$data-engineer` нужен при schema/migration/query/invariant scope; `$backend-engineer` - при реальном backend/API/domain change. Не подключать их только из-за теоретического edge case.
- `$security-engineer`/`$privacy-engineer` подключаются при соответствующей trust/data boundary или dedicated audit, а не на каждый authenticated экран.
- `$product-designer` нужен для реального UX/visual decision; `$ui-audit` - для dedicated visual audit/hardening, а не каждого UI diff.
- `$motion-design-engineer` нужен для существенного motion design/gesture/data animation или dedicated motion review. Одна обычная короткая CSS transition не требует отдельного skill.
- `$ui-prototyper` используется только явно для isolated design exploration нескольких направлений и не запускается автоматически.
- `$solution-architect` нужен при cross-system contract conflict/architecture decision, а не для обычной реализации существующего паттерна.
- `$ru-legal-risk` обязателен для dedicated legal-risk audit; в обычной task он conditional только
  при фактическом изменении personal/health data, providers, payments, legal/consent UI, data
  residency, recommendation logic, advertising/claims или external licenses. Dedicated audit
  использует primary role `product-lawyer`, существенные выводы требуют актуальных авторитетных
  источников, а remediation после owner decision выполняется отдельной implementation task.

При конфликте соблюдать приоритет: безопасность и приватность -> фактическое поведение продукта -> текущая task -> профильные skills.

## Главный процесс

- Один executable task-файл = одна Codex-сессия = одна `task/<ID>-<slug>` ветка = один отдельный
  worktree = один законченный логический результат. Umbrella `90`, `92`, `93`, `94`, `95`, `99`,
  `100` являются coordination contracts и отдельно не выполняются.
  Implementation exclusion действует только для `exclusive-write` lease в состояниях
  `starting/implementation/review/qa`; после durable readiness task lease сохраняется, но
  implementation exclusion освобождается. Обычная task без `concurrency` metadata считается
  `independent-write`; `exclusive-write` используется только для действительно global или
  coordination-sensitive изменений. Delivery lane хранится отдельным минимальным mutex/queue.
- `master` является единственной защищённой release-веткой. Task branch/worktree создаются от
  чистого, проверенного exact `origin/master` SHA; feature implementation непосредственно в
  canonical controller worktree запрещена.
- Внутри текущей task после terminal success автоматически выполняются self-review, применимую QA,
  commit, PR в `master`, CI и normal release шаги, если task явно не объявляет checkpoint или
  blocker. Следующая product task автоматически не запускается.
- Явный выбор task владельцем или `scripts/run_task_delivery.py <ID>` является одним standing
  authorization на normal path этой task. Низкоуровневые controller stages не являются действиями
  владельца и не создают повторных generic approval prompts.
- `scripts/task_session.py` и shared Git common-dir leases являются обязательной coordination
  boundary. Task PR идёт только в `master`; exact-head `checks` и current-base policy разрешают
  merge только для текущего task head. Implementation compatible `independent-write` tasks может
  идти параллельно, а одна delivery lane сериализует refresh, PR, CI, merge, production и smoke.
  Занятая delivery lane, CI или active production deploy не блокируют новую совместимую
  implementation task; они блокируют только acquisition/delivery critical section. `READY_FOR_DELIVERY`
  также не удерживает implementation exclusion.
- Новая production revision попадает в remote `master` только через merged PR с обязательным green
  check `checks`; direct push, force-push и удаление `master` запрещены Ruleset. Merge PR является
  release authorization и без отдельного ручного approval запускает post-merge CI, exact-SHA
  provenance gate и автоматический production deploy. History rewrite, ручные production-команды,
  bootstrap, infrastructure recovery и SHA вне текущего merged `master` остаются exceptional
  actions с отдельным owner approval, backup и preflight.
- Для `AUTO_RELEASE_ELIGIBLE` task нормальный release path выполняется без дополнительного вопроса
  владельцу: `implementation/self-review/QA -> relevant local checks -> logical commit/push ->
  task PR master -> current-base/provenance check -> exact-head GitHub checks -> merge master ->
  post-merge provenance/image publish -> immutable bundle deploy -> production smoke -> controller
  finish/clean task worktree and merged local branch -> archive task -> rebuild/check backlog
  manifests -> terminal report`. Полный локальный regression run доброволен и не создаёт release
  evidence; direct push в `master` запрещён.
- Implementation/self-review/QA нескольких совместимых `independent-write` task могут быть
  параллельными. Master integration и production delivery остаются **strictly serial**: только
  delivery owner может refresh/rebase, проверить provenance, открыть/обновить PR, merge или deploy.
  Если current base изменился, candidate обновляется перед push; exact-head required checks
  выполняет GitHub CI. Busy delivery/production только переводит candidate в
  `WAITING_FOR_DELIVERY`, а dirty, interrupted, conflict или ambiguous state останавливаются с
  точным blocker. READY/waiting/CI/production не блокируют новую совместимую `independent-write`
  task; independent task совместима с активной `exclusive-write`, пока serial delivery не выявит
  реальный конфликт файлов. Новая `exclusive-write` task консервативно ждёт активную implementation
  task.
- Task с явно обязательным owner checkpoint/approve, human/device evidence, manual visual approval,
  legal-counsel gate или destructive/external authorization останавливается ровно перед указанным
  gate до фактического прохождения. Task без tracked logical commit не создаёт PR; отсутствие
  checkpoint само по себе не является причиной ожидания.

Если текущая task не объявляет `OWNER_CHECKPOINT`, `HUMAN_EVIDENCE`, `MANUAL_VISUAL_APPROVAL`,
`LEGAL_COUNSEL_REQUIRED`, `EXTERNAL_AUTHORIZATION`, `DESTRUCTIVE_ACTION` или terminal blocker,
controller/lifecycle после terminal success автоматически продолжает self-review, применимую QA,
commit, task PR в `master`, required CI и normal release без дополнительного owner prompt.
Тишина владельца не является gate. Следующая product task автоматически не запускается.

После terminal successful normal deploy post-deploy closeout тоже не создаёт owner gate: `finish`
из canonical controller worktree автоматически удаляет только exact matching clean task worktree и
merged local branch без `--force`, затем canonical archive helper переносит task в `tasks/done/` и
rebuild/check manifests. Dirty/interrupted/unique/ambiguous state, divergence refs или archive/check
error останавливают closeout fail-closed с сохранением данных.

Direct push в `master` запрещён. Legacy `dev` refs не являются частью normal delivery и не должны
использоваться как release prerequisite. Required `checks` всегда привязан к exact PR head и
текущему base.
- Перед началом прочитать корневой `AGENTS.md`, этот файл, lifecycle и только текущую task.
- Tasks `00-73A`, включая буквенные подзадачи, подтверждены владельцем как завершённые, перенесены в `tasks/done/` и не выполняются повторно.
- Owner-selected task `103` завершена после owner approval и архивирована.
- Owner-selected task `104` завершена после owner approval и архивирована.
- Owner-selected task `104A` завершена после owner approval и архивирована.
- Tasks `74A` и `74` завершены после owner approval и архивированы.
- Task `75A` завершена и архивирована после owner screenshot approval и решения
  `START_RETHINK_EXPLORATION`; её audit/frozen findings стали входом `75B`.
- Task `75B` завершила explicit exploration/selection gate; владелец выбрал
  `SELECT_DIRECTION_PULSE` только как набор концепций поверх текущего UI.
- Owner-approved task `75C` завершила bounded production pilot; production baseline остаётся
  `DESIGN_V2_1` с выбранными Pulse-концепциями.
- Owner-selected tasks `103-105` завершены и архивированы.
- Owner-selected task `106` завершена и архивирована после owner screenshot approval.
- Tasks `79-80` завершены и архивированы после owner approval. History rewrite `master` запустил
  намеренный automatic production workflow; владелец подтвердил auto-deploy как feature, а trigger
  contract закреплён в обязательной документации. Tasks `114`, `115A` и `116-118` завершены и
  архивированы после отдельных owner approvals; factual next product task — `119`, но её
  implementation не запущена.
- Owner-selected task `107` создана для scheduled regression и закрытых Allure-отчётов; она не
  не является current, не меняет UX-reset critical path и требует отдельного owner запуска. DNS,
  Cloudflare Access/hosting, secrets и paid resources требуют дополнительного explicit approval.
- Owner-selected task `108` создана для полного аудита соответствия законодательству РФ и
  непрерывного legal-impact gate для любых будущих tasks; она не является current, не меняет
  UX-reset critical path, требует отдельного owner запуска, primary role `product-lawyer` и обязательной
  проверки итогового baseline/gate профильным российским юристом; `LEGAL_COUNSEL_REQUIRED`
  выделяет дополнительные спорные вопросы.
- Owner-selected task `112` завершена и архивирована: current-stack blue/green deployment,
  online-migration gate, old-asset overlap, single-owner worker/bot handoff и rollback проверены
  локально. После explicit owner approval production revision `194cf036` успешно развёрнута на
  constrained VPS через предусмотренный `single-slot` fallback с bounded downtime; evidence имеет
  verdict `active`, все stages прошли, public/API/SEO и ownership worker/bot проверены. Это не
  является доказательством production zero observed downtime или общей HA.
- Task `113A` завершена, выпущена в production revision `17bee56c` и архивирована после owner
  acceptance `2026-08-30`. Task `114` завершена и архивирована после owner approval; Task `115A`
  является current/not started и требует отдельной команды на запуск lifecycle.
- UX-reset sequence `115A -> owner approval -> 116..123 -> 81 -> 82 -> 84 -> 124A -> owner release
  approval -> 124B -> conditional 124C` продолжается с current/not-started Task `119` и не отменяет собственные Trigger,
  dependency и owner decisions task files.
- Task `50A` уже создала общий continuous Mobile Web/TMA gate, который переиспользуют последующие client-facing tasks.
- Перед client-facing task прочитать `MOBILE_TMA_FIRST_CONTRACT.md` и применимые пункты `.agents/references/MOBILE_TMA_ACCEPTANCE_MATRIX.md`.
- Не повторять полный аудит репозитория без прямого требования task; завершённая `75A` была таким
  явным design/motion-аудитом, `75B` выполнила exploration, `75C` реализует только выбранный pilot,
  а `76` проверяет последующие
  regressions/gaps после разрешения design gate.
- Старые changelog и выполненные task-файлы являются историческим контекстом и не задают pending order. Удалённые legacy `masters/` и `references/` не являются sources of truth.

### Роли lifecycle

`Основная роль` и `Дополнительные роли lifecycle` в task являются точным маршрутом. Не строить автоматическую multi-agent review chain и не создавать отдельного агента на каждый skill.

Для dedicated legal-risk audit основной ролью может быть read-only `product-lawyer` с обязательным
`$ru-legal-risk`. В обычной implementation task legal surface не меняет основную роль автоматически.

Если следующая task сама является dedicated approval/audit gate, не дублировать полный аналогичный audit в предыдущей task без явного требования. Примеры: `49B1 -> 49C`, `49E -> 49F`, `75A -> 75B`, `78 -> 79`.

### Blocking policy for quality/QA findings

- Только `BLOCKER/HIGH` блокируют завершение.
- Незакрытый `MEDIUM` не блокирует локальный lifecycle/commit, но блокирует автоматический release:
  перед `AUTO_RELEASE_ELIGIBLE` PR незакрытых `BLOCKER/HIGH/MEDIUM` должно быть ровно ноль.
- `MEDIUM/LOW/NIT/OUT_OF_SCOPE` не блокируют commit и не открывают новый workstream.
- Legal fields `RISK: CRITICAL/HIGH/MEDIUM/LOW` из `$ru-legal-risk` являются отдельной
  product/legal risk scale, не lifecycle severity. Canonical legal risks хранятся в
  `docs/private/legal/LEGAL_RISK_REGISTER.md` после owner checkpoint; только technical/audit-deliverable
  findings с lifecycle severity `MEDIUM/LOW` синхронизируются в `bugs/FINDINGS.md`.
- Каждый `MEDIUM/LOW` из quality verification, QA или audit до commit и финализации обязательно добавляется или
  обновляется в `codex-backlog/bugs/FINDINGS.md`, даже если исправлен в той же task. Финальный
  ответ или ignored `.artifacts/` не заменяют tracked-реестр.
- Если finding исправлен и проверен в текущей task, отдельный bug-task не создаётся. Неисправленный
  finding становится task в `codex-backlog/bugs/pending/` только после triage и явного решения
  владельца по правилам `codex-backlog/bugs/README.md`; он не меняет очередь product tasks.
- Результат `MEDIUM, но коммитить нельзя` запрещён: если task действительно неприемлема, finding должен быть `HIGH/BLOCKER` с воспроизводимым обоснованием.
- Primary writer выполняет один self-review в текущей сессии. После blocking fix выполняется только targeted recheck закрытого набора finding IDs.
- Обычная task: self-review + targeted recheck изменённых сценариев; QA - один pass + один targeted recheck при blocking defect. Дополнительные циклы только в исключениях lifecycle.
- Non-blocking finding, требующий migration/schema/API/platform architecture/new dependency/new role/new skill, всегда уходит в follow-up/owner decision.

## Active design source и alternatives gate

- Перед visual work прочитать `ACTIVE_DESIGN_SOURCE.md`.
- `DESIGN_V2_1` является текущим production baseline, пока отдельная owner-approved design task не активирует новую систему.
- Для обычных feature/fix tasks baseline используется как consistency contract и не переигрывается побочно.
- Для explicit design exploration/redesign весь Design V2/V2.1 разрешено пересматривать.
- Устойчивые design anchors: sport-tech, mobile-first, lime/black/white brand core, product truth, accessibility, usability и performance feasibility.
- Новые design/motion skills являются инструментом исследования качества, а не автоматическим доказательством, что baseline нужно заменить.
- Любой полный redesign требует owner selection/checkpoint перед массовой production rollout.
- После выбора новой системы обновить `ACTIVE_DESIGN_SOURCE.md`, durable design docs и применимые backlog contracts.
- Landing и authenticated product могут получать новый visual language в рамках такой design task, сохраняя единый YFC brand core.
- TMA остаётся частью того же продукта; platform-specific runtime не требует отдельной случайной эстетики.

## Обязательный design delivery contract для tasks `57-79`

Этот раздел применяется ко всем remaining tasks и устраняет расплывчатое требование «учесть
дизайн». Task-specific раздел уточняет поверхность и evidence, но не может ослабить этот baseline.

### Источники до visual work

Перед изменением пользовательского UI обязательно прочитать:

1. `codex-backlog/ACTIVE_DESIGN_SOURCE.md`;
2. `docs/design/design-direction-v2.1.md`;
3. `docs/design/component-principles-v2.md`;
4. только релевантные текущей поверхности документы из canonical списка active source;
5. фактическую production implementation и representative browser render соседней поверхности.

Historical renders и завершённые tasks не являются вторым source of truth. Если новая композиция
существенно расходится с active source или требует новой semantic role, остановиться на owner
checkpoint до массовой реализации.

### Design brief до реализации

Для новой или существенно меняющейся композиции implementer до кода фиксирует в working notes:

- пользователя и контекст использования;
- одно главное действие текущего состояния и secondary/recovery actions;
- порядок информации `главное -> подтверждающие факты -> детали`;
- какие shared components/tokens переиспользуются;
- mobile и desktop composition, включая max-width, gutters, adjacent spacing и bottom navigation;
- loading/empty/error/partial/disabled/permission/offline states;
- какие browser screenshots и geometry assertions докажут результат.

Это не отдельный redesign artifact и не расширение scope. Brief нужен, чтобы visual decisions не
возникали случайно во время CSS-правок.

### Текущие component baseline для обычных implementation tasks

Эти правила удерживают consistency текущей production системы в обычных tasks. Dedicated owner-approved redesign может заменить их полностью вместе с active design source. Они не являются вечными эстетическими запретами.

- На одной decision surface один primary action: `--v2-lime` + `--v2-on-lime`. Secondary,
  navigation и recovery остаются neutral. Compatibility token `--accent` нельзя использовать как
  единственное доказательство brand-primary.
- Selected/current state использует neutral active surface, усиленный label и lime boundary; lime
  fill не размножается на соседние controls.
- Shared `DataConfidence` использует neutral surface и одинаковую левую lime boundary во всех
  `sufficient`/`limited`/`insufficient`/stale states. Эта полоса является фирменной геометрией
  компонента, а не оценкой качества данных; смысл состояния передают текст и иконка.
- Все action buttons используют `--radius-action`; icon-only controls сохраняют не меньше `44px`
  touch target. Shared `DisclosureIcon` всегда имеет `28 x 28px`, `flex: 0 0 28px` и круг
  `border-radius: 50%`.
- Для любого реального семидневного контекста используется shared `WeekStrip`; page-local week
  markup/CSS запрещены.
- Card разрешена для самостоятельной task/entity/selection/recovery boundary. Rules, typography и
  whitespace предпочтительнее универсальных subsection cards; card-inside-card и KPI-card grid
  для каждой цифры запрещены.
- Использовать semantic tokens и spacing scale `4/8/12/18/28/44px`. Literal feature palette,
  локальная button geometry, отрицательные margin и absolute overlay для соседних content regions
  запрещены.
- Desktop content сохраняет canonical max-width и responsive gutters; mobile compactness
  достигается удалением лишних wrapper padding/gaps, а не microtype или уменьшением touch target.
- Charts имеют units, period, truthful scale, empty/insufficient state и text/table alternative;
  цвет и hover не являются единственным носителем смысла.
- Mobile Web и TMA используют одну component tree, typography, geometry и YFC Light/Dark. Telegram
  может отличаться только platform behavior, описанным TMA contract.

### Browser evidence и regression

Для visual implementation до завершения task обязательно:

- marketing/product proof screenshots всегда снимать из **текущего authenticated-интерфейса**
  приложения на обычных production routes/components с локальными детерминированными тестовыми
  данными. Не использовать для них demo-кабинет, demo-labelled chrome, устаревшие mockups или
  персональные production-данные. Demo screenshots допустимы только для явно обозначенного Demo
  narrative. После изменений иконографики, navigation или layout такие proofs переснимать;
  provenance фиксировать как минимум через route, theme, viewport, fixture, bytes и SHA-256;
- проверить фактический render минимум на `360x800`, `390x844`, `430x932`, `768x900` и desktop
  `1280` или `1440`; применимые Mobile Web и mocked TMA states сравнить при одинаковом viewport;
- покрыть Light/Dark, основной state и хотя бы один релевантный empty/error/partial/long-content
  state; реальный Telegram отмечать отдельно от mock;
- проверить no horizontal overflow, touch targets, keyboard/safe area/bottom navigation и
  `prefers-reduced-motion` там, где они затронуты;
- измерить bounding boxes соседних regions на desktop и контрольных mobile widths, чтобы gutters,
  gaps, fixed navigation и disclosures не пересекались;
- для brand-critical controls закрепить browser assertions по computed token colors, boundary,
  `--radius-action` и фиксированной geometry, а не только screenshot;
- выполнить Human Design Test из `$product-designer`: brand swap, screenshot, card, decoration и
  designer-intent checks; после первого browser render сделать минимум один refinement pass;
- сохранить representative screenshots в `.artifacts/tasks/<TASK_ID>/evidence/screenshots/`;
  исторические `.artifacts/screenshots/task-XX/` являются legacy evidence и не пополняются;
  `.artifacts/` не коммитить.

### Owner visual checkpoint

Если task создаёт новую пользовательскую поверхность, существенно меняет композицию или primary
action, до единственного логического commit показать owner representative screenshots: desktop,
compact Mobile Web и Dark TMA/эквивалентный Dark mobile state. Без явного owner approval task не
архивировать и commit не создавать. Для чисто non-visual task записать `visual checkpoint: N/A` с
обоснованием; скрытые UI-изменения под этим исключением запрещены.

Нарушение explicit active design/component contract является `HIGH`, если из-за него task не
соответствует acceptance. Субъективное предпочтение без ссылки на contract/evidence не становится
blocking finding.

## Архитектура

- Не переписывать проект с нуля и не проводить большой рефакторинг ради красоты.
- Web, Mobile Web и Telegram Mini App используют общую кодовую базу, backend и YFC Design System.
- TMA отличается платформенной интеграцией, а не отдельной палитрой, компонентами или бизнес-логикой.
- Не создавать второй frontend, вторую auth-систему или параллельные доменные модели.
- Детерминированные расчёты имеют один источник истины в backend/domain logic.
- Не добавлять Redis, микросервисы, отдельный search server, тяжёлую chart/animation framework или обязательную платную зависимость без доказанной необходимости.
- Внешние интеграции обязаны иметь timeout, ограниченные повторы, безопасные ошибки и предусмотренный fallback.

## Граница первого релиза

До task `79` не входят и не могут становиться скрытыми зависимостями:

- AI Coach и AI provider infrastructure;
- английская локализация;
- импорт программ из XLSX/CSV/TXT/DOCX;
- новостной канал и редакционный конвейер;
- progress photos;
- PWA-installability;
- monetization/entitlements;
- wearables/Health/Strava;
- delegated admin hierarchy;
- native mobile application.
- hydration tracking, daily sleep/mood check-ins и новые habit reminder templates;
- explicit trainer report handoff и AI report interpretation;
- food-photo recognition;
- новые knowledge packages, calculators и post-release repository cleanup.

Эти направления находятся только в trigger-gated tasks `80-101` и их буквенных подзадачах после release gate `79`. В release
UI нельзя показывать фиктивные, locked или `coming soon` entry points для них.

## Trigger-gated post-release pool `80-101`

Tasks `80-101` и их буквенные подзадачи находятся в общей папке `codex-backlog/tasks/`, но не становятся линейным
продолжением release sequence. Перед запуском читать:

1. `POST_RELEASE_PRIORITY_ORDER.md`;
2. `POST_RELEASE_DEPENDENCY_GRAPH.md`;
3. `POST_RELEASE_TRIGGER_DECISION_MATRIX.md`;
4. `POST_RELEASE_PRODUCT_REVIEW.md` для rationale и scope boundaries;
5. текущую конкретную executable task и, если указано, её umbrella.

Правила:

- номер задаёт предпочтительную последовательность, но не заменяет evidence, dependency или owner decision;
- допустимо выполнить более высокий номер раньше низкого, если его Trigger подтверждён;
- `90`, `92`, `94`, `95`, `99`, `100` отдельно не реализовывать — запускать только дочернюю task;
- umbrella не получает отдельную сессию или commit и считается закрытой после завершения всех
  owner-approved дочерних tasks либо фиксации `Defer/No-Go` для остальных;
- downstream task не запускается автоматически после upstream commit;
- `Defer/No-Go` является допустимым завершением discovery gate и не создаёт implementation diff;
- новые внешние provider terms, pricing, platform policies и official constraints проверять заново
  на момент выполнения;
- UI implementation tasks `80+` используют текущие `ACTIVE_DESIGN_SOURCE.md`,
  `docs/design/design-direction-v2.1.md`, `docs/design/component-principles-v2.md`, общий
  Mobile Web/TMA contract и owner visual checkpoint на тех же основаниях, что release tasks;
- umbrella не разрешает смешивать дочерние tasks в одном commit.

## Product core

Первый релиз оптимизирует связный цикл:

```text
понять план на сегодня
-> быстро выполнить тренировку
-> быстро записать питание
-> увидеть фактическую динамику
-> при необходимости работать с тренером
```

- Today показывает одно главное действие и компактный недельный контекст, но не превращается в notification feed.
- Workout logging по умолчанию остаётся простым: вес, повторы, завершение подхода. RIR, set type и supersets раскрываются дополнительно.
- Active workout должен переживать ожидаемые сетевые сбои без потери подтверждённых действий.
- Nutrition prioritizes recent/favorites/templates/quick add и различает полный, неполный, отсутствующий и осознанно не заполненный день.
- Weekly review и adaptive calorie proposal являются одним пользовательским процессом; изменение цели требует явного подтверждения.
- Progress, nutrition reports и downloadable report являются одной информационной архитектурой, а не конкурирующими верхнеуровневыми разделами.
- Нет social feed, friends, followers, ratings, trainer marketplace, generic messenger, video calls, GPS tracks или универсального readiness score.

## Public knowledge и SEO

- Полная база знаний живёт на Public Web.
- TMA не содержит самостоятельной библиотеки, article index, long-form reader или navigation entry на `/knowledge`.
- В TMA допустимы короткие контекстные объяснения, `Что это?`, техника упражнения и переход на public source только из уместного контекста.
- Public content people-first, reviewed, source-linked и не содержит диагнозов, лечения, спортивной фармакологии или гарантированных результатов.
- Draft/private/user-specific pages не индексируются.
- Sitemap содержит только canonical published URLs.
- Structured data соответствует видимому содержимому; запрещены fake ratings, reviews, offers и authors.
- Не создавать doorway/thin/programmatic pages и не публиковать массовый low-value generated content.
- Изменение public URL требует redirect/canonical review.

## Auth и account capabilities

```text
Authenticated Account
├── Personal capabilities
├── Trainer capability - включается пользователем напрямую
└── Root Admin - только server-configured owner/break-glass
```

- Personal capabilities доступны каждому authenticated account.
- Trainer mode включается из Profile/Settings сразу, без заявки, очереди, беты, ручной модерации, документов или обещания проверки квалификации.
- Trainer capability additive: тренер сохраняет все личные возможности и отдельно получает client workspace.
- Не создавать self trainer-client relationship ради личных данных тренера.
- При работе с клиентом имя и контекст клиента постоянно видимы; опасные действия явно называют клиента.
- Client data доступны только по действующей связи и разрешённому scope.
- Root Admin определяется server-side (`ADMIN_TELEGRAM_USER_IDS` или актуальный эквивалент), не создаётся и не назначается через UI/API/БД.
- До релиза нет delegated admins, support_admin/super_admin hierarchy и управления администраторами.
- Admin и Trainer независимы: Root не получает Trainer автоматически, Trainer не получает Admin.
- Frontend visibility никогда не является security boundary.

## Authentication invariants

- Один internal account может иметь несколько verified identities.
- Required browser providers: Telegram, Google, Яндекс, VK ID. Existing Apple сохраняется optional, если корректен.
- Email/password остаётся feature-flagged и не включается скрыто.
- Valid TMA launch использует signed `initData` и не показывает второй browser login.
- Canonical browser auth entry - `/login`.
- Никакого silent merge по email или автоматического переноса identity другого account.
- `next` только allowlisted internal path; open redirect запрещён.
- Provider credentials только server-side; refresh token не хранится в localStorage.
- Root authority нельзя перенести через account linking.

## Mobile/TMA-first delivery gate

Для Personal и client-facing Trainer flows смартфон является основной средой использования. Каждый pending feature task обязан закрывать свой mobile/TMA acceptance сразу, а не оставлять очевидные regressions до task `72`.

Минимум:

- `360x800`, `390x844`, `430x932`, touch и `hover: none`;
- no horizontal overflow;
- практически удобные touch targets;
- keyboard не перекрывает active field, primary action и recovery;
- fixed/sticky UI учитывает safe area/content safe area;
- light/dark, loading/error/offline/long-content/reduced-motion;
- recoverable state переживает reload/background/temporary network failure, если это релевантно;
- feature-specific scenario добавлен или подтверждён в continuous mobile/TMA smoke task `50A`;
- real Telegram client verification заявляется только если фактически выполнена.

Coach/Admin сложные рабочие пространства могут быть desktop-first. Это должно быть явно указано в task; mobile smoke остаётся обязательным, а Admin не появляется в TMA без отдельного решения.

## TMA product contract

TMA оптимизирован для быстрых мобильных действий:

- открыть Today;
- начать/продолжить/завершить тренировку;
- отметить подходы и отдых;
- быстро записать питание;
- посмотреть краткий Progress/итог;
- открыть технику упражнения;
- перейти к профилю и необходимым настройкам.

Не добавлять в TMA:

- отдельную базу знаний;
- длинное чтение статей как основной сценарий;
- дублирующий Telegram-only frontend;
- отдельную Telegram product palette;
- platform controls, дублирующие понятные shared controls без UX-причины.

## Demo Mode

- Demo использует ровно подготовленные безопасные сценарии из tasks `68-69`.
- Demo - отдельное временное application state, не общий database demo-user.
- Fixtures не содержат production/user data.
- Demo edits не импортируются в реальный аккаунт.
- Invitations, account linking, product notifications, Admin actions и writes к реальным пользователям блокируются server-side.
- Demo использует тот же UI и не становится вторым приложением.

## Data confidence и fitness safety

- Не делать сильных выводов из редких данных и не изобретать magic score.
- Anthropometry сравнивает пользователя прежде всего с собой; окружность не объявляется размером отдельной мышцы.
- Не интерполировать отсутствующие замеры и не считать пропущенное питание нулём.
- Strength volume и cardio metrics не смешиваются.
- Program selection, progression, workout adaptation, analytics и calorie calibration детерминированы и объяснимы.
- Не добавлять diagnosis/treatment, sports pharmacology, body-photo analysis или autonomous program/nutrition changes.

## Privacy и безопасность

- Все endpoint'ы соблюдают current auth/RBAC/ownership.
- Не доверять user identity или target user id из frontend, если контекст определяется серверной сессией.
- Не логировать secrets, tokens, Telegram init data, полные private notes, food contents, exact measurements или trainer comments без отдельной доказанной необходимости.
- Не показывать stack traces и raw upstream errors.
- Не ослаблять TLS verification и не использовать unsafe HTML rendering.
- Export/delete/report links не раскрывают чужие данные и имеют ограниченный lifecycle.

## Миграции и данные

- Использовать существующий Alembic/data migration mechanism.
- Не удалять пользовательские данные и не генерировать выдуманный backfill без прямого требования.
- Исторические nutrition targets имеют период действия; отчёты используют цель, действовавшую в конкретную дату.
- Индексы добавляются только под реальный query pattern.
- File/artifact generation ограничена по размеру и времени, хранение временное и документированное.

## UX и Design V2

Целевое направление:

```text
premium sport-tech
warm neutral / graphite / lime
strong hierarchy
one primary action
fewer nested cards
mobile-first interaction
purposeful motion
```

- Default UI понятен новичку; профессиональные детали раскрываются постепенно.
- Не передавать смысл только цветом.
- Поддерживать keyboard, focus, labels, contrast и `prefers-reduced-motion`.
- Loading, empty, partial, error, offline и long-data states являются частью acceptance criteria.
- Не добавлять локальные palette/card/button systems поверх shared Design V2.

## UI consistency contract

Для любой pending client-facing UI task действуют эти правила независимо от того, загружен ли `$product-designer` или `$ui-audit`:

- active design source, shared design tokens и существующие primitives/components являются первым source of truth;
- одинаковый **semantic** control/pattern должен использовать тот же shared component и именованный variant/size/state, если нет явной UX/responsive/platform причины отличаться;
- не создавать локальный button/input/card/badge/tab/dialog/navigation primitive, если существующий shared primitive можно разумно переиспользовать или минимально расширить;
- colors, typography, spacing, radii, borders, shadows, icon sizes и interaction states брать из активной системы, а не создавать экранные мини-системы;
- raw values допустимы для действительно уникальной геометрии, но не должны дублировать уже существующий token или создавать случайное расхождение повторяющегося паттерна;
- повторяющийся UI pattern должен иметь один поддерживаемый source of truth; при этом не абстрагировать семантически разные элементы только из-за внешнего сходства;
- Mobile Web и TMA используют те же visual/component primitives; platform-specific safe area, keyboard, BackButton, haptics и chrome не являются основанием для отдельного visual system;
- Personal/client-facing composition проектируется и проверяется mobile-first; desktop может иметь другую композицию, но не другой набор случайных primitives;
- новая feature-task проверяет consistency только изменённой поверхности и непосредственных usages shared component - **не запускает новый product-wide UI audit**;
- явная consistency regression текущего diff считается обычным defect текущей task; severity определяется реальным impact и acceptance criteria, а не автоматически повышается до `HIGH`.

Dedicated product-wide consistency audit после смены правил/дизайн-системы выполняется task `49B1`. После её закрытия будущие задачи обязаны сохранять baseline, а не повторять этот аудит.

## Plain-language contract

Primary labels:

| Internal term   | User-facing Russian                           |
| --------------- | --------------------------------------------- |
| RIR             | Повторы в запасе                              |
| working set     | Рабочий подход                                |
| warm-up set     | Разминочный подход                            |
| drop set        | Дроп-сет - объяснить при первом использовании |
| superset        | Суперсет - два упражнения подряд              |
| adherence       | Соблюдение плана                              |
| deload          | Облегчённая неделя                            |
| progression     | Увеличение нагрузки                           |
| data confidence | Достаточно ли данных для вывода               |

Не показывать raw internal English values только потому, что они существуют в коде.

## Проверки и Git

### Git traceability contract

Каждая executable backlog task обязана сохранять свой task ID по всему Git lifecycle. Номер GitHub
PR не заменяет task ID.

Для task-файла вида `76A-...md` использовать:

- branch: `task/76A-<short-kebab-description>`;
- commit: `<type>: [Task 76A] <краткое описание>`;
- PR title: `[Task 76A] <краткое описание>`.

Допустимые примеры:

```text
task/76A-destructive-pre-release-testing
test: [Task 76A] add destructive pre-release scenarios
fix: [Task 76A] prevent mobile keyboard overlap
[Task 76A] Destructive pre-release testing
```

Правила:

- task ID брать из текущего executable task-файла и сохранять без изменения регистра/суффикса;
- один логический task не смешивать в commit/PR с другим task ID;
- при нескольких commits внутри разрешённого lifecycle каждый commit текущей task содержит тот же
  `[Task <ID>]`;
- task ID не опускать в squash/merge title, release PR title и других tracked Git-событиях,
  представляющих реализацию конкретной backlog task;
- для merge/release flow предпочитать PR title как итоговый merge commit title, чтобы Actions и
  история Git сохраняли `[Task <ID>]`;
- GitHub Actions run name должен наследовать или явно отображать task-aware commit/PR title; не
  заменять task ID только номером workflow run или GitHub PR;
- служебные изменения, которые действительно выполняются вне backlog task, могут использовать
  обычный Conventional Commit без фиктивного task ID, например
  `ci: normalize protected master release flow` или `chore: update dependencies`;
- если служебное изменение фактически входит в scope текущей backlog task, task ID обязателен:
  `ci: [Task 76A] normalize release checks`;
- temporary/recovery branch, созданная не для отдельной executable task, не обязана получать
  искусственный task ID, но не должна использоваться как способ потерять traceability основной task.

После task:

1. Запустить только связанные unit/API/component/e2e/typecheck/lint/build проверки по `AGENTS.md`.
2. Не заявлять проверку, если она фактически не запускалась.
3. Проверить `git diff`, migrations и config changes.
4. Исправить все `BLOCKER/HIGH` текущего scope; `MEDIUM/LOW/NIT/OUT_OF_SCOPE` не использовать как основание расширить task.
5. После blocking fix повторить только affected checks/recheck, а не полный audit.
6. Не запускать полный suite автоматически, если его не требует task/доказанный риск.
7. Синхронизировать все новые/изменённые `MEDIUM/LOW` в `codex-backlog/bugs/FINDINGS.md` и
   проверить актуальность их route/status.
8. Создать один логический commit при tracked changes, даже если остались документированные non-blocking findings.
9. Перед commit проверить соответствие branch/commit/PR naming правилам `Git traceability contract`.
10. Для read-only audit без production changes всё равно commit-ить изменение реестра, если task
    обнаружила новый `MEDIUM/LOW`; без findings и tracked changes commit не создавать.

Финальный отчёт содержит: reused, changed, key files, migrations/config, exact checks,
limitations/follow-ups, затронутые registry IDs/statuses, task ID и commit hash.

## Beginner release acceptance

Новичок без внешнего поиска терминов способен пройти:

```text
registration
-> onboarding
-> choose program
-> complete workout
-> log food
-> add measurement
-> understand Progress
```

Тренер способен напрямую включить Trainer mode, пригласить тестового клиента, назначить программу, увидеть выполнение и оставить контекстный комментарий.

## Scope freeze

После task `79` до решения о релизе добавляются только исправления:

- security/privacy;
- data loss/corruption;
- broken core journey;
- legal/release blocker;
- severe accessibility/performance regression.

Все остальные идеи попадают в post-release backlog и приоритизируются по фактическому поведению и обратной связи пользователей.

## Выполненные tasks и новые skills

Tasks `00-55` не выполнять повторно из-за обновления `.agents`, новых skills или последующего design exploration. Поздняя task `76` остаётся release-stage retrospective audit. Реальные usability sessions — task `77`; production readiness — task `78`; final go/no-go — task `79`. Новый skill сам по себе не разрешает refactor без прямого требования текущей task или доказанного blocking defect.
