# RU/CIS Semantic Core и SEO opportunity research

Дата исследования: 2026-09-16
Task: 241A
Scope: русскоязычный public Web YFC; Россия, Казахстан, Беларусь; Google и Yandex раздельно.

## Executive summary

**A. Что имеет смысл запускать первым.** Owner-provided Yandex Wordstat export теперь
интегрирован в исследование. Самый большой наблюдаемый кластер — `калькулятор кбжу`
(Россия: 16 127 broad и 4 763 quoted/fixed-word-count), затем exercise technique и дневник
тренировок. Это evidence о поисковом сигнале, а не прогноз трафика и не Google Ads exact match.

**B. Обновлённый порядок Wave 1.** Сначала усилить существующий `/nutrition`, затем сделать
эталонной страницу `/exercises/bench-press`, усилить `/training`, реализовать 1ПМ и один
русскоязычный canonical asset для intent `программа тренировок 3 раза в неделю`. `/for-trainers`
остаётся коммерчески подходящим улучшением, но его Wordstat demand для заявленного seed не
подтверждён.

**C. Что отложить.** `/calculators/training-volume` и тонnage не входят в Wave 1: broad demand
слабый, а quoted/fixed-word-count signal почти отсутствует. Отдельный heart-rate calculator,
самостоятельный diary landing и country-specific pages также откладываются. Для cardio/nutrition
сначала нужны authoritative sources, reviewer policy и claims review.

**D. Что усилить вместо новых URL.** `/training` — дневник, запись подходов и сохранение
программ; `/nutrition` — текущий КБЖУ flow с прозрачными ограничениями; `/for-trainers` —
workspace value и путь `trainer activation -> client_invited`; `/knowledge` и связанные guides —
контекстные объяснения; `/exercises` — только реальные canonical cards из доменного каталога.

**E. Cannibalization.** Основные риски — несколько страниц вокруг `1ПМ` и `full body 3 раза в
неделю`, а также отдельные pages для `дневник тренировок`, `приложение для тренировок` и
`программа тренировок`. Нужен один canonical page per job с sections/variants, а не exact-match
страница на каждую формулировку. `/nutrition` не следует раздваивать на `/calculators/kbju`, пока
новый URL не получит materially different tool intent и самостоятельную product value.

**F. Что ещё нужно извне.** Нужно owner review выводов и отдельные product contracts для
будущих save flows; Wordstat export сам по себе не авторизует production page creation, merge или
Task 241B. GSC baseline `0 clicks / 0 impressions` за 28 settled days through 2026-09-11 — только
T0, не evidence отсутствия спроса.

## Evidence и ограничения

### Current YFC audit

Проверены current task worktree от `origin/master` SHA
`7f0151c2586b4fc95d82cd06560f9ccd7ae2c821`, manifest
`frontend/src/content/publicContent.json`, `docs/seo/public-content.md`,
`docs/seo/growth-analytics-foundation.md` и live host `https://your-fitness-coach.ru/`.

В baseline этого исследования manifest содержал 24 public entries: landing, 4 product pages,
knowledge index, 14 guides, exercise index и 3 exercise pages. После Task 241E canonical 1ПМ
страница добавлена в manifest; текущий sitemap содержит 26 canonical URLs (включая `/articles`).
`robots.txt`, `sitemap.xml` и основные public routes отвечают `200` в baseline-проверке; обновлённый
manifest добавляет один canonical URL для Task 241E. Private/API routes в sitemap не включаются.

