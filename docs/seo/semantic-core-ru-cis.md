# RU/CIS Semantic Core и SEO opportunity research

Дата исследования: 2026-09-16
Task: 241A
Scope: русскоязычный public Web YFC; Россия, Казахстан, Беларусь; Google и Yandex раздельно.

## Executive summary

**A. Что имеет смысл запускать первым.** Самые сильные product-led opportunities — инструмент
1ПМ/рабочих весов, одна полезная программа Full Body на 3 дня и калькулятор тренировочного
объёма. У всех трёх есть понятный результат, который можно связать с программой и сохранением в
YFC. Это пока opportunity ranking, а не доказательство объёма: Wordstat не дал authenticated
выгрузку, поэтому все demand values остаются `UNKNOWN`.

**B. Что требует Wordstat evidence.** В первую очередь — `калькулятор 1пм`, `калькулятор объёма
тренировки`, `программа тренировок 3 раза в неделю`, `приложение для фитнес тренера`,
`калькулятор кбжу`, `калькулятор пульсовых зон` и `дневник тренировок`. SERP подтверждает
существование intent и конкурирующих utility pages, но не размер спроса.

**C. Что отложить.** Отдельный heart-rate calculator, самостоятельный diary landing, массовое
расширение exercise catalog и country-specific pages не должны входить в первую implementation
wave. Для cardio/nutrition сначала нужны актуальные authoritative sources, reviewer policy и
claims review; для diary intent текущий `/training` закрывает большую часть product story.

**D. Что усилить вместо новых URL.** `/training` — дневник, запись подходов и сохранение
программ; `/nutrition` — текущий КБЖУ flow с прозрачными ограничениями; `/for-trainers` —
workspace value и путь `trainer activation -> client_invited`; `/knowledge` и связанные guides —
контекстные объяснения; `/exercises` — только реальные canonical cards из доменного каталога.

**E. Cannibalization.** Основные риски — несколько страниц вокруг `1ПМ` и `full body 3 раза в
неделю`, а также отдельные pages для `дневник тренировок`, `приложение для тренировок` и
`программа тренировок`. Нужен один canonical page per job с sections/variants, а не exact-match
страница на каждую формулировку. `/nutrition` не следует раздваивать на `/calculators/kbju`, пока
новый URL не получит materially different tool intent и самостоятельную product value.

**F. Что ещё нужно извне.** Owner export из Yandex Wordstat по пяти региональным slices и
уточнение, какие будущие save flows будут доступны в 241B. GSC baseline `0 clicks / 0 impressions`
за 28 settled days through 2026-09-11 — только T0, не evidence отсутствия спроса.

## Evidence и ограничения

### Current YFC audit

Проверены current task worktree от `origin/master` SHA
`7f0151c2586b4fc95d82cd06560f9ccd7ae2c821`, manifest
`frontend/src/content/publicContent.json`, `docs/seo/public-content.md`,
`docs/seo/growth-analytics-foundation.md` и live host `https://your-fitness-coach.ru/`.

В manifest 24 public entries: landing, 4 product pages, knowledge index, 14 guides, exercise
index и 3 exercise pages. Live sitemap содержит 25 canonical URLs (включая `/articles`).
`robots.txt`, `sitemap.xml` и основные public routes отвечают `200`; SEO smoke script подтвердил
25 canonical sitemap URLs. Private/API routes в sitemap не включаются.

| Current page | Current intent | Coverage gap | Action for future implementation |
| --- | --- | --- | --- |
| `/` | product overview, Web + Telegram entry | Не показывает конкретный calculator/program job | Оставить product landing; добавить только доказанный compact entry point |
| `/training` | программы, план и запись тренировок | Diary/app intent и save loop недостаточно explicit для search visitor | Усилить copy/IA и deep links; не создавать отдельный diary page в wave 1 |
| `/nutrition` | current KBJU orientation/calculator | Нет отдельной acquisition page для calorie/protein variants; health trust boundary | Усилить existing page; new calculator URL только после distinct tool contract |
| `/progress` | записи результатов, нагрузки, measurements | Не является top-of-funnel calculator/program page | Оставить supporting page; связать с program/trainer flows |
| `/for-trainers` | trainer workspace: programs, invites, client progress | Commercial CRM language и proof/FAQ могут быть сильнее | Усилить existing page; не создавать `/for-trainers/crm` без отдельного job |
| `/knowledge` | educational catalog | Частично покрывает RIR, Full Body/Split, KBJU, heart rate, hydration | Использовать как context layer; link only to relevant tools/programs |
| `/knowledge/...` | durable guides with sources/limits | Нет 1ПМ и volume guides; некоторые intents ведут к future tools | Add guides only beside a useful asset, not article volume for its own sake |
| `/articles` | public article index contract | Current SEO research does not prove article-first opportunity | Не превращать в keyword doorway; not Wave 1 |
| `/exercises` | allowlisted exercise catalog | Только bench press, lat pulldown, squat; thin expansion risk | Expand one verified canonical page at a time with useful technique/media |
| `/exercises/<slug>` | technique, errors, safety, domain data | No public add-to-workout action yet | Add CTA only when public-to-product flow exists; otherwise informational |

