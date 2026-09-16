# SEO Wave 1 proposal

Task 241A, research-only.
Status: proposal for owner review; no production implementation is included.

## Decision

Wave 1 should contain seven assets, but only three are new product-led candidates. The other four
are existing-page improvements or bounded catalog work. This keeps the wave useful without creating
near-duplicate URLs before Wordstat evidence and product contracts exist.

Demand is `UNKNOWN` for every candidate because authenticated Yandex Wordstat data was unavailable.
The ranking below is therefore an opportunity proxy using product fit, conversion intent, SERP
attainability, content readiness, linking potential and geography. It is not a promise of traffic.

## Ranked Wave 1: 7 primary assets

| Rank | Asset / canonical hypothesis | Type | Why now | Primary CTA | Product integration required | Complexity | Content/source requirements | SERP gap | Success metric |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `/calculators/1rm` | New interactive calculator | Strongest clear tool/BOFU intent; Google and Yandex both show utility SERP | `Сохранить результат в программу` | 1RM calculation contract, formula/limits, `calculator_started`, `calculator_result`, later `calculator_saved` | M | Formula provenance, exercise/unit validation, uncertainty and technique disclaimer | Competitors stop at formula or result; few connect result to YFC program | calculator result rate; save rate; registration -> first workout |
| 2 | `/programs/full-body-3-days` | New public program asset | Bounded schedule, strong program intent, natural bridge to exercises and training | `Открыть программу` / later `Сохранить в YFC` | Public program read model, exercise references, `public_program_opened`, later `public_program_saved` | M | Original Russian program, progression/limits, audience assumptions, no guaranteed result | SERP has articles/videos but not a coherent editable product path | open -> registration; open -> save; first workout |
| 3 | `/calculators/training-volume` | New interactive tool | Existing competitors prove tool intent; product has training data that can become useful | `Посмотреть объём программы` | Explicit planned-vs-completed volume model; no unsupported “optimal” claims | M/L | Define sets × reps × load, aggregation, source-backed interpretation | Most tools output tonnage without explaining data meaning or next action | calculator completion; repeat use; program engagement |
| 4 | `/for-trainers` | Existing page improvement | Commercial investigation is valuable and current YFC already has programs/progress/invites | `Включить режим тренера` | Existing `trainer_application_started/completed`, `client_invited` only | S/M | Current feature proof, workflow screenshots only if real, honest scope/FAQ | Competitors are broader CRM/booking suites; YFC can be more focused and truthful | trainer activation; activation -> client_invited |
| 5 | `/exercises` + one verified expansion | Existing catalog improvement | Exercise SERP is broad, media-led, and current public catalog is a canonical domain source | `Добавить упражнение в тренировку` only when flow exists | Public-to-product add action is future; shared exercise catalog remains source | M | Technique, breathing, errors, safety, equipment/variants, lawful media | Competitors have volume but inconsistent canonical data; do not mass-generate pages | non-brand impressions; page engagement; add action after implementation |
| 6 | `/training` | Existing page improvement | Owns workout diary/app intent better than a duplicate diary landing | `Начать тренировку` | Existing `first_workout_started`; no new future event until flow is proven | S/M | Explain plan -> record -> progress path, current features only | App SERP is saturated; YFC should prove one integrated job | landing -> registration; registration -> first workout |
| 7 | `/nutrition` + knowledge links | Existing page improvement | Existing calculator and KBJU guides already own product context; avoids YMYL cannibalization | Current nutrition action; future save only after contract | Existing nutrition flow; source/reviewer contract before new calculator URL | M | Assumptions, limits, authoritative sources, no individualized medical claims | Competitors have calculators but trust/limits are inconsistent | nutrition action completion; registration/activation |

### What is explicitly not in Wave 1

- standalone `/calculators/kbju`: first strengthen `/nutrition` and decide whether a distinct tool
  exists;
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

Make current calculator assumptions and limitations visible in the public fallback and page copy.
Link to the KBJU reference and protein/recomposition guide. Keep `КБЖУ`, calories and protein
variants as sections until Wordstat and product contracts prove a separate canonical tool. Avoid
medical/dietological promise language.

### `/for-trainers`

Lead with current sequence: trainer mode -> create/assign program -> invite client -> inspect
progress. Add a compact “what this is not” boundary if needed: not a booking marketplace, payment
CRM or generic club ERP. The commercial SERP rewards concrete feature proof; it does not authorize
YFC to claim features that are absent.

### `/exercises` and existing cards

Improve information architecture and internal links before adding volume. Expand only records that
have verified technique, breathing, errors, safety, equipment, difficulty and source/license state.
The exercise page can later own an `Добавить упражнение` action, but Wave 1 research must not imply
that action exists.

### `/knowledge`

Use existing guides as the explanation layer for tools: RIR and progressive overload beside 1RM;
Full Body/Split beside the program; KBJU/protein beside nutrition. Add a new guide only where it
explains a real product asset or closes a current user question.

## Implementation dependencies and split

### A future 1RM task can be one bounded vertical slice if it includes

- a server-trusted calculation contract and unit/error bounds;
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
activation, client invite and related actions. The following names are future-only and must not be
reported as implemented by this task:

| Event | Intended moment | Gate |
| --- | --- | --- |
| `calculator_started` | user begins a public calculator | calculator flow exists and event is typed |
| `calculator_result` | validated result is shown | result is actually computed |
| `calculator_saved` | result is successfully saved | authenticated save succeeds |
| `public_program_opened` | useful public program is opened | public read model exists |
| `public_program_saved` | program is saved successfully | save contract exists |
| `exercise_added_from_public_page` | exercise is added from public page | add flow exists |

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

1. Owner review of Task 241A and manual Wordstat export.
2. 241B (future, not started): implement the owner-approved first product-led asset, likely 1RM or
   Full Body depending on volume evidence and product contract.
3. Separate volume-definition spike if the owner keeps training-volume calculator in scope.
4. Separate trainer-page copy/IA task and nutrition/cardio risk-reviewed tasks only as evidence
   supports them.
