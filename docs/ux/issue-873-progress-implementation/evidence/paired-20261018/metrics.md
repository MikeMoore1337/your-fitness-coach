# Issue #873 final AFTER evidence metrics

- Capture revision: `2f1cb8930e07a41a8b7303cb4c8b63ad45f65b82`.
- Fixture: `frontend/tests/e2e/progress-experience.spec.ts::mockProgress`.
- Browser: Playwright Chromium, reduced motion; WebKit coverage is recorded by the targeted
  cross-browser E2E run, but this package contains Chromium screenshots only.
- Themes: light and dark.
- Viewports: 320×844, 360×844, 393×844, 430×844, 1024×1000, 1280×1000, 1440×1000 and
  1920×1000.
- Captures: 144 total — 112 default, 28 expanded and 4 `action-add-measurement`.
- Views: `overview`, `body`, `training`, `nutrition`, `cardio`, `wellbeing`, `history`.
- Region: `.progress-summary` for overview and `.progress-details` for detail views.
- Scroll: `window.scrollY=0` after `document.fonts.ready` and two animation frames.
- Format: JPEG, quality 88.

## Fixture facts

- Body: four weight points and two waist points; circumference confidence remains limited.
- Nutrition: 18 days have a confirmed diary status; 9 days have usable data for averages. The
  report therefore keeps `18/30` and `9/30` distinct and labels their definitions.
- Cardio: three completed sessions in the requested period; durations 30/45/45 minutes and
  distances 3/4/5 km. The visible row count matches the summary badge.
- History: two completed workouts on different dates, with separate exercises, 4/5 sets and
  1480/1730 kg volumes; totals are 2 workouts, 9 sets and 3210 kg.

## Interpretation

This is synthetic browser evidence for visual review. It does not prove physical iPhone/Safari,
native Telegram Mini App, VoiceOver, real touch, production data, production deployment or
owner visual acceptance. The historical paired package at `../paired-20261017/` uses the prior
one-workout fixture and must not be presented as the final two-workout comparison.
