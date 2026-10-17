# Contract: feasibility of automatically calculated KBJU (#1071)

The Mifflin-St Jeor estimate and goal multiplier set a **starting energy budget**, not a clinical prescription.

## Invariant

For a calculated target, the protein/fat energy budget must be compatible with the goal energy budget **before** calories and macro targets are saved or shown as a valid result.

The calculator MUST NOT silently increase calories to make weight-based protein and fat allocations fit. In particular, it must never transform the initial 85% deficit into a surplus for a fat-loss goal. The owner-approved recomposition coefficient remains `0.95`.

If `4 × protein_g + 9 × fat_g > target_calories`:
- The API rejects an explicitly requested calculation with HTTP 400 and a specific explanatory error; it does not commit a target or alter historical versions.
- The TypeScript calculator returns `valid=false`, `estimate=null` and an explanation, so the Save action is disabled and the public calculator does not display a misleading result.
- During *automatic* recalculation from a new body measurement/profile update, the measurement remains saved; the previous target is retained, and a notification explains why no new calculated target was created.

The standard gram-per-actual-kg protein/fat heuristics are **not validated** for marked adiposity or extreme anthropometry. They must not be silently replaced with an invented reference body weight. A separate scientific-policy review is tracked in #1072.

## Regression contract

- The observed previously-accepted combination `female, 350 kg, 100 cm, 100 y, mostly_sitting, up_to_4000, no trainings, fat_loss` is **infeasible**, not an authorized 5600 kcal plan.
- Feasible adult estimates retain existing Mifflin, activity, MET, goal-multiplier and rounding semantics; `P*4 + F*9 + C*4` differs from target only by rounding.
- Backend and frontend must agree on validity and outcomes.
- Never mutate trainer/manual/adaptive or historical versions via this change.

Scientific background for upcoming validation: https://pubmed.ncbi.nlm.nih.gov/15883556/ ; https://pubmed.ncbi.nlm.nih.gov/28642676/ ; https://www.niddk.nih.gov/health-information/weight-management/body-weight-planner . These papers support *considering prediction uncertainty*, not the claim that this particular guard has undergone clinical validation.

## Scope note

This narrow correction does **not** redesign the user interface or change the empirically unvalidated macro basis. Issue #1072 covers reference weight/composition, fat and carbohydrate adequacy, double-counted activities and longitudinal expenditure uncertainty.
