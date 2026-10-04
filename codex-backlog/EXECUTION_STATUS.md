# Execution status v53

## Product v8 current state — 2026-10-04

Канонический Product v8 roadmap: [GitHub Issue #683](https://github.com/MikeMoore1337/your-fitness-coach/issues/683).
Текущий repository baseline — `206058185dda7357582f088997b7522ab42765f0` на `master` и
`origin/master`; Product v8 implementation baseline остаётся production-verified после V8-01,
а dependency maintenance PR `#589` и replacement PR `#689` merged separately. Product v8
**RECONSTRUCTED / NO CURRENT EXECUTABLE TASK SELECTED**.

V8-01 / Task 684 — **COMPLETED / PRODUCTION VERIFIED**: Issue `#684` closed, PR `#686`
merged, product deployed SHA `bffaf336f350def789376ce7eb299705371188f3`. Для V8-01 не потребовались
env, migration, schema или provider changes. Post-merge/release и production smoke зелёные.
Later lockfile-only maintenance merges do not change this product verification result.

Product v8 current execution state:

```text
V8-01 / Task 684
  -> COMPLETED / PRODUCTION VERIFIED

V8-00 / Task 124B
  -> REMOVED_FROM_ROADMAP / NO_GO BY OWNER
  -> not an evidence gate
  -> not a dependency or Product v8 blocker
  -> must not auto-start or recreate V8-03

V8-R1 / measurement reporting boundedness
  -> BLOCKED_ON_EVIDENCE
  -> separate optional reliability task
  -> NOT a Product v8 blocker

V8-03
  -> CANCELLED AS GENERIC PLACEHOLDER
  -> do not create without a newly specified concrete problem

CURRENT_EXECUTABLE_PRODUCT_V8_TASK
  -> determined by the reconstructed v8 backlog selection
  -> NONE after the bounded 2026-10-04 review
```

Synthetic/demo evidence still cannot be represented as real-user evidence. Its absence is no
longer a blocker for Product v8. The bounded backlog review found no unimplemented, independently
executable product task: the requested hydration/wellbeing/trainer/reminder/knowledge/PWA/Web Push/
AI/import/progress/nutrition and trainer directions are already implemented in the current product;
remaining candidates retain their own evidence, provider, owner or infrastructure gates.
Controller refactor — `SEPARATE_INFRA_WORKSTREAM / DEFER`; exercise video technique evaluation —
`NO_GO / OUT_OF_SCOPE`.

Этот current-state block имеет приоритет над историческими owner-driven очередями ниже.

Historical audit reconciliation:

- Task `138` — `ALREADY_IMPLEMENTED`: security-gate/SkillSpector delivered through Task `364`
  and PR `#365`; это не dependency Product v8. Root task/link drift должен быть убран отдельной
  governance-синхронизацией, но не требует продуктовой реализации.
- Tasks `119`, `120A-D`, `120E`, `124A` и Product v7 tasks — уже закрытые фактические
  workstreams; старое утверждение о Task `119` как следующей незапущенной product task — stale.
- Task `124B` is preserved only as historical provenance and is
  `REMOVED_FROM_PRODUCT_V8 / NO_GO BY OWNER`; it is not a gate, dependency, blocker or auto-run
  candidate. Task `124C` is likewise not spawned by it; the old conditional remediation linkage
  is historical only.
- Nutrition label-scan finding `F-128G-01` остаётся отдельным deferred/flag-off workstream и
  не переносится в v8 без production-quality GO и owner trigger.
- SEO `#324` и зависимые `#320-#323` остаются `BLOCKED_ON_EVIDENCE`; SEO Growth Stage 2 и
  массовые programmatic pages не входят в v8.
- Optional, owner-selected и infrastructure workstreams (`107`, `108`, `110`, `111`, `127`,
  `138`, `269`, `388`, `403`, `415`, AI/SEO pools) не запускаются автоматически и не становятся
  Product v8 только из-за наличия в backlog. The bounded review separately recorded completed
  implementations and own-gated candidates in `POST_RELEASE_PRODUCT_REVIEW.md`.

## Historical backlog/provenance — owner-confirmed state on 2026-08-28

The following historical checklist is retained for provenance. It does not override the
Product v8 current-state block above and does not define an executable task or dependency.

- [x] tasks `00-73`, включая `69B` и предшествующие буквенные подзадачи, complete;
- [x] завершённые task-файлы перенесены в локальный owner-only `tasks/done/` и доступны владельцу
      для чтения;
- [x] `DESIGN_V2_1` — current production baseline, полностью пересматриваемый owner-approved
      Rethink task;
- [x] task `50A` создала continuous Mobile Web/TMA gate;
- [x] task `69A` заменила guided demo ограниченным Web-кабинетом и архивирована;
- [x] task `69B` унифицировала иконографику и data visualization и архивирована после owner approval;
- [x] task `70` завершена вне очереди и архивирована без включения изменений task `69B`;
- [x] task `71` завершена вне очереди и архивирована без включения изменений task `69B`;
- [x] task `72` завершила TMA platform hardening и архивирована после owner approval;
- [x] task `73` финализировала production Landing, public product hero и demo/privacy continuation и архивирована после owner approval;
- [x] task `73A` реализовала утверждённую premium strength marketing art-direction, прошла review/QA, получила owner approval и архивирована;
- [x] owner-selected task `103` реализовала безопасный news ingestion и owner-only editorial draft queue, прошла review/QA и архивирована после owner approval;
- [x] owner-selected task `104` реализовала тематические изображения, revision-bound модерацию и provisional staging publication pipeline, прошла review/QA и архивирована после owner approval;
- [x] owner-selected task `104A` реализовала exact Telegram HTML preview/channel parity, прошла review/QA, реальную staging-публикацию и архивирована после owner approval;
- [x] owner-selected task `105` реализовала отдельный default-off opt-in, owner-approved weekly digest и мгновенную изолированную отписку, прошла review/QA и архивирована после owner approval;
- [x] owner-selected task `106` добавила на Landing явный запуск Telegram Mini App и ссылку на
      публичный Telegram-канал о фитнесе и здоровье, прошла review/QA, получила owner screenshot
      approval и архивирована;
- [x] task `74A` внедрила product-wide semantic motion language и data-viz animation, прошла review/QA, получила owner approval и архивирована;
- [x] task `74` завершила cross-product responsive/accessibility/states hardening, прошла QA, получила owner screenshot approval и архивирована;
- [x] task `75` завершила UI performance и motion hardening, прошла independent review, получила
      owner screenshot approval и архивирована;
- [x] task `75A` завершила evidence-based Rethink-аудит design/UX/UI/motion, получила owner
      screenshot approval и решение `START_RETHINK_EXPLORATION`, синхронизировала findings и архивирована;
- [x] task `75B` завершила isolated exploration, bounded refinement и owner selection; владелец
      выбрал `SELECT_DIRECTION_PULSE` как четыре концепции поверх текущего UI, task архивирована;
- [x] task `75C` перенесла выбранные chart/dock/card-artwork/motion концепции поверх текущего UI без
      restyle, прошла review/QA, получила owner screenshot approval и архивирована;
- [x] task `76` завершила skill-aware retrospective release audit, закрыла все подтверждённые
      `BLOCKER/HIGH/MEDIUM`, синхронизировала findings и архивирована после owner screenshot approval;
- [x] task `76A` завершила pre-human adversarial negative/destructive testing gate с verdict `PASS`,
      закрыла все подтверждённые `BLOCKER/HIGH`, синхронизировала findings и архивирована после
      owner approval;
- [x] task `77` подготовила полный research packet, но реальные сессии не проводились; владелец явно
      принял отсутствие real-user validation и связанный residual risk, после чего task архивирована;
- [x] task `78` завершила production operational readiness: fail-closed config/deploy gates,
      audit retention, PostgreSQL migration/backup/restore drill, monitoring/rollback contract и
      production-like regression evidence; владелец подтвердил external controls и screenshot packet;
- [x] task `79` завершила final integrated release gate; владелец уточнил, что auto-deploy после
      green CI в `master` является намеренной функцией, а trigger contract закреплён в документации;
- [x] owner-approved task `80` завершила repository hygiene/privacy cleanup, README/config audit,
      private-path boundary и архивирована вместе с task `79`;
- [x] task `113-development-branch-normalization.md` завершила переход permanent development branch
      на `dev`, master-only release safeguards и canonical automatic release eligibility contract;
- [x] `113A-owner-ux-stabilization.md` — stabilization revision `17bee56c` выпущена в production,
      owner verification принята `2026-08-30`, task завершена и архивирована;
- [x] `114-nutrition-search-barcode-production-regression.md` — implementation, review и QA
      завершены; owner принял visual evidence и явно разрешил production release с risk acceptance
      отсутствующего real-device/TMA camera evidence; task архивирована, production release явно разрешён;
- [x] `115A-post-release-ux-audit-ia-prototype.md` завершила current-state audit, target IA,
      compactness/disclosure specs, три isolated prototype direction и plan для Task `124B`;
      владелец выбрал Direction A `Command Stack`, разрешил commit, task архивирована без
      production implementation/release;
- [x] tasks `116-core-navigation-today-quick-start.md`,
      `117-first-run-without-mandatory-onboarding.md` и
      `118-simple-training-program-flow.md` завершены и архивированы отдельными task lifecycle;
- [ ] **historical/stale sequence (superseded by Product v8 audit #683):** `119-type-aware-workout-logging.md`
      не является текущей next product task; её lifecycle требует отдельной команды владельца
      и не запускается автоматически;
- [ ] historical owner-driven sequence (superseded by Product v8 audit #683 and owner removal of
      Task `124B`):
      `114 -> 115A -> 116 -> 117 -> 118 [COMPLETED] -> 119..123 -> 81 -> 82 -> 84`
      `-> 124A -> owner release approval -> 124B -> conditional 124C`;
- [x] owner-selected task `106-landing-telegram-product-news-links.md` завершена вне основной
      очереди и не изменила порядок `78-101`.
- [ ] owner-selected task `107-scheduled-regression-private-allure-reports.md` создана вне основной
      очереди, не назначена current и требует отдельного owner запуска; DNS/Cloudflare/hosting
      actions остаются под дополнительным explicit approval.
- [ ] owner-selected task `108-russian-law-compliance-audit-continuous-gate.md` создана вне основной
      очереди, не назначена current и требует отдельного owner запуска через `product-lawyer` и
      `$ru-legal-risk`; итоговый baseline/gate обязательно проверяет профильный российский юрист,
      а `LEGAL_COUNSEL_REQUIRED` выделяет дополнительные спорные вопросы. После legal/owner
      checkpoint Stage C этой же task реализует versioned пользовательское соглашение, отдельное
      согласие на обработку ПД и server-side auth-gate для Web/TMA/Bot; до screenshot approval
      commit/archive запрещены. Запуск lifecycle, production activation и external legal actions
      не авторизованы созданием task.
- [x] owner-selected task `109-landing-value-proposition-conversion-story.md` завершена и
      архивирована вне основной очереди: factual оффер и conversion story не используют сравнения,
      fake proof или неподтверждённые claims; security/trust copy остаётся ограничена approved
      baseline task `108`.
- [ ] owner-selected task `110-user-custom-avatar-upload.md` создана вне основной очереди для
      private custom avatar на desktop/mobile с безопасной обработкой, export/delete и fallback
      `custom -> provider -> emoji`; migration/deploy требуют отдельного запуска/approval.
- [ ] owner-selected task `111-progress-bento-dashboard-periods.md` создана вне основной очереди для
      YFC bento-дашборда и периодов `1/7/30/90/365/custom`; визуальный референс не разрешает
      выдумывать hydration/steps/health score или новый data pipeline.
- [x] owner-selected task `112-zero-downtime-production-deployment.md` завершена и архивирована вне
      основной очереди: stable gateway, blue/green slots, online-migration fail-closed gate,
      old-asset overlap, single-owner worker/bot handoff, rollback и production-like drill прошли
      review/QA. После explicit owner approval revision `194cf036` развёрнута в production через
      resource-aware `single-slot` fallback с bounded downtime: deployment verdict `active`, все
      stages passed, public/API/SEO и ownership worker/bot подтверждены. Production blue/green
      zero-observed-downtime на этом constrained VPS не заявляется.

- [ ] owner-selected umbrella `126-equipment-camera-recognition-umbrella.md` создана вне основной
      очереди по прямому запросу владельца. Она не меняет current UX-reset path. `126A` заблокирована
      до завершения exercise catalog `120D` и successful AI beta foundation `90B`; после feasibility
      возможны только owner-approved `126B -> 126C`. Tasks `91/92A/92B/94A/94B` не hard dependencies,
      но compatible artifacts `92B/94A/94B` переиспользуются, если к тому моменту существуют.
- [ ] owner-selected task `127-task-branches-worktrees-serialized-dev-integration.md` выполняется в
      `task/127-task-workflow-automation` после прямого запроса владельца. Локальный controller,
      CI provenance, ADR/runbook и deterministic rehearsal находятся в implementation lifecycle;
      live GitHub App/Ruleset apply остаётся на обязательном owner checkpoint. Task закрепляет
      `1 task = 1 branch = 1 worktree`, integration-only `dev`, atomic leases, task PR в `dev`,
      единую сериализованную integration queue, provenance/recovery и безопасный `master -> dev`
      sync. Task `127` не запускается автоматически и не заменяет отдельный запуск product Task
      `119`; до завершения `127` несколько параллельных write-сессий не считаются безопасными.

Не выполнять повторно tasks `00-80`, включая `69B`, `73A`, task `74A` и tasks `103-106`.
Task `77` закрыта не как factual real-user validation, а по явному owner decision принять отсутствие
сессий и residual risk. Tasks `78-80` закрыты после owner approval. History rewrite `master`
запустил предусмотренный automatic production workflow; runtime diff относительно прежнего master
был нулевым, health после rollout зелёный, а владелец подтвердил auto-deploy как feature. После
branch normalization owner вставил и принял Task `113A`; Task `114` завершена и архивирована после
owner approval, production release явно разрешён.
`DESIGN_V2_1` с owner-approved bounded Pulse pilot остаётся production baseline. Permanent branch
source разработки — `dev`, production source — protected `master`. Tasks `114`, `115A` и `116-118`
завершены и архивированы; историческая запись о Task `119` как фактической next product task
superseded Product v8 audit #683 и не запускает её lifecycle.
Umbrella `100` отдельно не выполняется; `100A` не назначена без собственного Trigger, dependency
и owner decision. Tasks `107-111`, family `126` и Task `127` также не запускаются автоматически.
Завершённая task `112` не изменила product order. Другие pending tasks автоматически не
реализуются.

## Nutrition Label OCR closeout

- [x] Task 128G: implementation, PR #281, merge, production deployment, RapidOCR activation и
      synthetic/corpus validation complete; production HUMAN_EVIDENCE FAIL /
      BLOCKED BY CURRENT INFRASTRUCTURE из-за 503 local_ocr_timeout на текущем host; production
      quality GO NO; public rollout и дальнейшая оптимизация DEFERRED UNTIL SERVER MIGRATION.
- [x] Task 128G exposure mitigation: production NUTRITION_LABEL_SCAN_ENABLED=false,
      NUTRITION_LABEL_SCAN_KILL_SWITCH=false; active SHA остаётся
      1dae5176456b190c15fcd9c9fb6078cf8c338bf1; отдельный deploy не требуется.
- [ ] Task 128H: DEFERRED, not started. Exact trigger:
      Production migrated to a more powerful server and owner explicitly authorizes reopening
      nutrition-label OCR work.
- [ ] F-128G-01: MEDIUM UX follow-up deferred with 128H; обычные Nutrition/Food flows не входят
      в dependency и продолжаются независимо от OCR.

Task 128G не блокирует более приоритетные backlog tasks. Только tasks, которым нужен именно
production-ready label scanning, сохраняют будущую dependency на 128H.
