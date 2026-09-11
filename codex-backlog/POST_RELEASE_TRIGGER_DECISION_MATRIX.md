# Trigger and owner decision matrix

Перед запуском направления заполнить его строку фактическим evidence. Для downstream task
дополнительно проверить dependency и собственный checkpoint из task-файла.

| Task/direction | Evidence source | Baseline | Observed problem/demand | Decision rule | Owner decision | Date |
|---:|---|---|---|---|---|---|
| `80` | | | | Release `79` закрыт; owner запускает bounded cleanup без history rewrite | | |
| `81` | | | | Есть повторяемый optional hydration job и подтверждён report/reminder scope | | |
| `82` | | | | Daily subjective context полезен пользователю/тренеру и не дублирует weekly check-in | | |
| `83` | | | | Есть потребность в explicit handoff сверх пассивного coach access | | |
| `84` | | | | Пользователи явно включают meal/water/movement templates; anti-spam contract принят | | |
| `85` | | | | Есть editorial capacity, primary sources и подтверждённые вопросы пользователей | | |
| `86` | Owner/product inputs from Task 86 continuation brief, 2026-09-05 | Web ~60%, TMA ~40%; Web users regularly return; Web is an independent primary channel | Browser/TMA return requires more actions and has worse availability; no home-screen icon/standalone UX; Telegram is not universal; active workout must survive background/lock/suspend/freeze/discard/reopen | Owner-provided evidence closes the trigger gate; quantitative analytics fields remain to be instrumented and verified in Task 86 | `Go` | 2026-09-05 |
| `86A` | Owner/product inputs recorded for Task 86 | Web Push is product-necessary because notifications exist and Telegram is not universal | Web notification subscriptions, delivery, permission UX, backend integration and lifecycle are not covered by Task 86 | Start only after Task 86 PWA/SW foundation is complete; separate owner launch and privacy/security gate | Pending after `86` | 2026-09-05 |
| `87` | | | | Определены конкретные AI jobs, privacy boundary, evals и допустимая стоимость | | |
| `88` | Результат `87` | | | Только explicit owner `Go` после provider/privacy decision | | |
| `89` | Результат `88` | | | Grounded core прошёл evals; доказана потребность в consented personal tools | | |
| `90A` | Результат `89` | | | Core/tools готовы к internal UI/evaluation gate | | |
| `90B` | Результат `90A` | | | Есть реальные participants, consent и готовность к ограниченному rollout | | |
| `91` | Результат `90B` | | | Rollout получил `Go`, а пользователям нужна интерпретация factual report | | |
| `92A` memory | Owner decision в текущей сессии, 2026-09-11; scope и категории memory перечислены в owner decision | Current AI Coach canonical data остаются источником истины; durable memory ранее отсутствовала | Owner подтвердил узкий continuity/personalization job только для данных вне canonical product model | Только четыре approved non-medical categories; explicit confirmation, user controls, provenance, canonical precedence и запрет sensitive/history duplication | `Go`, narrow scope | 2026-09-11 |
| `92B` provider routing | Owner decision в текущей сессии, 2026-09-11; фактическое provider evidence ещё не предоставлено | Текущий single-provider route и graceful unavailable state | Измеримый outage/capability/latency/cost/privacy/quality gap пока не установлен | `Research first`: metadata-only evidence; implementation только после нового evidence-backed owner decision, максимум 2 providers | `Research first` | 2026-09-11 |
| `93A` | Owner Narrow Go в launch brief Task 93A, 2026-09-06; synthetic versioned corpus добавлен в `backend/tests/test_program_import.py`; реальный пользовательский corpus недоступен | `pre-implementation quantitative baseline: not measured` | Канонический шаблон v1 даёт ограниченный deterministic scope; нужны bounded extraction/matching/preview, manual resolution, privacy-safe telemetry и atomic private unassigned confirm | Versioned canonical template покрывает согласованный v1 job; AI dependency и произвольные layouts исключены | `Narrow Go` | 2026-09-06 |
| `93B` | Результат и usage baseline `93A`; corpus heterogeneous XLSX/CSV/TXT/DOCX | | | Измеримый unsupported/manual-resolution gap сохраняется; compatible provider privacy/cost contract принят; AI улучшает locked baseline без critical failures | | |
| `94A` | | | | После AI-блока manual food entry friction измерим; owner одобрил bounded research/provider-cost boundary | | |
| `94B` | Результат `94A` | | | Только owner `Go/Narrow Go` с locked cases/thresholds/privacy/cost | | |
| `95A` | | | | Browser print-to-PDF из `67` не закрывает повторяемый delivery job | | |
| `95B` | Результат `95A` | | | Отдельно доказан temporary share и/или Telegram delivery | | |
| `96` | | | | Подтверждён один конкретный wearable datum/platform/job | | |
| `97` | | | | Есть реальная команда и owner-approved responsibility matrix | | |
| `98` | | | | Есть измеримое ограничение Web/TMA/PWA, требующее native feasibility | | |
| `99A` | | | | Есть payer/value contract и измеримые operating/AI/storage costs | | |
| `99B` | Результат `99A` | | | Только explicit commercial/provider `Go` | | |
| `99C` | Результат `99B` | | | Sandbox стабилен; owner утвердил цены, тексты и rollout cohort | | |
| `100A` | | | | Подтверждены target segment, reviewer capacity и scope первой волны | | |
| `100B` | Результат `100A` | | | Locale foundation стабильна; подтверждены public/SEO/content scope и reviewer | | |
| `101` | | | | Есть повторяющийся спрос и готов sensitive-media lifecycle; AI/body analysis исключён | | |
| `107` | Owner request и аудит current GitHub Actions/test harness | Большой regression scope уже существует, но нет schedule, единого Allure HTML, очевидной browser-ссылки, закрытого доступа и явного lifecycle отчётов | Владелец утвердил `allure.your-fitness-coach.ru`, Cloudflare Access allowlist, Daily `14` дней и Weekly `4` отчёта | Task creation approved; implementation требует отдельного owner запуска, а DNS/Cloudflare/hosting/secrets — дополнительного explicit approval | Создать task, implementation pending | 2026-08-28 |
| `108` | Прямой owner request на проверку соответствия законодательству РФ | Существующие security/privacy/product audits не дают полного legal-risk coverage и не охватывают автоматически ещё не созданные задачи | Владелец потребовал охватить весь проект, все backlog tasks и любые будущие задачи через continuous gate | Task creation approved; Stage A read-only audit, обязательный RF counsel review baseline/gate, Stage B, `LEGAL_COUNSEL_REQUIRED`, remediation и external legal actions имеют отдельные checkpoints | Создать task, audit pending | 2026-08-28 |
| `109` | Прямой owner request на ясный Landing offer | Фактические proof уже есть, но общий оффер распределён по секциям; security claim пока не имеет отдельного approved baseline | Собрать уникальность через связный YFC feedback loop без competitors/fake proof; trust copy — только из approved baseline `108` | Task creation approved; implementation, final copy и screenshots требуют отдельных owner launch/approval | Создать task, implementation pending | 2026-08-28 |
| `110` | Прямой owner request на собственный avatar desktop/mobile | Сейчас есть provider `photo_url` и детерминированный emoji fallback, но нет управляемого custom upload | Private upload с safe processing, replace/delete/export и fallback `custom -> provider -> emoji`; без публичного профиля или анализа изображения | Task creation approved; implementation и production migration/deploy требуют отдельных owner decisions | Создать task, implementation pending | 2026-08-28 |
| `111` | Прямой owner request и предоставленный visual reference | Progress имеет частичные периоды/произвольный report range, но не единый `1/7/30/90/365/custom` bento overview | Перенести hierarchy референса в YFC без выдуманных данных и второго analytics pipeline | Task creation approved; implementation, screenshots и performance evidence требуют отдельных owner launch/approval | Создать task, implementation pending | 2026-08-28 |
| `126A` | Прямой owner request на `камера -> тренажёр -> упражнения -> добавить в программу`; результаты `120D` и `90B` | Camera recognition отсутствует; exercise expansion уже владеет `120A-120D`, поэтому отдельная база не нужна | После завершения `120D` и successful `90B` провести bounded Vision/non-AI feasibility, representative corpus, privacy/cost/latency eval и выбрать `GO/NARROW GO/NO-GO` | Task family creation approved; запуск 126A только после prerequisites и отдельной owner команды; paid/live provider actions отдельно gated | Создать task family, research pending | 2026-08-30 |
| `126B` | Результат `126A` | Production Vision recognition/matching отсутствует | Только owner `GO/NARROW GO` с locked supported classes, thresholds, provider/privacy/cost contract | Реализовать server-side image boundary и deterministic equipment -> existing exercise matching; не запускать автоматически | | |
| `126C` | Результат `126B` | Camera shortcut в add-exercise flow отсутствует | Backend 126B прошёл review/QA, фактические quality/latency/privacy результаты остаются приемлемыми | Реализовать Mobile Web/TMA camera/picker UX и переиспользовать existing add-to-program flow; owner device/screenshot gate обязателен | | |
| `127` | Прямой owner request после фактического concurrent write/commit/push race в общем `dev` worktree | Правила одновременно допускают permanent implementation в `dev` и требуют task branches; `dev` допускает ordinary direct push, единой atomic integration queue нет | Ввести `1 task = 1 branch = 1 worktree`, integration-only `dev`, task session controller/leases, task PR -> dev, strictly serial merge queue, dev provenance, release freeze и recovery без destructive cleanup | Task creation approved; implementation требует отдельного owner запуска; live Ruleset/merge queue/bypass/sync actor changes имеют отдельный checkpoint | Создать Task 127, implementation pending | 2026-08-30 |

