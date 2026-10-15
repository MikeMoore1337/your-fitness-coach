# Issue #1002 — компактная computed-style сводка

Baseline: `origin/master` `474d920d29e373043d4216586095ad7c90f7eb2e`; fixture data synthetic; browser audit local-only.

## Matrix

| Browser/theme | Capture attempts | DOM captures | Horizontal overflow |
|---|---:|---:|---:|
| Chromium Dark | 72 | 32 | 0 |
| Chromium Light | 72 | 30 | 0 |
| WebKit Dark | 72 | 24 | 0 |
| WebKit Light | 72 | 24 | 0 |

Widths: `320/360/390/393/430/1440 px`. WebKit active-workout capture is valid; report/Nutrition/Cardio WebKit routes remained loading/authorization in this run and are `NOT_PROVEN`.

## Key computed values

| Screen | Selector | Computed evidence | Classification |
|---|---|---|---|
| Today active | `.today-workout-focus__header` | `border-bottom: 2px solid rgb(178, 245, 32)`; other borders `0`; rect `369×70` at 393 | C — active state, preserve |
| Today active | `.active-workout-set.is-current` | all four borders `1px solid rgb(178, 245, 32)`; `box-shadow: rgb(178, 245, 32) 3px 0 0 0 inset`; rect `369×468` at 393 | C — current set, preserve |
| Today cardio | `.cardio-log` | `border-top: 3px solid rgb(178, 245, 32)`; other sides `1px` neutral; rect `369×632.03` at 393 | A-05 — remove only top edge |
| Progress report | `.progress-report-factual-summary` | `border-left: 3px solid rgb(178, 245, 32)` + neutral `1px` frame; rect `321×530.59` at 393 | A-02 — remove only left edge |
| Progress report | `.progress-report-program` | `border-left: 3px solid rgb(178, 245, 32)`; rect `321×314` at 393 | A-03 — remove only left edge |
| Progress report | `.progress-report-exercises article` | two visible cards; each `border-left: 3px solid rgb(178, 245, 32)` + neutral `1px` frame | A-04 — remove only left edge |
| Progress report | `.progress-report-confidence` | `border-left: 3px solid rgb(178, 245, 32)` | C — data completeness semantic, preserve |
| Nutrition | `.ai-coach-contextual-entry` | `border-left: 3px solid rgb(178, 245, 32)`; rect `366×183` at 390 Dark | A* — defer to #1003 |
| Progress | `.progress-insights__column--good` | `border-left: 3px solid rgb(178, 245, 32)` | C — semantic success, preserve |
| Progress | `.data-viz-chart__selection` | `border-inline-start: 3px solid rgb(178, 245, 32)` | C — selected data point, preserve |
| Profile | `.app-mobile-header__profile` | all four borders `2px solid rgb(178, 245, 32)` | B — normal uniform frame, preserve |

Raw JSON attempts remain in the local audit worktree but are intentionally not committed: each file exceeds the repository pre-commit 500 KB added-file limit. This compact summary is the reviewable evidence surface for the Draft PR.
