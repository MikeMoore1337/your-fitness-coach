# Issue #1002 — AFTER evidence для тонких равномерных граней

Пакет снят после fresh frontend build на synthetic/test-only данных. Базовая ревизия
`origin/master`: `8a5c955400de87eed8c92974bd196a8343c6cd35`. Кодовый commit реализации:
`1c05a6bbbe799ab5f0057e9478e968493242ecc4` (`fix(ui): remove thick one-sided lime edges (#1002)`).

Это техническое AFTER-доказательство, а не owner visual acceptance, merge или release approval.
AI Coach в этом worktree не менялся и остаётся скрытым после PR #1021.

## Матрица

- Report и Today Cardio: Chromium и WebKit, Light/Dark, ширины `320`, `360`, `390`, `393`,
  `430` и `1440 px`; в каждом проходе проверены computed CSS и `scrollWidth <= innerWidth`.
- Active Workout: Chromium и WebKit, Light/Dark, ширины `320`, `360`, `393` и `430 px`;
  проверены current-set frame, RIR и рабочий timer.
- Mock TMA critical regression: Chromium прошёл 13 сценариев; после обновления только A-06
  golden отдельный Active Workout visual test прошёл. WebKit mobile-regression не смог открыть
  локальный preview в отведённые 30 секунд и не используется как mobile proof.
- Physical iPhone/Safari, native Telegram, VoiceOver, production runtime и реальный 200% browser
  zoom этим пакетом не подтверждаются.

## Representative AFTER captures

| Экран | Browser | Viewport | Theme | Кадр |
| --- | --- | ---: | --- | --- |
| Progress report, A-01…A-04 | Chromium | 393 | Dark | [PNG](report-393-dark-after.png) |
| Progress report, A-01…A-04 | Chromium | 393 | Light | [PNG](report-393-light-after.png) |
| Progress report, A-01…A-04 | Chromium | 1280 | Dark | [PNG](report-1280-dark-after.png) |
| Progress report, A-01…A-04 | Chromium | 1280 | Light | [PNG](report-1280-light-after.png) |
| Today Cardio, A-05 | Chromium | 390 | Dark | [PNG](cardio-390-dark-after.png) |
| Today Cardio, A-05 | Chromium | 390 | Light | [PNG](cardio-390-light-after.png) |
| Today Cardio, A-05 | Chromium | 1440 | Dark | [PNG](cardio-1440-dark-after.png) |
| Today Cardio, A-05 | Chromium | 1440 | Light | [PNG](cardio-1440-light-after.png) |
| Active Workout, current + RIR | Chromium | 393 | Dark | [PNG](active-393-dark-rir-chromium.png) |
| Active Workout, current + RIR | Chromium | 393 | Light | [PNG](active-393-light-rir-chromium.png) |
| Active Workout, timer | Chromium | 393 | Dark | [PNG](active-393-dark-timer-chromium.png) |
| Active Workout, timer | Chromium | 393 | Light | [PNG](active-393-light-timer-chromium.png) |
| Active Workout, current + RIR | WebKit | 393 | Dark | [PNG](active-393-dark-rir-webkit.png) |
| Active Workout, current + RIR | WebKit | 393 | Light | [PNG](active-393-light-rir-webkit.png) |

Исторические BEFORE кадры и исходная классификация находятся в [audit-пакете PR
#1023](../1002-lime-edge-audit-20261016/README.md). Все данные в обоих пакетах synthetic.

## A-кейсы: было / стало / сохранено / не доказано

| ID | Было | Стало | Сохранено | Не доказано |
| --- | --- | --- | --- | --- |
| A-01 | `.progress-report-overview`: `border-left: 3px` lime | `border-left-width: 0px`, `border-left-style: none` | padding, фон и layout | physical device |
| A-02 | `.progress-report-factual-summary`: lime `3px` слева + обычный frame | левая грань `1px solid`, цвет совпадает с верхней гранью | равномерная рамка и содержимое | owner visual acceptance |
| A-03 | `.progress-report-program`: lime `3px` слева | `border-left-width: 0px`, `border-left-style: none` | карточка и layout | production runtime |
| A-04 | две `.progress-report-exercises article` с lime `3px` слева | обе карточки: все четыре стороны `1px`; левая совпадает с верхней | две карточки, рамки и структура | VoiceOver |
| A-05 | `.cardio-log`: lime `3px` сверху, остальные стороны `1px` | все четыре стороны `1px solid` одного цвета | focus duration и disabled validation CTA | native Telegram |
| A-06 | current set: `box-shadow: inset 3px 0 0 lime` + `1px` current border | `box-shadow: none`; current border остаётся `1px` lime | current semantics, RIR `aria-pressed`, rest timer, keyboard/safe-area regression scope | real iPhone/Safari |

## Регрессии и границы

- Targeted computed assertions находятся в [progress-report.spec.ts](../../../../../frontend/tests/e2e/progress-report.spec.ts), [today-dashboard.spec.ts](../../../../../frontend/tests/e2e/today-dashboard.spec.ts) и [active-workout-experience.spec.ts](../../../../../frontend/tests/e2e/active-workout-experience.spec.ts).
- Active visual golden обновлён только для изменённого A-06 кадра:
  `mobile-ui-regression.spec.ts-snapshots/mobile-chromium/win32/active-workout-390x844-dark.png`.
- Прогон mobile-regression сохранил известный baseline mismatch Progress: `741` пиксель в Light
  и `716` в Dark; эти эталоны не относятся к A-01…A-06 и не обновлялись.
- [AI Coach hidden regression](../../../../../frontend/tests/e2e/ai-coach-hidden.spec.ts) прошёл
  в Chromium и WebKit; CSS/видимость AI Coach не изменялись.
- Не менялись токены, обычные рамки, focus outlines, selected/warning/success состояния,
  `.today-workout-focus__header`, `.progress-report-confidence` и другие owner-approved rails.

Следующий owner gate: подтвердить этот единый AFTER-пакет визуально в Dark/Light; затем отдельно
разрешить merge и release. Draft PR не закрывает Issue и не выполняет deploy.