## Завершённые owner decisions

| Task/direction | Evidence source | Baseline | Observed problem/demand | Decision rule | Owner decision | Date |
|---:|---|---|---|---|---|---|
| `103` | Owner-selected editorial flow | | | Stable Telegram Core и owner moderation capacity | `Go`, выполнено | 2026-08-26 |
| `104` | Результат `103` | | | Требовались images/moderation/publication boundaries | `Go`, выполнено | 2026-08-26 |
| `104A` | Real owner preview task `103` и feedback | Task `104` владеет images/moderation/publication | Служебный plain-text draft не является готовым канальным постом | После `104` нужен formatted artifact gate перед `105` | `Go`, выполнено | 2026-08-26 |
| `105` | Опубликованные snapshots цепочки `103 -> 104 -> 104A` | Recurring private digest по умолчанию отсутствовал | Подтверждён интерес к недельной подборке и consent copy/version `weekly-news-v1` | Только default-off opt-in и мгновенная изолированная отписка | `Go`, выполнено | 2026-08-26 |
| `106` | Owner-approved Landing task и screenshot evidence | Telegram destinations были смешаны | Канонические Main Mini App/support/news links | Явные distinct links без нового runtime | `Go`, выполнено | 2026-08-28 |

Допустимые решения для pending: `Go`, `Defer`, `No-Go`, `Research first`. Пустая строка, номер или
завершённая dependency не считаются согласием.

Для Task `86` evidence предоставлен владельцем в continuation brief, а не production analytics
или синтетическим user test. Не предоставлены source/period/sample/latency/browser-distribution
поля количественной аналитики; они не выдумываются и остаются ограничениями измерения/задачами
реализации и верификации. Это не блокирует запуск, поскольку текущий `Go` опирается на явное
описание пользовательского gap и критического active-workout lifecycle владельцем.
