# Порядок направлений после release gate `79`

## Текущий owner-driven UX-reset cycle

До возврата к прежнему trigger-gated pool действует линейная canonical очередь:

```text
113 branch normalization [COMPLETED]
  -> 113A Owner UX Stabilization [COMPLETED, OWNER ACCEPTED]
  -> 114 nutrition/barcode P0 regression [COMPLETED, OWNER APPROVED, RELEASE AUTHORIZED]
  -> 115A UX audit + IA + compactness/disclosure prototype/spec [COMPLETED, OWNER APPROVED: COMMAND STACK]
  -> 116 [COMPLETED] -> 117 [COMPLETED] -> 118 [COMPLETED]
  -> 119 [NEXT PRODUCT TASK, NOT STARTED] -> 120A -> 120B -> 120C -> 120D
  -> 121 -> 122 -> 123
  -> 81 Hydration -> 82 Sleep/Mood -> 84 Reminders
  -> 124A pre-release integrated UX/QA gate
  -> OWNER RELEASE APPROVAL
  -> dev -> master + production deployment
  -> 124B production real-user usability validation
  -> 124C only if 124B has BLOCKER/HIGH
```

Task `115B` и pre-implementation gate `116+ blocked until real-user validation` не применяются.
Human validation выполняется на фактически deployed production build в Task `124B`; Task `115A`
закрыла owner design gate выбором `Command Stack`, а Task `124A` остаётся pre-release QA gate.

Tasks `85`, `110`, `111` остаются pending вне critical path: соответственно после `121`, `122`,
`123`. Они входят в `124A` только если владелец отдельно включил их в тот же release candidate.

После завершения Task `113` source разработки — permanent `dev`, production source — protected
`master`. Release/smoke Task `113A` завершены, точная owner-команда
`Stabilization принята. Можно переходить к Task 114.` получена `2026-08-30`. Tasks `114`, `115A`
и `116-118` затем запускались отдельными командами, завершены и архивированы; Task `119` не
запускается автоматически.

Tasks `80-101` и их буквенные подзадачи образуют trigger-gated post-release pool. Номер task
задаёт предпочтительную последовательность реализации, но не отменяет фактический Trigger,
dependency и отдельное решение владельца.

Nutrition Label OCR family после owner-authorized closeout Task 128G вынесена в отдельную
deferred ветку: production-quality GO отсутствует, exposure выключена, а Task 128H не входит
в текущую общую очередь и не запускается автоматически. Более приоритетные tasks не должны
ждать OCR; dependency на 128H сохраняется только для будущей production-ready label-scanning
работы после миграции host и exact owner trigger.

## Последовательность pending-задач

Таблица ниже сохраняет порядок общего pool после текущего UX-reset cycle и не переопределяет
описанный выше critical path.

|        Task | Направление                          | Почему здесь                                                                                                      |
| ----------: | ------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
|        `80` | Repository hygiene/security/README   | Уменьшает риск утечек, мусора и stale setup до новых изменений                                                    |
|        `81` | Hydration в Nutrition                | Частый optional daily flow на готовых diary/report foundations                                                    |
|        `82` | Daily sleep + mood                   | Добавляет субъективный контекст в дневные и периодические отчёты                                                  |
|        `83` | Handoff отчёта trainer               | Закрывает core coaching loop без публичной ссылки                                                                 |
|        `84` | Reminder templates                   | Переиспользует task `64` и данные hydration после `81`                                                            |
|        `85` | Knowledge package                    | Низкий runtime risk, практичная польза и grounding для AI                                                         |
|        `86` | PWA                                  | Улучшает возврат к тренировке при подтверждённом Web retention gap                                                |
|       `86A` | Web Push notifications               | Отдельный follow-up на базе PWA/SW Task `86`; не зависит от Telegram как единственного канала                     |
|     `87-91` | AI Coach beta и period insights      | Сначала privacy/provider gate, затем grounded core, tools, evals, rollout и bounded report insights               |
|   `92A-92B` | Advanced AI                          | Memory и multiprovider остаются рядом с AI Coach, но запускаются независимо только после evidence beta            |
|       `93A` | Deterministic import XLSX/CSV без AI | Даёт раннюю ценность через versioned template и общий безопасный preview/confirm pipeline без provider dependency |
|       `93B` | AI-assisted import XLSX/CSV/TXT/DOCX | Только после evidence `93A`: расширяет поддерживаемые layouts/documents, сохраняя deterministic fallback          |
|   `94A-94B` | Распознавание еды по фото            | Важная функция после основного AI Coach-кластера: feasibility/eval, затем только подтверждаемый draft             |
|   `95A-95B` | Server PDF и внешняя доставка        | Нужны только при доказанном gap после in-product handoff `83`                                                     |
|        `96` | Wearables discovery                  | Research-only для конкретного data/platform job                                                                   |
|        `97` | Delegated admins                     | Требует реальной команды и responsibility matrix                                                                  |
|        `98` | Native feasibility                   | Только при измеримом ограничении Web/TMA/PWA                                                                      |
|   `99A-99C` | Billing/монетизация                  | По решению владельца оставлено почти в самом конце                                                                |
| `100A-100B` | Английская локализация               | По решению владельца оставлена в хвосте                                                                           |
|       `101` | Приватные фотографии прогресса       | Последняя очередь; AI/body analysis полностью исключён                                                            |

