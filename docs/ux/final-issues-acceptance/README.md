# YFC — финальная техническая приёмка Issues

Этот пакет — фактическая матрица покрытия 22 GitHub Issues, а не обещание полного релиза. Для каждого acceptance criterion проверены Issue body/comments, linked PR, текущий код и адресные tests/Checks. `#872` исключена последним запросом владельца.

## Итоговый срез

| Поле | Значение |
|---|---|
| Issues всего | 22 |
| `IMPLEMENTED_VERIFIED` | 0 |
| `IMPLEMENTED_NEEDS_ACCEPTANCE` | 11: #859, #860, #867, #868, #903, #904, #905, #906, #946, #947, #948 |
| `PARTIALLY_IMPLEMENTED` | 3: #865, #869, #870 |
| `NOT_IMPLEMENTED` | 7: #861, #862, #863, #864, #866, #873, #874; причина — отдельный owner gate |
| `BLOCKED_OWNER_INPUT` | 1: #871 |
| `INTENDED_BEHAVIOR` / `NOT_REPRODUCED` | 0 как итоговый статус Issue; отдельные под-критерии отмечены в матрице |
| `MASTER_SHA` | `e6b692e464411817a3abb8f5ec77b131595eaf47` (live `origin/master` at audit update) |
| Production | Не изменялась |
| Merge/deploy | Не выполнялись |

Подробная разбивка каждого критерия: [ISSUE_COVERAGE_MATRIX.md](ISSUE_COVERAGE_MATRIX.md).

## PR и Checks