| Current page | Current intent | Coverage gap | Action for future implementation |
| --- | --- | --- | --- |
| `/` | product overview, Web + Telegram entry | Не показывает конкретный calculator/program job | Оставить product landing; добавить только доказанный compact entry point |
| `/training` | программы, план и запись тренировок | Diary/app intent и save loop недостаточно explicit для search visitor | Усилить copy/IA и deep links; не создавать отдельный diary page в wave 1 |
| `/nutrition` | current KBJU orientation/calculator | Нет отдельной acquisition page для calorie/protein variants; health trust boundary | Усилить existing page; new calculator URL только после distinct tool contract |
| `/progress` | записи результатов, нагрузки, measurements | Не является top-of-funnel calculator/program page | Оставить supporting page; связать с program/trainer flows |
| `/for-trainers` | trainer workspace: programs, invites, client progress | Commercial CRM language и proof/FAQ могут быть сильнее | Усилить existing page; не создавать `/for-trainers/crm` без отдельного job |
| `/knowledge` | educational catalog | Частично покрывает RIR, Full Body/Split, KBJU, heart rate, hydration | Использовать как context layer; link only to relevant tools/programs |
| `/knowledge/...` | durable guides with sources/limits | Нет volume guides; 1ПМ теперь имеет supporting context, некоторые intents ведут к future tools | Add guides only beside a useful asset, not article volume for its own sake |
| `/articles` | public article index contract | Current SEO research does not prove article-first opportunity | Не превращать в keyword doorway; not Wave 1 |
| `/exercises` | allowlisted exercise catalog | Только bench press, lat pulldown, squat; thin expansion risk | Expand one verified canonical page at a time with useful technique/media |
| `/exercises/<slug>` | technique, errors, safety, domain data | No public add-to-workout action yet | Add CTA only when public-to-product flow exists; otherwise informational |

### Demand evidence policy

Owner-provided `Yandex Wordstat -> Regions` export покрывает период `15.08.2026–15.09.2026`,
фильтр устройств `все устройства` и основной регион `Россия`. В CSV `demand_value` сохраняет
число broad frequency для России как backward-compatible краткое значение. Поля
`demand_broad_frequency`, `demand_quoted_frequency` и `quoted_broad_ratio` разделяют фактические
метрики. `NO_DATA` означает отсутствие пригодной выгрузки, а не нулевой спрос.

Под кавычками понимается Wordstat operator `"..."`: он фиксирует количество слов, но не
обязательно порядок и словоформу. В этом исследовании это называется
`quoted/fixed-word-count frequency`, а не exact match в смысле Google Ads. Если quoted export не
получен, broad остаётся валидным, а quoted и ratio получают `NO_DATA`.

Для строк с owner evidence используются статусы `observed_broad_and_quoted` или
`observed_broad_only`; для остальных seed variants — `no_export_available`. Ни одно отсутствие
данных не превращается в `0`, `UNKNOWN` или субъективный score 0–5.

Один initial Yandex snapshot по `калькулятор 1пм` был доступен и показал utility SERP, но число
`19 млн результатов` не является frequency и в ranking не используется. Google UI snapshots
показывают organic composition и related queries, но Google Keyword Planner data не собиралась.
Detailed input/import contract находится в `manual-wordstat-input.md`.

### Owner Wordstat evidence matrix

Значения в ячейках — `broad / quoted/fixed-word-count` для указанного региона. `NO_DATA` не
означает ноль. Региональные значения не усредняются и не подменяют основной Russia row в CSV.

| Seed | Россия | Москва и МО | Москва | Санкт-Петербург и ЛО | Санкт-Петербург | Казахстан | Беларусь | СНГ без России |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `калькулятор 1пм` | 363 / 261 | 90 / 70 | 39 / 26 | 27 / 21 | 22 / 18 | 1 / NO_DATA | NO_DATA | 15 / 14 |
| `программа тренировок 3 раза в неделю` | 1351 / 32 | 247 / 10 | 137 / 4 | 86 / NO_DATA | 75 / NO_DATA | 7 / 1 | 35 / NO_DATA | 47 / NO_DATA |
| `full body 3 раза в неделю` | 20 / NO_DATA | 4 / NO_DATA | 3 / NO_DATA | 5 / NO_DATA | 4 / NO_DATA | 1 / NO_DATA | NO_DATA | NO_DATA |
| `дневник тренировок` | 3038 / 456 | 832 / 195 | 630 / 184 | 389 / 105 | 350 / 102 | 16 / 3 | 58 / 10 | 79 / 13 |
| `калькулятор кбжу` | 16127 / 4763 | 3715 / 1194 | 2217 / 787 | 1255 / 387 | 967 / 300 | 135 / 57 | 304 / 79 | 461 / 148 |
| `жим лежа техника` | 2943 / 528 | 651 / 100 | 402 / 73 | 232 / 53 | 182 / 47 | 13 / 3 | 26 / 4 | 48 / 8 |
| `программа тренировок для новичка` | 604 / 34 | 124 / 8 | 82 / 8 | 45 / 3 | 33 / 1 | 5 / 1 | 3 / NO_DATA | 9 / NO_DATA |
| `тоннаж тренировки` | 181 / 2 | 33 / 1 | 21 / 1 | 8 / NO_DATA | 7 / NO_DATA | 2 / NO_DATA | NO_DATA | 3 / NO_DATA |
| `калькулятор объёма тренировки` | 5 / NO_DATA | NO_DATA | NO_DATA | NO_DATA | NO_DATA | NO_DATA | NO_DATA | NO_DATA |
| `приложение для фитнес тренера` | NO_DATA | NO_DATA | NO_DATA | NO_DATA | NO_DATA | NO_DATA | NO_DATA | NO_DATA |

