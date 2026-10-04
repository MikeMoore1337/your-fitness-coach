# Your Fitness Coach - backlog первого публичного релиза v17

Backlog использует resource-aware lifecycle. В owner workspace завершённые задачи архивируются в
локальный ignored `tasks/done/` и остаются доступными владельцу для чтения.

## Текущее состояние

### Product v8 current governance — 2026-10-04

Каноническая roadmap — [Issue #683](https://github.com/MikeMoore1337/your-fitness-coach/issues/683).
Repository baseline: `6e231e068fe513cc5bf8ba2c24ff32c4e577ec18`.

```text
V8-01 / Task 684 -> COMPLETED / PRODUCTION VERIFIED
V8-00 / Task 124B -> REMOVED_FROM_ROADMAP / NO_GO BY OWNER
V8-R1 measurement boundedness -> separate optional reliability / BLOCKED_ON_EVIDENCE
V8-03 -> CANCELLED AS GENERIC PLACEHOLDER
CURRENT_EXECUTABLE_PRODUCT_V8_TASK -> NONE after bounded backlog review
```

Task `124B` is preserved as historical provenance only. It is not an evidence gate, dependency,
blocker or automatic task; synthetic/demo evidence remains distinct from real-user evidence, but
its absence does not block Product v8. Controller refactor remains `SEPARATE_INFRA_WORKSTREAM /
DEFER`; video exercise technique evaluation remains `NO_GO / OUT_OF_SCOPE`.

- tasks `00-80`, включая буквенные подзадачи, `69B`, `73A` и `74A`, а также owner-selected tasks
  `103-106` подтверждены как завершённые;
- завершённые task-файлы перенесены в локальный owner-only `tasks/done/` без переименования;
- `DESIGN_V2_1` с owner-approved bounded Pulse pilot остаётся current production baseline;
- task `77` закрыта по explicit owner acceptance отсутствия real-user sessions и residual risk;
- task `78` завершила production operational readiness после owner approval и подтверждения
  внешних operational controls;
- task `79` завершила final release gate без deployment, task `80` завершила approved repository
  hygiene/privacy cleanup; обе архивированы после owner approval;
- owner-selected task `112` завершена и архивирована; revision `194cf036` развёрнута после explicit
  owner approval через constrained-host `single-slot` fallback с bounded downtime и verdict
  `active`, без заявления production blue/green zero observed downtime;
- task `113` завершила branch normalization и automatic release eligibility contract;
- task `114` назначена current, но её Trigger/реализация не запускались;
- owner-selected tasks `107-111` созданы вне основной очереди и не являются current.

## Текущая задача

```text
CURRENT_EXECUTABLE_PRODUCT_V8_TASK = NONE
```

Не выбирать и не запускать старую UX-reset sequence автоматически. Направления `81/82/83/84/85`,
`86/86A`, bounded AI, imports, Progress, trainer and nutrition improvements были проверены и уже
реализованы либо имеют собственный gate; подробная selection table находится в
`POST_RELEASE_PRODUCT_REVIEW.md`.

Не запускать заново `00-80`, `74A`, `103-106` и `113`. Назначение `114` не запускает её реализацию, а
создание owner-selected tasks `107-111` не разрешает их implementation, external actions или
юридически значимые owner decisions. Stage C task 108 реализует пользовательское соглашение,
отдельное согласие на обработку ПД и technical auth-gate только после legal/owner checkpoint;
до commit обязателен screenshot approval Web/Mobile Web/mocked TMA.

## Design alternatives flow

```text
49A  targeted brief/current-state delta [done]
49B  exactly three cross-surface directions + renders [done]
49B1 current Design V2 UI consistency + mobile-first normalization [done]
49C  compare normalized V2/A/B/C + owner selection [done]

KEEP_V2_UNCHANGED
  -> skip 49D-49F
  -> 49G closure

V2.1 / A / B / C / explicit hybrid
  -> 49D final responsive specification
  -> owner approval
  -> 49E production-realistic pilot
  -> owner manual test
  -> 49F final owner approval
  -> 49G conditional rollout + backlog alignment

49G -> 50A mobile/TMA quality foundation [done]
50-74A feature/release/hardening tasks [done]
75 performance/motion hardening [COMPLETED]
75A design/UX/UI/motion Rethink audit [COMPLETED]
  -> KEEP: continue to 76
  -> EVOLVE: bounded remediation
  -> RETHINK [SELECTED]: 75B isolated exploration + owner selection
75B product-wide visual + motion directions [COMPLETED, SELECT_DIRECTION_PULSE]
  -> 75C bounded production pilot [COMPLETED]
  -> 76 audit [COMPLETED] -> 76A adversarial gate [COMPLETED]
  -> 77 real-user gate [CLOSED BY OWNER ACCEPTED RESIDUAL RISK]
  -> 78 production readiness [COMPLETED] -> 79 final release gate [COMPLETED, NO DEPLOY]
  -> 80 repository hygiene/privacy cleanup [COMPLETED]
  -> 113 branch normalization [COMPLETED]
  -> 114 nutrition/barcode P0 regression [CURRENT, NOT STARTED]
  -> 115A -> OWNER APPROVAL -> 116..123 -> 81 -> 82 -> 84 -> 124A
  -> OWNER RELEASE APPROVAL -> 124B -> conditional 124C [HISTORICAL; 124B REMOVED / 124C CANCELLED]
103-106 owner-selected Telegram flow/Landing tasks [done]
107 Scheduled regression + private Allure reports [OWNER-SELECTED PENDING; NOT CURRENT]
108 Russian law compliance audit + continuous legal gate [OWNER-SELECTED PENDING; NOT CURRENT]
109 Landing value proposition + conversion story [OWNER-SELECTED PENDING; NOT CURRENT]
110 User custom avatar upload desktop/mobile [OWNER-SELECTED PENDING; NOT CURRENT]
111 Progress bento dashboard + 1/7/30/90/365/custom periods [OWNER-SELECTED PENDING; NOT CURRENT]
```

## Что изменено в v17

- Tasks `79-80` завершены и архивированы после owner approval; deployment не выполнялся.
- Permanent development branch — `dev`; protected `master` остаётся production source.
- Canonical lifecycle различает `AUTO_RELEASE_ELIGIBLE` и owner/human-gated tasks.
- UX-reset critical path начинается с Task `114`; Task `81` перенесена после `123`.
- Добавлена owner-selected pending task `107` для scheduled regression и закрытых Allure-отчётов
  на `allure.your-fitness-coach.ru` с явным access/retention owner contract.
- Добавлена owner-selected pending task `108` для полного аудита соответствия законодательству РФ,
  покрытия всех существующих tasks и непрерывного gate для ещё не созданных будущих задач.
- Добавлены owner-selected pending tasks `109-111`: factual Landing offer, безопасный custom avatar
  на desktop/mobile и YFC bento-представление Progress с периодами `1/7/30/90/365/custom`.
- Resource-aware review policy `BLOCKER/HIGH only` сохранена; `MEDIUM/LOW` синхронизируются в
  `bugs/FINDINGS.md`.

Подробности: `TASK_EXECUTION_LIFECYCLE.md`, `SKILL_ASSIGNMENT_MATRIX.md`, `ACTIVE_DESIGN_SOURCE.md`.