### Demand evidence policy

В исследовании нет официальных search-volume numbers. `Yandex Wordstat` без owner authentication
перенаправляет на Passport; после повторных automated-like queries Yandex SERP показал SmartCaptcha.
Один initial Yandex snapshot по `калькулятор 1пм` был доступен и показал utility SERP, но число
`19 млн результатов` не является frequency и в ranking не используется. Google UI snapshots показывают
organic composition и related queries, но Google Keyword Planner data не собиралась. Поэтому:

- `demand_value` в CSV = `UNKNOWN`;
- `demand_status` = `unknown_wordstat_unavailable`;
- SERP result count, third-party metrics и snippets не выдаются за frequency;
- detailed manual export contract находится в `manual-wordstat-input.md`.

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

`Search demand` is recorded separately as qualitative SERP signal plus `UNKNOWN` demand confidence.
Scores are 0–5. Health/claims complexity is a penalty applied to the tier decision, not disguised
as a demand score. A cluster cannot become a confirmed launch decision until Wordstat export and
owner review are available.

| Cluster | SERP signal | Product fit | Conversion | Attainability | Readiness | Linking | Geo | Health risk | Opportunity proxy |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| A 1ПМ/working weights | many calculator/formula results; calculator intent clear | 5 | 5 | 4 | 3 | 5 | 4 | low–medium | 87 |
| C Full Body / beginner program | article + video + template mix; strong program action | 5 | 5 | 4 | 3 | 5 | 4 | low–medium | 87 |
| B training volume | several interactive calculators and tonnage tools | 5 | 4 | 4 | 3 | 5 | 4 | low–medium | 83 |
| D trainer workspace / CRM | commercial products and feature-led landing pages | 5 | 5 | 3 | 3 | 4 | 4 | low | 81 |
| E exercise technique | broad informational/video SERP; current YFC catalog is credible base | 4 | 3 | 3 | 3 | 5 | 5 | medium | 75 |
| H workout diary/app | app stores, roundups and product pages; high competition | 4 | 4 | 2 | 3 | 4 | 5 | low | 73 |
| F KBJU/calorie/protein | calculators mixed with nutrition/medical trust domains | 4 | 4 | 3 | 2 | 4 | 5 | high | 69 |
| G pulse zones | interactive tools exist, but claims/medical context is sensitive | 3 | 3 | 3 | 2 | 4 | 4 | high | 60 |

## Cluster conclusions

### A — 1ПМ, RM and working-weight tools

Dominant intent is `tool/calculator`, with adjacent informational formula and percentage queries.
Google and Yandex both show multiple calculators, not only articles: Start-fit, Body1, GeneticLab,
AnatomyStudy, Sport-iv, Inspire2, Zozhnik and other utility pages. The gap is not another formula
explanation; it is a trustworthy result with explicit formula/limitations, exercise context,
percentage table, and a future save-to-program path.

Recommended canonical hypothesis: `/calculators/1rm`. Do not create separate URLs for `жим`,
`присед`, `становая` until data shows a materially different intent; exercise selector/sections
should prevent cannibalization. Product dependency: calculator result and `calculator_saved` flow
do not exist yet.

### B — training volume and tonnage

Intent is mostly `tool/calculator` plus informational planning (`sets per muscle group`). SERP has
interactive tools from AnatomyStudy, Start-fit, OnlyPump, Calcal and Sport-iv. YFC can differentiate
with a transparent definition of volume, per-exercise/per-week views, and direct program context,
not a generic tonnage number. Need a separate contract for what YFC can calculate from planned versus
completed sets; do not imply an evidence-based optimal range without sources.

### C — 3-day and beginner programs