The owner export contains smaller but non-zero Russian-language signals in Kazakhstan and Belarus
for several major clusters, especially KBJU, diary and programs. This supports one RU/CIS
canonical surface, not `/kz` or `/by` clones.

### SERP observation dates

- Google: UI snapshots 2026-09-14 и контрольные snapshots 2026-09-16, `hl=ru`, `gl=ru`, Russia,
  non-personalized where the page exposed that state.
- Yandex: 2026-09-16, `lr=2`/visible St Petersburg region for the accessible snapshot; subsequent
  query switching reached SmartCaptcha. Yandex competitor observations are therefore directional,
  not a full regional sample.
- Competitor pages and H1/form/structured-data checks: public HTTP fetches 2026-09-14–16.

## Transparent prioritization model

The numeric `priority_score` is an implementation-opportunity proxy, **not search volume**:

```text
100 × (0.30 product_fit
     + 0.20 conversion_intent
     + 0.20 serp_attainability
     + 0.15 content_readiness
     + 0.10 internal_linking
     + 0.05 geo_breadth) / 5
```

`Search demand` is recorded separately as the Wordstat evidence above. Scores are 0–5 and remain
an opportunity proxy, not demand. `priority_score` in the CSV is that product/opportunity proxy;
it must not be compared numerically with 16 127, 2 943 or any other Wordstat frequency.
Health/claims penalty, implementation cost and cannibalization risk remain separate decision
dimensions. A cluster can be proposed for implementation only after owner review and its product
contract; Wordstat does not authorize production changes.

| Cluster | RU Wordstat evidence | Quoted/broad | Product/opportunity score | Health/claims penalty | Implementation cost | Cannibalization / decision |
| --- | ---: | ---: | ---: | --- | --- | --- |
| F KBJU/calorie/protein | 16127 / 4763 | 29.5% | 69 | high | M | high if duplicate URL; strengthen `/nutrition` in Wave 1 |
| E exercise technique | 2943 / 528 for bench press | 17.9% | 75 | medium | M | improve `/exercises/bench-press`, then bounded expansion |
| H workout diary/app | 3038 / 456 | 15.0% | 73 | low | S/M | strengthen `/training`; no diary duplicate |
| A 1ПМ/working weights | 363 / 261 | 71.9% | 87 | low–medium | M | `/calculators/1rm` implemented; high formula-variant cannibalization |
| C 3-day / beginner program | 1351 / 32 for broad Russian program seed | 2.4% | 87 | low–medium | M | one canonical program asset; Full Body wording is secondary |
| D trainer workspace / CRM | NO_DATA | NO_DATA | 81 | low | S/M | improve `/for-trainers` conditionally; demand remains unknown |
| B training volume / tonnage | 181 / 2 for tonnage; 5 / NO_DATA for calculator | 1.1% / NO_DATA | 83 | low–medium | M/L | defer; fix definition before tool work |
| G pulse zones | NO_DATA | NO_DATA | 60 | high | M/L | defer for claims/source review |

## Cluster conclusions

### A — 1ПМ, RM and working-weight tools

Dominant intent is `tool/calculator`, with adjacent informational formula and percentage queries.
Google and Yandex both show multiple calculators, not only articles: Start-fit, Body1, GeneticLab,
AnatomyStudy, Sport-iv, Inspire2, Zozhnik and other utility pages. The gap is not another formula
explanation; it is a trustworthy result with explicit formula/limitations, exercise context,
percentage table, and a future save-to-program path. The canonical result is now implemented at
`/calculators/1rm`; saving remains a separate product contract.

