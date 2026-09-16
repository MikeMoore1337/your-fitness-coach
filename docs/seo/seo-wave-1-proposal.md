# SEO Wave 1 proposal

Task 241A, research, and Task 241B, bounded first implementation.
Status: 241A evidence is integrated; 241B implements the owner-approved public `/nutrition`
calculator slice. Production status remains governed by the task delivery lifecycle.

## Decision

Owner-provided Yandex Wordstat evidence is integrated for the period `15.08.2026–15.09.2026`,
device filter `все устройства`, with Russia as the primary geography. The quoted metric means
Wordstat's quoted/fixed-word-count frequency: the `"..."` operator fixes the word count but not
necessarily order or word form. It is not Google Ads exact match.

Wave 1 contains seven assets, but only two are new product-led candidates. The other five are
existing-page improvements or bounded catalog work. The ordering below combines actual Wordstat
evidence with product fit, health/claims penalty, implementation cost and cannibalization risk.
Wordstat demand and the existing `priority_score` opportunity proxy are shown separately; neither
is a traffic forecast or production authorization.

## Ranked Wave 1: 7 primary assets

| Rank | Asset / canonical hypothesis               | Type                        | RU Wordstat evidence                                                                    | Why now                                                                                                             | Product/opportunity separation                                                    | Health / cost / cannibalization gate                                           |
| ---: | ------------------------------------------ | --------------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
|    1 | `/nutrition` + knowledge links             | Existing page improvement   | `калькулятор кбжу`: 16127 broad / 4763 quoted (29.5%)                                   | Strongest observed cluster already has a canonical product page; improve it before creating a second calculator URL | Existing page fit; current `priority_score` 69 is not comparable to the frequency | High YMYL/claims penalty; M; avoid `/calculators/kbju` duplication             |
|    2 | `/exercises/bench-press`                   | Existing page exemplar      | `жим лежа техника`: 2943 / 528 (17.9%)                                                  | Material technique demand and a real canonical exercise page; establish the quality pattern first                   | Existing catalog fit; `priority_score` 75                                         | Medium claims/safety penalty; M; no mass-generated exercise pages              |
|    3 | `/training`                                | Existing page improvement   | `дневник тренировок`: 3038 / 456 (15.0%)                                                | Good acquisition cluster maps to current program -> workout -> logging -> progress story                            | Existing product path; `priority_score` 73                                        | Low claims penalty; S/M; no duplicate diary landing                            |
|    4 | `/calculators/1rm`                         | New interactive calculator  | `калькулятор 1пм`: 363 / 261 (71.9%)                                                    | Modest volume but unusually pure BOFU intent and clear future save-to-program value                                 | New product contract; `priority_score` 87                                         | Low–medium claims penalty; M; formula variants remain one canonical URL        |
|    5 | `/programs/full-body-3-days`               | New public program asset    | `программа тренировок 3 раза в неделю`: 1351 / 32 (2.4%); Full Body seed 20 / `NO_DATA` | Broad Russian program cluster is meaningful; use Full Body as concept/secondary wording                             | New public program read model; `priority_score` 87                                | Low–medium claims penalty; M; no gender/goal/country duplicates                |
|    6 | `/for-trainers`                            | Existing page improvement   | `NO_DATA` — no usable owner export for requested trainer variants                       | Product fit and commercial SERP justify a focused truthful improvement, not a volume claim                          | Existing product fit; `priority_score` 81                                         | Low claims penalty; S/M; no `/for-trainers/crm` without distinct job           |
|    7 | `/exercises` + one verified next expansion | Bounded catalog improvement | Reuse the bench-press evidence pattern; no mass-demand claim                            | Apply the exemplar structure only to another verified canonical exercise                                            | Existing catalog fit; `priority_score` 75 family proxy                            | Medium safety/content cost; M; stop if useful canonical content is unavailable |

### What is explicitly not in Wave 1

- standalone `/calculators/kbju`: first strengthen `/nutrition` and decide whether a distinct tool
  exists;
- `/calculators/training-volume` and a standalone tonnage calculator: direct calculator evidence is
  only 5 broad with no quoted export; tonnage is 181 broad / 2 quoted and needs a domain contract;
- `/calculators/heart-rate-zones`: defer for claims/health-risk and reviewer contract;
- `/workout-diary` or `/fitness-app`: duplicate risk while `/training` is underused;
- country-specific pages for Russia/Kazakhstan/Belarus without regional intent evidence;
- a page for every exercise/variant or every spelling of Full Body;
- AI-generated page volume, fake FAQ/reviews/authors, or private-data indexation.

## Existing-page improvement backlog

### `/training`