Intent splits into `program/template` and informational advice. `Full Body 3 раза в неделю` is the
cleanest first candidate because it has a bounded schedule and a clear save action. Google SERP
contains InstructorPRO, Maxler, Dzen/Championat, Reddit and video results; the page must be more
useful than a text list by exposing days, exercises, progression notes and a future `public_program_saved`
flow. Keep beginner, mass and weight-loss variants under one information architecture until Wordstat
proves separate dominant intents.

### D — trainer workspace / CRM

Intent is `commercial investigation` / `transactional product`. Fitness1C, Rubitime, YCLIENTS,
Fitbase, Bitrix24 and similar products compete on booking, CRM, analytics and client management.
YFC's differentiator is a focused trainer workflow for programs, progress and invite—not a promise
of bookings, payments or full club CRM. Strengthen `/for-trainers` with concrete current actions and
proof; a `/for-trainers/crm` page would be misleading while the product scope remains narrower.

### E — exercise technique

SERP is informational and media-heavy: Fitness3000, Sport-Express, Nef, PlanetaSport, DDX and
videos compete with technique/how-to pages. Existing YFC exercise cards are a sound canonical base
because their data comes from the shared domain catalog. Expand only when the entry has technique,
breathing, common errors, safety limits, equipment/variant and genuinely useful media or diagrams.
The `Добавить упражнение в тренировку` CTA is a future dependency, not a current promise.

### F — KBJU, calorie and protein tools

Intent is tool-led but high-trust: Alena RightFood, Smart Eat, XFIT, WillFood, PowerTeam and
nutrition/medical sources appear. `/nutrition` already owns a product-calculator story and should be
strengthened before a second canonical URL. Any new page needs transparent assumptions, source/reviewer
policy, health limitations and no individualized medical claim. First-wave status: supporting
improvement, not an independent launch.

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
distinct public entry and save funnel are implemented.

## Top 10 opportunity clusters

1. `калькулятор 1пм` / `рассчитать рабочий вес` — tool result plus future save.
2. `full body 3 раза в неделю` — bounded program with clear product action.
3. `калькулятор объема тренировки` / `тоннаж тренировки` — plan/completed-volume utility.
4. `приложение для фитнес тренера` / `CRM для фитнес тренера` — focused trainer workspace.
5. `жим лежа техника` and verified exercise technique pages — canonical catalog expansion.
6. `программа тренировок для новичка` — should share the program IA with Full Body, not duplicate it.
7. `дневник тренировок` / `запись рабочих весов` — strengthen `/training` before a new landing.
8. `калькулятор кбжу` / `сколько белка нужно` — strengthen `/nutrition` with health-safe source policy.
9. `калькулятор пульсовых зон` — real tool gap, but deferred for claims risk.
10. adjacent `проценты от 1пм` / `формула 1пм` — sections of the 1ПМ asset, not separate pages.

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

1. Owner review of this packet and Wordstat export.
2. A future product/SEO implementation task for one canonical 1ПМ asset plus its save-flow contract.
3. A separate bounded task for one Full Body program asset and public-to-product save semantics.
4. A later training-volume spike that first fixes the planned-vs-completed volume definition.
5. Conditional follow-up for nutrition/cardio only after source, reviewer and claims decisions.

Task 241B is intentionally not started by this research task.

## Sources used

- Live YFC: https://your-fitness-coach.ru/
- YFC public-content contract: `docs/seo/public-content.md`
- YFC growth/analytics contract: `docs/seo/growth-analytics-foundation.md`
- Wordstat entry point: https://wordstat.yandex.ru/ (authentication unavailable in this session)
- Google UI snapshots, examples: https://www.google.com/search?q=%D0%BA%D0%B0%D0%BB%D1%8C%D0%BA%D1%83%D0%BB%D1%8F%D1%82%D0%BE%D1%80+1%D0%BF%D0%BC&hl=ru&gl=ru and https://www.google.com/search?q=full+body+3+%D1%80%D0%B0%D0%B7%D0%B0+%D0%B2+%D0%BD%D0%B5%D0%B4%D0%B5%D0%BB%D1%8E&hl=ru&gl=ru
- Yandex UI snapshot: https://yandex.ru/search/?text=%D0%BA%D0%B0%D0%BB%D1%8C%D0%BA%D1%83%D0%BB%D1%8F%D1%82%D0%BE%D1%80+1%D0%BF%D0%BC&lr=2
- Competitor URLs and query-level evidence are listed in `serp-competitor-matrix-ru-cis.md`.
