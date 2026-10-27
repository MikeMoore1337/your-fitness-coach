# Issue #873 final AFTER evidence metrics

- Implementation revision: `00e2701adcb5ae889f27aa72555265628c19df25`.
- Base used for the PR sync: `ace951a13c2672189fdc464e92bd12b6371f3914` (`origin/master` at
  capture time).
- Fixture: `frontend/tests/e2e/progress-experience.spec.ts::mockProgress`.
- Browser: Playwright Chromium with reduced motion; WebKit is covered separately by the
  cross-browser/mobile regression suites, but this package contains Chromium screenshots only.
- Themes: light and dark.
- Viewports: 320×844, 360×844, 393×844, 430×844, 1024×1000, 1280×1000, 1440×1000 and
  1920×1000.
- Captures: 144 total — 112 default, 28 expanded and 4 `action-add-measurement`.
- Distribution: 72 light and 72 dark; 20 captures per section except Body (24, including the
  action state); 30 captures at each expanded-state width (393 and 1440).
- Views: `overview`, `body`, `training`, `nutrition`, `cardio`, `wellbeing`, `history`.
- Region: `.progress-summary` for Overview and `.progress-details` for detail views.
- Scroll: `window.scrollY=0` after `document.fonts.ready` and two animation frames.
- Format: JPEG, quality 88.

## Audit record

- Manifest/file audit: all 144 manifest entries have a corresponding JPEG; no capture was
  overwritten from the previous `paired-20261018` package.
- Lime-edge audit: the all-Progress Playwright audit now evaluates Weekly Review surfaces with
  no broad class exceptions; the targeted `lint:lime-edges` guard and focused Vitest positive/
  negative fixtures passed.
- Body layout audit: the dedicated mobile test uses real `getBoundingClientRect()` and computed
  styles at 320/393/430 px, checks token-sized sibling gaps, uniform 1px borders/radii, no
  horizontal overflow and reachability above the fixed dock.
- Focused visual review: light/dark Body expanded states, desktop expanded Body, add-measurement
  state and dark expanded Wellbeing were spot-checked against the captured matrix; the full
  matrix is available in the gallery and manifest.

## Fixture facts

- Body: four weight points and two waist points; circumference confidence remains limited.
- Nutrition: 18 days have a confirmed diary status; 9 days have usable data for averages. The
  report therefore keeps `18/30` and `9/30` distinct and labels their definitions.
- Cardio: three completed sessions in the requested period; durations 30/45/45 minutes and
  distances 3/4/5 km. The visible row count matches the summary badge.
- History: two completed workouts on different dates, with separate exercises, 4/5 sets and
  1480/1730 kg volumes; totals are 2 workouts, 9 sets and 3210 kg.

## Interpretation and gates

This is synthetic browser evidence for visual review. It does not prove physical iPhone/Safari,
native Telegram Mini App, VoiceOver, native keyboard/safe-area behavior, real-device touch,
production data, production deployment or owner visual acceptance. Owner AFTER visual acceptance
is still pending; the PR remains Draft and merge/deploy are separate gates.