Add a search-readable section that states the current job in plain Russian: choose/create a program,
open a workout, record sets and see the result. Keep one primary CTA. Link contextually to the
Full Body program asset when it exists and to relevant exercise/knowledge pages. Do not call the
feature a generic “diary app” if the current UI does not prove that exact breadth.

### `/nutrition`

Task 241B makes current calculator assumptions and limitations visible in the public fallback and
page copy, with the calculation available without authentication. The page links to the KBJU
reference and food-source guide. `КБЖУ`, calories and protein variants remain on one canonical
`/nutrition` URL; the observed demand does not authorize a duplicate calculator URL or
individualized medical/dietological promise language.

### `/exercises/bench-press`

Use the existing canonical exercise page as the first exemplar for `техника` intent: technique,
breathing, common errors, safety limits, equipment/variants, useful media or diagrams, and clear
source/license state. Do not imply a public add-to-workout action until that product flow exists.

### `/for-trainers`

Lead with current sequence: trainer mode -> create/assign program -> invite client -> inspect
progress. Add a compact “what this is not” boundary if needed: not a booking marketplace, payment
CRM or generic club ERP. The commercial SERP rewards concrete feature proof; it does not authorize
YFC to claim features that are absent.

### `/exercises` and existing cards

Use the bench-press page as the quality gate before bounded expansion. Improve information
architecture and internal links before adding volume. Expand only records that have verified
technique, breathing, errors, safety, equipment, difficulty and source/license state.
The exercise page can later own an `Добавить упражнение` action, but Wave 1 research must not imply
that action exists.

### `/knowledge`

Use existing guides as the explanation layer for tools: RIR and progressive overload beside 1RM;
Full Body/Split beside the program; KBJU/protein beside nutrition. Add a new guide only where it
explains a real product asset or closes a current user question.

## Implementation dependencies and split

### The Task 241E 1RM slice includes

- a bounded client-side calculation contract and unit/error bounds;
- public fallback metadata and canonical URL;
- accessible result state and formula limitations;
- product action only if save/auth flow is already specified;
- route/sitemap/internal-link regression tests;
- no fabricated performance claim.

If saving needs a new schema/API contract, split it into a product contract/data task first; do not
smuggle it into a content-only task.

### Full Body program

Separate content and product read-model decisions if the current program model cannot safely expose
public data. One canonical 3-day program may contain beginner/goal notes; no gender/country/query
duplicates until demand data and owner decision support them.

### Training volume

Run a bounded domain spike before implementation: define planned vs completed volume, incomplete set
data, units, aggregation period and interpretation. A number without a clear contract is not a
useful SEO asset.

### Trainer and nutrition improvements

These can be separate small implementation tasks after owner review. Trainer copy needs current
feature evidence; nutrition needs source/reviewer/claims decision. Neither requires production env
changes in this research packet.

## Future measurement contract

The repository already has implemented product goals for registration, first workout, trainer
activation, client invite and related actions. The following names remain future-only and must not
be reported as implemented by this task:

| Event                             | Intended moment                    | Gate                        |
| --------------------------------- | ---------------------------------- | --------------------------- |
| `calculator_saved`                | result is successfully saved       | authenticated save succeeds |
| `public_program_opened`           | useful public program is opened    | public read model exists    |
| `public_program_saved`            | program is saved successfully      | save contract exists        |
| `exercise_added_from_public_page` | exercise is added from public page | add flow exists             |

`calculator_started` and `calculator_result` are implemented by Tasks 241B and 241E as action-only events;
their exact trigger and no-payload boundary are documented in `growth-analytics-foundation.md`.

Wave KPI sequence should be `indexed URLs -> non-brand impressions/clicks -> relevant action ->
registration -> activation`, not traffic alone. Baseline for comparison remains GSC T0:
0 clicks/0 impressions for settled 28 days through 2026-09-11.

## Internal linking graph

```text
1RM calculator <-> RIR/progressive-overload guides <-> exercises <-> Full Body program <-> /training
Full Body program <-> /training <-> exercises <-> progressive-overload guide
/for-trainers <-> /progress <-> /training
/nutrition <-> KBJU/protein guides
```

Every edge must be useful in both directions and point to an existing canonical destination. Do not
add links merely to place keywords on every page.

## Recommended follow-up task sequence

1. Owner review of Task 241A and this evidence-informed Wave 1.
2. 241B: public `/nutrition` calculator and SEO acquisition slice, delivered through the normal
   task lifecycle.
3. Separate trainer-page copy/IA task and nutrition/cardio risk-reviewed tasks only as evidence and
   owner decisions support them.
4. Separate volume-definition spike if the owner later keeps training-volume calculator in scope.
