# Dependency graph — post-release trigger-gated pool

## Canonical Product v8 completed graph — 2026-10-04

Roadmap: [GitHub Issue #683](https://github.com/MikeMoore1337/your-fitness-coach/issues/683).
Closeout source baseline `e8d9228b259e35740ff68048f2772482fb4e8945` (governance sync PR #691 merge); V8-01 / Task 684 remains
**COMPLETED / PRODUCTION VERIFIED**. Dependency maintenance PRs `#589` and `#689` are separate
lockfile-only workstreams and are not Product v8 nodes.

```text
Product v8
  -> COMPLETED

V8-01 / Task 684
  -> COMPLETED / PRODUCTION VERIFIED

V8-00 / Task 124B
  -> REMOVED_FROM_ROADMAP / NO_GO BY OWNER
  -> not a gate, dependency or blocker
  -> no auto-start and no V8-03 generation

V8-R1 / measurement reporting boundedness
  -> BLOCKED_ON_EVIDENCE
  -> separate optional reliability task
  -> not a Product v8 blocker

V8-03
  -> CANCELLED AS GENERIC PLACEHOLDER
  -> do not create without a concrete newly specified problem

CURRENT_EXECUTABLE_PRODUCT_V8_TASK
  -> NONE
  -> Product v8 is closed; no next Product v8 task is selected
```

Synthetic/demo evidence still cannot be described as real-user evidence, but missing real-user
validation is not a Product v8 blocker. The review found no unimplemented, independently
executable product node: the requested daily-workflow, trainer, progress, nutrition, knowledge,
PWA/Web Push, import and bounded AI directions are already implemented. Remaining candidates keep
their own gates and are not silently attached to this graph. No V8-04+ placeholder is created.
Task `138` is `ALREADY_IMPLEMENTED` through
Task `364`/PR `#365`, not a v8 dependency. The historical UX-reset graph below is retained for
traceability and must not auto-start Task `119` or any other old product task. Controller refactor
is `SEPARATE_INFRA_WORKSTREAM / DEFER`. Exercise video technique evaluation is `NO_GO` /
`OUT_OF_SCOPE`. SEO `#320-#324` remains a separate evidence-gated roadmap; `92B`, `95A` and
`95B` remain separate own-gate workstreams. No parked node transfers to a future product version
automatically.

## Исторический UX-reset critical path (provenance only; not canonical Product v8)

```text
113 -> 113A STABILIZATION -> production smoke -> OWNER VERIFICATION -> 114 -> 115A -> OWNER APPROVAL
 -> 116 -> 117 -> 118 -> 119
 -> 120A -> 120B -> 120C -> 120D
 -> 121 -> 122 -> 123
 -> 81 -> 82 -> 84 -> 124A
 -> OWNER RELEASE APPROVAL
 -> dev -> master -> production deployment
 -> 124B -> 124C only if BLOCKER/HIGH [HISTORICAL ONLY]
```

- `81` зависит от `123`; Today использует compact quick action, detail/history — Nutrition.
- `82` зависит от `81` и semantic system `123`; check-in compact, insights/history — Progress.
- `84` зависит от `82` и `122`; settings compact/default-off, Today только actionable state.
- `85 -> 121`, `110 -> 122`, `111 -> 123`; эти tasks вне critical path `124A`, пока владелец не
  включил их в release candidate.
- `115B` отсутствует. The old `124B` real-user validation link is preserved here only as
  historical provenance; owner decision removed Task `124B` from Product v8, so it is not an
  executable dependency and does not create `124C`.

```text
release 79
  -> 80 Repository hygiene/security/README
  -> 81 Hydration tracking
  -> 82 Daily sleep/mood
  -> 83 Authenticated trainer report handoff
  -> 84 Contextual reminder templates
  -> 85 Knowledge: GI/КБЖУ/BMI/HR zones
  -> 86 PWA
  -> 86A Web Push notifications foundation (after `86`, separate owner launch)
  -> 87 AI decision/privacy/provider
       -> 88 Grounded core
       -> 89 Read-only personal tools
       -> 90 umbrella -> 90A UI/internal evals -> 90B Real-user beta decision
       -> 91 AI period insights
       -> 92 umbrella
            -> 92A Long-term memory (independent Trigger)
            -> 92B Multiprovider routing (independent Trigger)
  -> 93 umbrella
       -> 93A Deterministic XLSX/CSV template import without AI
            -> safe extraction -> neutral draft -> deterministic candidates
            -> manual ambiguity resolution -> explicit confirmation -> editable draft
       -> observed unsupported/manual-resolution gap + compatible AI route
            -> 93B AI-assisted heterogeneous XLSX/CSV/TXT/DOCX
                 -> deterministic extraction -> source-grounded AI proposal
                 -> deterministic candidates -> bounded AI reranking/advisory
                 -> same manual resolution/confirmation/fallback from 93A
  -> 94 umbrella -> 94A Food-photo feasibility/evals
       -> owner Go/Narrow Go -> 94B Confirmed assisted entry
  -> 95 umbrella -> 95A Server PDF/authenticated download -> 95B Share/Telegram delivery
  -> 96 Wearables discovery
  -> 97 Delegated admins
  -> 98 Native feasibility
  -> 99 umbrella -> 99A Commercial/provider decision
       -> 99B Billing/entitlement backend -> 99C Checkout/account rollout readiness
  -> 100 umbrella -> 100A Core product localization -> 100B Public Web/SEO/content
  -> 101 Private progress photos without AI/body analysis

Report 67 + notifications 64 + active coach relationship
  -> 83 Authenticated trainer report handoff

Report delivery 95A -> 95B External share/Telegram delivery
  (does not replace task 83 in-product handoff)

Telegram Core release task 04
  -> 103 News ingestion -> 104 Moderated publishing -> 104A Exact publication composition
  -> 105 Weekly opt-in digest [COMPLETED]

Current Landing + canonical `@your_fitness_coach_bot` Main Mini App + confirmed `@your_fitness_news`
  -> 106 Landing Telegram app/support/news discoverability [COMPLETED]

Current GitHub Actions CI + Pytest/Vitest/Playwright harness + owner access/retention decisions
  -> 107 Scheduled regression + private Allure reports [OWNER-SELECTED, PENDING; NOT CURRENT]

Current code/data/infrastructure + all backlog families + owner facts + product-lawyer/ru-legal-risk + RF counsel
  -> 108 Russian law compliance audit + continuous future-task gate [OWNER-SELECTED, PENDING; NOT CURRENT]

Current factual Landing + DESIGN_V2_1 + optional approved public security claims baseline from 108
  -> 109 Landing value proposition + conversion story [OWNER-SELECTED, PENDING; NOT CURRENT]

Current AppShell avatar fallback + provider photo + private media/export/delete lifecycle
  -> 110 User custom avatar upload desktop/mobile [OWNER-SELECTED, PENDING; NOT CURRENT]

Current Progress/report services + TimeSeriesChart/DataConfidence + DESIGN_V2_1/Pulse
  -> 111 Progress bento dashboard + 1/7/30/90/365/custom periods [OWNER-SELECTED, PENDING; NOT CURRENT]

Current Git branch/worktree policy + CI + dev/master Rulesets + observed concurrent write/push race
  -> 127 Task branches/worktrees + serialized dev integration queue [OWNER-SELECTED, P0, PENDING]
       -> owner launch
       -> isolated Task 127 branch/worktree
       -> controller + atomic leases + task PR -> dev checks
       -> one-at-a-time dev integration + release freeze + dev update provenance
       -> owner checkpoint for live Ruleset/merge-queue/sync-actor changes
       -> read-back verification + synthetic two-task rehearsal

Task `127` не зависит от product Task `119` и не меняет product dependency graph. До её завершения
параллельные write tasks запрещены; действует прежний single-writer последовательный режим.

## Nutrition Label OCR deferred branch

Task 128G
  -> implementation / merge / production deployment COMPLETE
  -> RapidOCR activation + corpus validation COMPLETE
  -> HUMAN_EVIDENCE FAIL: 503 local_ocr_timeout on current production host
  -> production-quality GO NO; exposure disabled
  -> server migration + explicit owner trigger
       -> Task 128H performance validation
       -> bounded optimization if proven
       -> rollout + same-photo HUMAN_EVIDENCE

Task 128G больше не является dependency для higher-priority work. Обычные Nutrition/Food,
manual и barcode flows также не зависят от 128H. Только future tasks, которым нужен
production-ready nutrition-label scanning, сохраняют hard dependency на Task 128H.

Exercise catalog expansion 120A -> 120B -> 120C -> 120D
  + successful AI beta foundation 87 -> 88 -> 89 -> 90A -> 90B
  -> 126 umbrella
       -> 126A Equipment-camera Vision feasibility/evals
            -> owner GO/NARROW GO
                 -> 126B Server-side Vision + canonical equipment -> existing exercise matching
                      -> 126C Mobile Web/TMA camera + existing add-to-program flow

Optional reuse only: 92B capability routing, 94A Vision eval contracts, 94B image-ingress/camera primitives.
Tasks 91/92A/92B/94A/94B are not hard dependencies of 126A.
```

Import umbrella `93` сохраняет один pipeline, но разделяет independent delivery gates. `93A` даёт
deterministic XLSX/CSV template import без AI-кластера. Условная `93B` переиспользует тот же draft,
matching, preview и confirmed write только после evidence `93A` и compatible provider/privacy/cost
decision. `92A` memory и `92B` multiprovider не являются обязательными зависимостями.

Положение food-photo после AI закреплено и номерами, и графом. Все стрелки дополнительно требуют
evidence Trigger и owner decision. Umbrella-файлы не являются implementation tasks и не разрешают
смешивать дочерние tasks в одном commit.