## Почему импорт разделён на deterministic baseline и AI enhancement

Прежние tasks `81-program-import-xlsx-csv` и `95-program-import-txt-docx` сначала были объединены в
task `93`, а затем декомпозированы в `93A` и `93B`. Пользовательский job и pipeline остаются едиными:
загрузить существующую программу, проверить распознанную структуру и получить редактируемый draft.
Этапы разделены по независимой ценности и dependency: canonical XLSX/CSV template полезен без AI,
тогда как heterogeneous documents требуют отдельного evidence/provider/privacy/cost gate.

`93A` строит upload/security, neutral draft, deterministic matching, preview/resolution и atomic
confirmed write. `93B` переиспользует этот baseline: AI предлагает нейтральную структуру и помогает
ранжировать только ограниченный список кандидатов. Права доступа, валидация и запись остаются
детерминированными; AI-score не разрешает auto-match или создание canonical exercise.

## Routing rules

- Umbrella `90`, `92`, `93`, `94`, `95`, `99`, `100`, `126` — coordination contracts, а не executable tasks.
- Внутри обязательных цепочек соблюдать порядок: `87 -> 88 -> 89 -> 90A -> 90B -> 91`,
  `94A -> 94B`, `95A -> 95B`, `99A -> 99B -> 99C`, `100A -> 100B`.
- `92A` и `92B` независимы: потребность в memory не доказывает потребность во втором provider.
- `93A` не зависит от AI-кластера и запускается только по собственному corpus/evidence/owner Trigger.
- `93B` требует завершённую `93A`, измеримый gap и compatible AI route; `92A/92B` могут завершиться
  `Defer/No-Go` и не блокируют AI-assisted import.
- Food-photo выполняется после основного AI-блока: сначала task `94A`, а task `94B` — только после
  owner `Go/Narrow Go` с зафиксированными thresholds, privacy и cost contract.
- `83` не заменяет `95B`: первая task создаёт authenticated in-product handoff текущему trainer,
  вторая отдельно владеет expiring share/Telegram delivery.
- `101` не включает и не порождает AI-анализ фото тела, оценку формы или рекомендации по внешности.
- `126A` требует `120D + successful 90B`; далее только `126A -> owner GO/NARROW GO -> 126B -> 126C`. `91/92A/92B/94A/94B` не являются hard dependencies.
- После любой task остановиться; следующая задача требует отдельного запуска.

Завершённые Telegram-задачи `103-106` архивированы и не входят в pending-последовательность.
Owner-selected task `106` завершила discoverability Telegram Mini App, поддержки и публичного
канала на Landing и не изменила порядок `80-101`.

Owner-selected task `107` создана вне pending-последовательности для scheduled regression и
закрытых Allure-отчётов. Её owner-approved scope не меняет next task `119` или UX-reset path;
implementation и внешние DNS/Cloudflare/hosting actions требуют отдельного запуска/approval.

Owner-selected task `108` создана вне pending-последовательности для product-wide аудита
соответствия законодательству РФ и непрерывного legal-impact gate будущих задач. Она не меняет
next task `119` или UX-reset path; запуск, legal review и любые remediation/external actions
требуют отдельных owner decisions.

Owner-selected Task `109` завершена и архивирована вне pending-последовательности. Pending Tasks
`110/111` остаются отдельными направлениями custom avatar и Progress bento dashboard: они не
меняют next task `119` или UX-reset path, не образуют общую implementation batch и запускаются
только отдельными owner решениями.

Owner-selected umbrella `126` также находится вне pending-последовательности. Она фиксирует
future feature распознавания тренажёра камерой без дублирования exercise expansion `120A-120D`.
Исполняемая цепочка: `126A feasibility/evals -> owner GO/NARROW GO -> 126B backend recognition/matching
-> 126C camera/TMA/program integration`. `126A` требует завершённую `120D` и successful AI beta
foundation до `90B`. Task `91` не является hard dependency, потому что period insights не добавляют
image capability; `92A` не относится к job, а `92B/94A/94B` переиспользуются только если уже
завершены и совместимы. Family не меняет current UX-reset path и не запускается автоматически.

Owner-selected task `112` завершена и архивирована вне pending-последовательности после локального
review/QA zero-downtime deployment contract. Отдельно разрешённый production rollout revision
`194cf036` завершён через `single-slot` fallback с bounded downtime и verdict `active`; production
blue/green zero observed downtime на constrained VPS не заявляется. Tasks `116-118` завершены;
next/not-started product task — `119`; UX-reset path не изменился.

Owner-selected Task `127` создана вне product sequence для обязательного перехода на
`1 task = 1 branch = 1 separate worktree`, integration-only `dev` и единую сериализованную очередь
task PR merge в `dev`. Она не запускает Task `119` и не меняет её product scope. До завершения
Task `127` разрешён только прежний строго последовательный single-writer режим; несколько
параллельных write-сессий не считаются безопасными.