Recommended canonical hypothesis: `/calculators/1rm`. Do not create separate URLs for `жим`,
`присед`, `становая` until data shows a materially different intent; exercise selector/sections
should prevent cannibalization. Owner Wordstat shows 363 broad and 261 quoted/fixed-word-count
for the main seed, a 71.9% ratio: modest volume but unusually pure intent. Product dependency:
the `calculator_saved` flow does not exist yet; the calculator result is intentionally local and
action-only.

### B — training volume and tonnage

Intent is mostly `tool/calculator` plus informational planning (`sets per muscle group`). SERP has
interactive tools from AnatomyStudy, Start-fit, OnlyPump, Calcal and Sport-iv. Owner Wordstat is
weak for the direct calculator seed (5 broad and no quoted export) and modest for `тоннаж тренировки`
(181 broad and 2 quoted), so this is not Wave 1. YFC can still differentiate later with a transparent
definition of volume, per-exercise/per-week views, and direct program context, not a generic tonnage
number. Need a separate contract for planned versus completed sets; do not imply an evidence-based
optimal range without sources.

### C — 3-day and beginner programs

Intent splits into `program/template` and informational advice. The broader Russian seed
`программа тренировок 3 раза в неделю` has 1 351 broad but only 32 quoted/fixed-word-count, while
`full body 3 раза в неделю` has 20 broad and no quoted export. Build one Russian canonical program
asset and use Full Body as concept/secondary wording, not as the primary acquisition phrase. Google
SERP contains InstructorPRO, Maxler, Dzen/Championat, Reddit and video results; the page must be
more useful than a text list by exposing days, exercises, progression notes and a future
`public_program_saved` flow. Keep beginner, mass and weight-loss variants under one information
architecture until stronger evidence supports separate intents.

### D — trainer workspace / CRM

Intent is `commercial investigation` / `transactional product`. Fitness1C, Rubitime, YCLIENTS,
Fitbase, Bitrix24 and similar products compete on booking, CRM, analytics and client management.
YFC's differentiator is a focused trainer workflow for programs, progress and invite—not a promise
of bookings, payments or full club CRM. No usable Wordstat export was obtained for either requested
trainer seed, so demand remains `NO_DATA`; keep the opportunity based on product fit and commercial
SERP only. Strengthen `/for-trainers` with concrete current actions and proof; a `/for-trainers/crm`
page would be misleading while the product scope remains narrower.

### E — exercise technique

SERP is informational and media-heavy: Fitness3000, Sport-Express, Nef, PlanetaSport, DDX and
videos compete with technique/how-to pages. Existing YFC exercise cards are a sound canonical base
because their data comes from the shared domain catalog. Expand only when the entry has technique,
breathing, common errors, safety limits, equipment/variant and genuinely useful media or diagrams.
Owner Wordstat makes `жим лежа техника` a material opportunity (2 943 broad and 528
quoted/fixed-word-count). Make the existing bench-press canonical page the first exemplar, then
reuse the structure for other verified exercises. The `Добавить упражнение в тренировку` CTA is a
future dependency, not a current promise.

### F — KBJU, calorie and protein tools

Intent is tool-led but high-trust: Alena RightFood, Smart Eat, XFIT, WillFood, PowerTeam and
nutrition/medical sources appear. `/nutrition` already owns a product-calculator story and should be
strengthened before a second canonical URL. Any new page needs transparent assumptions, source/reviewer
policy, health limitations and no individualized medical claim. This is the strongest observed
cluster (16 127 broad and 4 763 quoted/fixed-word-count, 29.5%). First-wave action is to strengthen
`/nutrition`; do not automatically create `/calculators/kbju`.

### G — pulse zones

Interactive tools from Lifehacker, GET.run, GeneticLab, PaceRun and Velosophy show a real tool
intent. However, `пульс для жиросжигания` and zone claims can be misread as medical advice. Defer
until sources, claims review, age/medication limitations and a safe disclaimer contract exist.
Existing heart-rate guide can remain contextual; no new calculator in Wave 1.

### H — workout diary and app

SERP mixes app stores, roundups, Reddit and product pages: GymUp, Gymate, Forma, Lifehacker,
Britetodo, RBC Style. It is commercially attractive but broad and saturated. Current `/training`
already explains programs and recorded sets; strengthen it around `план -> записать -> увидеть
прогресс` and link from program pages. A separate diary landing would duplicate intent until a
distinct public entry and save funnel are implemented. Owner Wordstat shows 3 038 broad and 456
quoted/fixed-word-count, so the existing `/training` improvement moves into the first three actions.

