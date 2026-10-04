# Порядок выполнения release backlog v50

## Completed

`00-80`, включая `69B`, `73A`, `74A` и предшествующие буквенные подзадачи, а также
owner-selected Telegram tasks `103-106`, tasks `109/112`, owner-approved UX reset gate `115A` и
UX-reset implementation tasks `116-118`.
Task-файлы находятся в локальном owner-only `tasks/done/`.

## Product v8 completed closeout — 2026-10-04

Closeout source baseline: `e8d9228b259e35740ff68048f2772482fb4e8945` (governance sync PR #691 merge); roadmap: Issue `#683`.

```text
Product v8 -> COMPLETED
V8-01 / Task 684 -> COMPLETED / PRODUCTION VERIFIED
V8-00 / Task 124B -> REMOVED_FROM_ROADMAP / NO_GO BY OWNER
V8-R1 measurement boundedness -> separate optional reliability / BLOCKED_ON_EVIDENCE
V8-03 -> CANCELLED AS GENERIC PLACEHOLDER
CURRENT_EXECUTABLE_PRODUCT_V8_TASK -> NONE / Product v8 closed
```

Hydration, Sleep/Mood, trainer report handoff, reminders, knowledge, PWA/Web Push, bounded AI,
imports, Progress, trainer and nutrition directions were checked against current code/history and
are already implemented. The remaining report-delivery, SEO/product-handoff, provider-routing and
measurement options retain independent gates. No new Product v8 Issue or implementation task is
selected by this reconciliation. `124B` is historical provenance only and is not a gate or
dependency; synthetic/demo evidence remains non-real-user evidence without blocking closeout.
Parked or gated workstreams do not transfer automatically to a future product version.

## Historical/stale current sequence

The following sequence is retained for provenance and is not an executable current order. Task
`119` is not the next Product v8 task; the old `124B -> 124C` tail was removed by owner decision.

```text
113A Owner UX Stabilization [COMPLETED, OWNER ACCEPTED]
  -> 114 Nutrition search/barcode production regression [COMPLETED, OWNER APPROVED, RELEASE AUTHORIZED]
  -> 115A UX audit + IA + compactness/disclosure prototype/spec [COMPLETED, OWNER APPROVED: COMMAND STACK]
  -> 116 [COMPLETED] -> 117 [COMPLETED] -> 118 [COMPLETED]
  -> 119 Type-aware workout logging [NEXT PRODUCT TASK, NOT STARTED]
```

Tasks `75C`, `76` и `76A` завершены после применимых owner checkpoints. Task `76A` получила
adversarial verdict `PASS`, закрыла все `BLOCKER/HIGH` и архивирована. В task `77` реальные сессии
не проводились; владелец явно принял отсутствие real-user validation и residual risk, после чего
task архивирована. Task `78` завершила production readiness после owner approval и подтверждения
external controls. Tasks `79-80` завершены и архивированы после owner approval. History rewrite
`master` запустил намеренный automatic production workflow; владелец подтвердил это поведение как
feature, а точный trigger contract закреплён в обязательной документации. Task `113` завершила
branch normalization. Task `113A` выпущена в production, принята владельцем и архивирована;
production baseline остаётся `DESIGN_V2_1`. Task `114` завершена и архивирована после owner
approval. Task `115A` завершила isolated UX audit/prototype gate, владелец выбрал `Command Stack`,
разрешил commit, и task архивирована. Tasks `116-118` завершены и архивированы. Task `119`
обозначена следующей product task, но её lifecycle не начат.

Conditional release sequence:

```text
75 [COMPLETED] -> 75A Rethink audit [COMPLETED] -> START_RETHINK_EXPLORATION
  KEEP -> 76 [COMPLETED] -> 76A [COMPLETED] -> 77 [COMPLETED] -> 78 [COMPLETED] -> 79 [COMPLETED]
  EVOLVE -> bounded remediation -> 76 [COMPLETED]
  RETHINK -> 75B exploration [COMPLETED] -> 75C pilot [COMPLETED] -> 76 [COMPLETED]
```

Release/smoke Task `113A` завершены, а точная owner-команда
`Stabilization принята. Можно переходить к Task 114.` получена `2026-08-30`. Tasks `114`, `115A`
и `116-118` затем запускались отдельными командами, завершены и архивированы; Task `119` не
запускается автоматически.
Trigger-gated tasks сохраняют собственные gates. Никакая task не запускает следующую автоматически.

## Текущий UX-reset cycle

Canonical owner-driven порядок:

```text
113 [COMPLETED] -> 113A [COMPLETED, OWNER ACCEPTED] -> 114 [COMPLETED, OWNER APPROVED]
-> 115A [COMPLETED, OWNER APPROVED: COMMAND STACK]
-> 116 [COMPLETED] -> 117 [COMPLETED] -> 118 [COMPLETED]
-> 119 [NEXT PRODUCT TASK, NOT STARTED] -> 120A -> 120B -> 120C -> 120D
-> 121 -> 122 -> 123 -> 81 -> 82 -> 84 -> 124A
-> OWNER RELEASE APPROVAL -> dev -> master -> production deployment
-> 124B -> 124C only if BLOCKER/HIGH
```

Task `115B` отсутствует. Реальные пользовательские сессии выполняются на deployed production build
в Task `124B`, а не блокируют implementation `116+`. Tasks `85`, `110`, `111` остаются вне critical
path и входят в `124A` только по отдельному owner решению. Каждая стрелка сохраняет Trigger,
dependency и owner gate своей task; следующая task автоматически не запускается.

Owner-selected task `106` завершена и архивирована после owner screenshot approval. Она не изменила
основную release-последовательность; после завершения `116-118` next/not-started product task — `119`.

Owner-selected task `107` создана для scheduled regression и закрытых Allure-отчётов на
`allure.your-fitness-coach.ru`. Она не является current, не меняет UX-reset critical path и требует
отдельного owner запуска плюс explicit approval перед DNS/Cloudflare/hosting actions.

Owner-selected task `108` создана для комплексного аудита соответствия законодательству РФ и
непрерывного legal-impact gate, охватывающего все текущие и любые будущие задачи. Она не является
current, не меняет UX-reset critical path и требует отдельного owner запуска через `product-lawyer` и
`$ru-legal-risk`; итоговый baseline/gate обязательно проверяет профильный российский юрист, а
`LEGAL_COUNSEL_REQUIRED` выделяет дополнительные спорные вопросы.

Owner-selected tasks `109-111` созданы вне основной очереди: `109` — factual Landing offer и
conversion story, `110` — private custom avatar desktop/mobile, `111` — Progress bento dashboard и
периоды `1/7/30/90/365/custom`. Task `109` завершена; `110/111` не меняют next `119` или UX-reset
critical path, не запускаются автоматически и требуют отдельных owner запусков; для UI до commit
действует screenshot approval.

Owner-selected umbrella `126` создана вне основной очереди для сценария `камера -> тренажёр ->
existing exercises -> добавить в программу`. Family не меняет next `119` или UX-reset critical path.
Её executable chain: `126A -> owner GO/NARROW GO -> 126B -> 126C`. Task `126A` не может начаться до
завершения `120D` и successful AI beta foundation `90B`. Tasks `91`, `92A`, `92B`, `94A`, `94B`
не являются hard dependencies; завершённые `92B/94A/94B` переиспользуются при совместимости.
Task family `125/125A/125B` про migration инфраструктуры также не является dependency `126`.

Owner-selected task `112` завершена и архивирована вне основной очереди. Она добавила проверяемый
current-stack zero-downtime deployment contract. После explicit owner approval production revision
`194cf036` успешно развёрнута через `single-slot` fallback с bounded downtime из-за фактической
capacity constrained VPS; это не доказательство production blue/green zero observed downtime.
Task `112` не изменяет текущий UX-reset cycle. Tasks `114`, `115A` и `116-118` завершены отдельно;
Task `119` не запускается автоматически.

Owner-selected Task `127` создана вне product sequence для перехода на
`1 task = 1 branch = 1 separate worktree`, integration-only `dev`, atomic session leases и одну
сериализованную очередь task PR merge в `dev`. Она не запускается автоматически и не меняет scope
Task `119`. До завершения Task `127` несколько параллельных write-сессий запрещены; допустим только
прежний строго последовательный single-writer режим.