- Мобильная интеграция и #867/#914: [PR #927](https://github.com/MikeMoore1337/your-fitness-coach/pull/927), source fix [`be3d2a2`](https://github.com/MikeMoore1337/your-fitness-coach/commit/be3d2a2a0ffac3e27c44029578f3354197387736), evidence [`f3475375`](https://github.com/MikeMoore1337/your-fitness-coach/commit/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08), current formatting head [`06cc0dbe`](https://github.com/MikeMoore1337/your-fitness-coach/commit/06cc0dbeaae04479cedfac1f7b860aa51dadd326), [CI run](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38157427549).
- Approved mobile package: [PR #915](https://github.com/MikeMoore1337/your-fitness-coach/pull/915).
- Replacement preview #860: [PR #907](https://github.com/MikeMoore1337/your-fitness-coach/pull/907).
- Water navigation #868: [PR #908](https://github.com/MikeMoore1337/your-fitness-coach/pull/908).
- Nutrition labels #869: [PR #909](https://github.com/MikeMoore1337/your-fitness-coach/pull/909).
- Profile goal #870: [PR #910](https://github.com/MikeMoore1337/your-fitness-coach/pull/910).
- Reminder calendar guard #871: [PR #911](https://github.com/MikeMoore1337/your-fitness-coach/pull/911).
- Landing #903: [PR #936](https://github.com/MikeMoore1337/your-fitness-coach/pull/936), current head [`9d628f8e`](https://github.com/MikeMoore1337/your-fitness-coach/commit/9d628f8e9111e5bd39c65b8c55aa46b3559f1ece), evidence [`c40a64ee`](https://github.com/MikeMoore1337/your-fitness-coach/commit/c40a64eedb467bb33938a1cf6165d5878ed0d56b). Targeted Chromium and WebKit specs are green locally; [GitHub Checks run 38161796686](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38161796686) is the release gate.
- Demo transport #904/#905: [PR #939](https://github.com/MikeMoore1337/your-fitness-coach/pull/939), [CI run 38154110013](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38154110013).
- Nutrition mobile #946–#948: [PR #958](https://github.com/MikeMoore1337/your-fitness-coach/pull/958), head [`df454007`](https://github.com/MikeMoore1337/your-fitness-coach/commit/df454007a1379a3fd98490d4ca2e7e334a535d16), [CI run 38169839440](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38169839440), [48-capture evidence](evidence/946-948/README.md).

## Evidence gallery

Открываемая после checkout галерея: [index.html](index.html).

### #867 — active workout, реальный AFTER

Источник: synthetic `mockActiveWorkout`, runtime commit `be3d2a2…`, Chromium/WebKit, 320/360/393/430 CSS px, dark/light. Полная provenance: [evidence/867/provenance.json](evidence/867/provenance.json). BEFORE baseline — owner-reported overlap at [`c8ece94`](https://github.com/MikeMoore1337/your-fitness-coach/tree/c8ece94eb1542e6d0c806aa9f602645126649e17/docs/ux/issue-914-acceptance).

Chromium AFTER:

- [320 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/chromium/resting-dock-320-dark.png) · [320 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/chromium/resting-dock-320-light.png)
- [360 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/chromium/resting-dock-360-dark.png) · [360 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/chromium/resting-dock-360-light.png)
- [393 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/chromium/resting-dock-393-dark.png) · [393 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/chromium/resting-dock-393-light.png)
- [430 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/chromium/resting-dock-430-dark.png) · [430 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/chromium/resting-dock-430-light.png)

Chromium BEFORE baseline (owner-reported runtime package): [320 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/c8ece94eb1542e6d0c806aa9f602645126649e17/docs/ux/issue-914-acceptance/before/chromium-320-dark-timer.png) · [360 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/c8ece94eb1542e6d0c806aa9f602645126649e17/docs/ux/issue-914-acceptance/before/chromium-360-dark-timer.png) · [393 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/c8ece94eb1542e6d0c806aa9f602645126649e17/docs/ux/issue-914-acceptance/before/chromium-393-light-timer.png) · [430 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/c8ece94eb1542e6d0c806aa9f602645126649e17/docs/ux/issue-914-acceptance/before/chromium-430-light-timer.png)

WebKit AFTER:

- [320 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/webkit/resting-dock-320-dark.png) · [320 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/webkit/resting-dock-320-light.png)
- [360 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/webkit/resting-dock-360-dark.png) · [360 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/webkit/resting-dock-360-light.png)
- [393 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/webkit/resting-dock-393-dark.png) · [393 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/webkit/resting-dock-393-light.png)
- [430 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/webkit/resting-dock-430-dark.png) · [430 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/webkit/resting-dock-430-light.png)

Для #904/#905 главным evidence являются [sanitized transport/RBAC tests in PR #939](https://github.com/MikeMoore1337/your-fitness-coach/pull/939#files_bucket), а не декоративные mock screenshots. Для #906 используются реальные AFTER из [PR #944](https://github.com/MikeMoore1337/your-fitness-coach/pull/944); вариант B визуально одобрен владельцем, native browser zoom 125% не проверялся.

### #903 — Landing weekly score, real BEFORE/AFTER

Evidence commit: [`c40a64ee`](https://github.com/MikeMoore1337/your-fitness-coach/commit/c40a64eedb467bb33938a1cf6165d5878ed0d56b), source fix [`733933a7`](https://github.com/MikeMoore1337/your-fitness-coach/commit/733933a73a3bc27ca596b9efb00751105a539a86), current PR head [`9d628f8e`](https://github.com/MikeMoore1337/your-fitness-coach/commit/9d628f8e9111e5bd39c65b8c55aa46b3559f1ece). The same interaction was captured on `/` and `/for-athletes`; the permanent screenshots below are from `/for-athletes`. `pointer` is selected 5 after mouse click, `keyboard` is focus-visible without selection, and `none` is the unselected baseline.

- 390×844 dark: [BEFORE](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/c40a64eedb467bb33938a1cf6165d5878ed0d56b/docs/ux/final-issues-acceptance/evidence/903/before/before-390-dark.png) · [AFTER pointer](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/c40a64eedb467bb33938a1cf6165d5878ed0d56b/docs/ux/final-issues-acceptance/evidence/903/after/after-390-dark.png) · [AFTER keyboard](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/c40a64eedb467bb33938a1cf6165d5878ed0d56b/docs/ux/final-issues-acceptance/evidence/903/after/keyboard-390-dark.png) · [AFTER none](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/c40a64eedb467bb33938a1cf6165d5878ed0d56b/docs/ux/final-issues-acceptance/evidence/903/after/none-390-dark.png)
- 390×844 light: [BEFORE](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/c40a64eedb467bb33938a1cf6165d5878ed0d56b/docs/ux/final-issues-acceptance/evidence/903/before/before-390-light.png) · [AFTER pointer](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/c40a64eedb467bb33938a1cf6165d5878ed0d56b/docs/ux/final-issues-acceptance/evidence/903/after/after-390-light.png) · [AFTER keyboard](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/c40a64eedb467bb33938a1cf6165d5878ed0d56b/docs/ux/final-issues-acceptance/evidence/903/after/keyboard-390-light.png) · [AFTER none](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/c40a64eedb467bb33938a1cf6165d5878ed0d56b/docs/ux/final-issues-acceptance/evidence/903/after/none-390-light.png)
- 1440×900 dark/light and scale fragments: [dark pointer](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/c40a64eedb467bb33938a1cf6165d5878ed0d56b/docs/ux/final-issues-acceptance/evidence/903/after/scale-pointer-1440-dark.png) · [dark keyboard](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/c40a64eedb467bb33938a1cf6165d5878ed0d56b/docs/ux/final-issues-acceptance/evidence/903/after/scale-keyboard-1440-dark.png) · [light pointer](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/c40a64eedb467bb33938a1cf6165d5878ed0d56b/docs/ux/final-issues-acceptance/evidence/903/after/scale-pointer-1440-light.png) · [light keyboard](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/c40a64eedb467bb33938a1cf6165d5878ed0d56b/docs/ux/final-issues-acceptance/evidence/903/after/scale-keyboard-1440-light.png)

### #906 — Hero, approved variant B

Реальные `BEFORE / A / B` из изолированной локальной сборки: [индекс #906](evidence/906/README.md), [provenance](evidence/906/provenance.json), [proposal summary](proposals/906-hero-qhd.md). Владелец выбрал и визуально одобрил B в [Issue](https://github.com/MikeMoore1337/your-fitness-coach/issues/906#issuecomment-6112622277) и [PR](https://github.com/MikeMoore1337/your-fitness-coach/pull/944#issuecomment-6112622702); текущий PR head — [`2a8629de`](https://github.com/MikeMoore1337/your-fitness-coach/commit/2a8629def1c591d6c64df4d114546b54b6448d20). Native browser zoom 125% remains unverified.

### #946–#948 — мобильный выбор продуктов

Полный индекс [evidence/946-948/README.md](evidence/946-948/README.md) содержит 48 настоящих Chromium/WebKit captures: закрытая и открытая клавиатура, результаты для «рис» и «картофель», длинные названия, pressed/selected, dark/light, 320/393. Визуальная геометрия `visualViewport` контролировалась в браузере; это не доказательство физического iPhone, native Telegram keyboard или VoiceOver.

- #946: клавиатура не перекрывает поле и результаты; восстановление запроса/focus проверено адресным E2E.
- #947: pressed/selected контрастны, favorite не выбирает продукт, selected-state не возникает от случайного касания.
- #948: длинные названия переносятся, вторичные действия уходят ниже; данные и КБЖУ не изменялись.

### Остальные визуальные Issues: прямой индекс существующих доказательств

Ссылки ниже — опубликованные изображения из стабильного runtime `38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f`. Они помечены как `reference`, если кадр подтверждает только общий маршрут, но не весь acceptance criterion.

| Issue | Достоверные опубликованные кадры | Статус доказательства |
|---|---|---|
| #861 | [Plan 320 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-320-dark-programs.png) · [light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-320-light-programs.png) | reference; отдельный search/editor acceptance отсутствует; `NOT_IMPLEMENTED` по owner gate |
| #862 | [Plan 360 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-360-dark-programs.png) · [light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-360-light-programs.png) | reference; editor save/keyboard proof отсутствует |
| #863 | [Plan 320 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-320-dark-programs.png) · [light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-320-light-programs.png) | reference; full Plan criteria remain owner-gated |
| #864 | [Plan 393 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-393-dark-programs.png) · [light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-393-light-programs.png) | reference; 8-week geometry not proven |
| #865 | [Progress 320 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-320-dark-progress.png) · [light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-320-light-progress.png) | reference for compact overview; metrics/empty-state audit remains partial |
| #866 | [Workout 360 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-360-dark-workout.png) · [light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-360-light-workout.png) | reference; completed-exercise acceptance absent |
| #869 | [Nutrition 393 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-393-dark-nutrition.png) · [light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-393-light-nutrition.png) | reference; diary/plan/grocery/history flow remains partial |
| #870 | [PR #910 implementation](https://github.com/MikeMoore1337/your-fitness-coach/pull/910) | no trustworthy profile screenshot in this package; visual acceptance absent |
| #873 | [Progress 430 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-430-dark-progress.png) · [light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-430-light-progress.png) | reference; detailed subsections and no-data semantics unproven |
| #874 | [Progress 393 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-393-dark-progress.png) · [browser PDF](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/ee92508da30ed5eed5e3e3914754515e4a278c25/docs/ux/mobile-859-glass-polish/pdf/browser-after.pdf) · [server PDF](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/ee92508da30ed5eed5e3e3914754515e4a278c25/docs/ux/mobile-859-glass-polish/pdf/server-after.pdf) | reference/PDF artifacts; current full report contract still unproven |

## Owner gates

1. #871: политика выбора сегодняшнего дня после уже прошедшего часа напоминания. Рекомендация — запросить новое время сегодня; не менять расписание молча и не создавать напоминание до валидного значения.
2. #906: visual approval варианта B получен; отдельное разрешение на merge/release всё ещё требуется.
3. #946–#948: техническая реализация и browser evidence готовы; visual acceptance владельца по каждой Issue ещё ожидается.
4. Остальные `IMPLEMENTED_NEEDS_ACCEPTANCE`: визуальная/release-приёмка конкретных доказательств.

`MERGE=FORBIDDEN`, `DEPLOY=FORBIDDEN`, `OWNER_VISUAL_APPROVAL=PARTIAL`, `OWNER_RELEASE_APPROVAL=PENDING`, `PRODUCTION_SHA=UNCHANGED`.