## Top 10 opportunity clusters

The list combines actual RU Wordstat evidence with product fit and implementation constraints. It is
not a ranking of raw frequency alone; `NO_DATA` opportunities remain explicitly uncertain.

1. `калькулятор кбжу` — 16 127 broad / 4 763 quoted; strengthen `/nutrition` with YMYL safeguards.
2. `жим лежа техника` — 2 943 / 528; make `/exercises/bench-press` the first exercise exemplar.
3. `дневник тренировок` — 3 038 / 456; strengthen `/training`, not a duplicate landing.
4. `калькулятор 1пм` — 363 / 261; high-intent BOFU tool with unusually pure quoted ratio.
5. `программа тренировок 3 раза в неделю` — 1 351 / 32; one Russian canonical program asset.
6. `программа тренировок для новичка` — 604 / 34; supporting intent inside the same program IA.
7. `приложение для фитнес тренера` / `CRM для фитнес тренера` — `NO_DATA`; commercial-fit improvement
   of `/for-trainers`, not a demand-confirmed launch.
8. `тоннаж тренировки` — 181 / 2; useful later only after a sound planned/completed-volume contract.
9. `full body 3 раза в неделю` — 20 / `NO_DATA`; secondary wording for the Russian program asset.
10. `калькулятор объема тренировки` — 5 / `NO_DATA`; keep in backlog, outside Wave 1.

Pulse-zone queries remain outside this evidence-informed Top 10 because no owner export was supplied
and the health/claims penalty is high. Adjacent `проценты от 1пм` and `формула 1пм` remain sections
of the 1ПМ asset, not separate pages.

## Product-led linking graph

```text
/calculators/1rm
  -> /knowledge/training/repetitions-in-reserve
  -> /exercises/bench-press, /exercises/squat, relevant future cards
  -> /programs/full-body-3-days
  -> future calculator_saved / program_saved action

/programs/full-body-3-days
  -> /training
  -> exercise cards
  -> /knowledge/training/progressive-overload
  -> future public_program_saved

/for-trainers
  -> /progress
  -> /training
  -> future trainer_activation -> client_invited

/nutrition
  -> /knowledge/nutrition/kbju-as-a-reference
  -> /knowledge/nutrition/protein-and-recomposition
  -> existing product calculator; no invented save CTA
```

Links should be contextual and bidirectional where the destination exists. Do not add a sitewide
keyword footer or link every guide to every tool.

## Recommended next tasks (not started here)

1. Owner review of this packet and the integrated Wordstat evidence.
2. A future product/SEO implementation task for the owner-approved `/nutrition` improvement or
   another bounded first-wave asset, with its product and claims contract.
3. A future task for the canonical 1ПМ save-flow contract, if it is approved separately.
4. A separate bounded task for one Russian 3-day program asset and public-to-product save semantics.
5. A later training-volume spike that first fixes the planned-vs-completed volume definition.
6. Conditional follow-up for cardio only after source, reviewer and claims decisions.

Task 241B is intentionally not started by this research task.

## Sources used

- Live YFC: https://your-fitness-coach.ru/
- YFC public-content contract: `docs/seo/public-content.md`
- YFC growth/analytics contract: `docs/seo/growth-analytics-foundation.md`
- Wordstat entry point and owner export source: https://wordstat.yandex.ru/ (period 2026-08-15..2026-09-15; `Regions`; all devices)
- Google UI snapshots, examples: https://www.google.com/search?q=%D0%BA%D0%B0%D0%BB%D1%8C%D0%BA%D1%83%D0%BB%D1%8F%D1%82%D0%BE%D1%80+1%D0%BF%D0%BC&hl=ru&gl=ru and https://www.google.com/search?q=full+body+3+%D1%80%D0%B0%D0%B7%D0%B0+%D0%B2+%D0%BD%D0%B5%D0%B4%D0%B5%D0%BB%D1%8E&hl=ru&gl=ru
- Yandex UI snapshot: https://yandex.ru/search/?text=%D0%BA%D0%B0%D0%BB%D1%8C%D0%BA%D1%83%D0%BB%D1%8F%D1%82%D0%BE%D1%80+1%D0%BF%D0%BC&lr=2
- Competitor URLs and query-level evidence are listed in `serp-competitor-matrix-ru-cis.md`.
