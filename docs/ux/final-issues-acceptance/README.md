# YFC — финальная техническая приёмка Issues

Этот пакет — фактическая матрица покрытия 19 GitHub Issues, а не обещание полного релиза. Для каждого acceptance criterion проверены Issue body/comments, linked PR, текущий код и адресные tests/Checks. `#872` исключена последним запросом владельца.

## Итоговый срез

| Поле | Значение |
|---|---|
| Issues всего | 19 |
| `IMPLEMENTED_VERIFIED` | 0 |
| `IMPLEMENTED_NEEDS_ACCEPTANCE` | 7: #859, #860, #867, #868, #903, #904, #905 |
| `PARTIALLY_IMPLEMENTED` | 3: #865, #869, #870 |
| `NOT_IMPLEMENTED` | 0 (remaining unimplemented work is covered by explicit owner gates) |
| `BLOCKED_OWNER_INPUT` | 9: #861, #862, #863, #864, #866, #871, #873, #874, #906 |
| `INTENDED_BEHAVIOR` / `NOT_REPRODUCED` | 0 как итоговый статус Issue; отдельные под-критерии отмечены в матрице |
| `MASTER_SHA` | `a70fa8a1493c2f1ad0711c3143ab7700c96a92f4` |
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
- Landing #903: [PR #936](https://github.com/MikeMoore1337/your-fitness-coach/pull/936), [green CI run 38157331212](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38157331212).
- Demo transport #904/#905: [PR #939](https://github.com/MikeMoore1337/your-fitness-coach/pull/939), [CI run 38154110013](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38154110013).

## Evidence gallery

Открываемая после checkout галерея: [index.html](index.html).

### #867 — active workout, реальный AFTER

Источник: synthetic `mockActiveWorkout`, runtime commit `be3d2a2…`, Chromium/WebKit, 320/360/393/430 CSS px, dark/light. Полная provenance: [evidence/867/provenance.json](evidence/867/provenance.json). BEFORE baseline — owner-reported overlap at [`c8ece94`](https://github.com/MikeMoore1337/your-fitness-coach/tree/c8ece94eb1542e6d0c806aa9f602645126649e17/docs/ux/issue-914-acceptance).

Chromium AFTER:

- [320 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/chromium/resting-dock-320-dark.png) · [320 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/chromium/resting-dock-320-light.png)
- [360 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/chromium/resting-dock-360-dark.png) · [360 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/chromium/resting-dock-360-light.png)
- [393 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/chromium/resting-dock-393-dark.png) · [393 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/chromium/resting-dock-393-light.png)
- [430 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/chromium/resting-dock-430-dark.png) · [430 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/chromium/resting-dock-430-light.png)

WebKit AFTER:

- [320 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/webkit/resting-dock-320-dark.png) · [320 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/webkit/resting-dock-320-light.png)
- [360 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/webkit/resting-dock-360-dark.png) · [360 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/webkit/resting-dock-360-light.png)
- [393 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/webkit/resting-dock-393-dark.png) · [393 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/webkit/resting-dock-393-light.png)
- [430 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/webkit/resting-dock-430-dark.png) · [430 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/webkit/resting-dock-430-light.png)

Для #904/#905 главным evidence являются [sanitized transport/RBAC tests in PR #939](https://github.com/MikeMoore1337/your-fitness-coach/pull/939#files_bucket), а не декоративные mock screenshots. Для #906 AFTER намеренно отсутствует до owner visual approval.

### #903 — Landing weekly score, real BEFORE/AFTER

Evidence commit: [`16f88bc0`](https://github.com/MikeMoore1337/your-fitness-coach/commit/16f88bc0bf5bd1d8d488bbd7b4fa5a934f7e4fc8), source fix [`6d4b061c`](https://github.com/MikeMoore1337/your-fitness-coach/commit/6d4b061cda0a9272e71876af77e7f2165e51fbf1), current PR head [`13604595`](https://github.com/MikeMoore1337/your-fitness-coach/commit/13604595ca45c3bdac07edac99a205d3022264e3). The same interaction was captured on `/` and `/for-athletes`; the permanent screenshots below are from `/for-athletes`.

- 390×844: [BEFORE dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/16f88bc0bf5bd1d8d488bbd7b4fa5a934f7e4fc8/docs/ux/final-issues-acceptance/evidence/903/before/before-390-dark.png) · [AFTER dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/16f88bc0bf5bd1d8d488bbd7b4fa5a934f7e4fc8/docs/ux/final-issues-acceptance/evidence/903/after/after-390-dark.png) · [BEFORE light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/16f88bc0bf5bd1d8d488bbd7b4fa5a934f7e4fc8/docs/ux/final-issues-acceptance/evidence/903/before/before-390-light.png) · [AFTER light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/16f88bc0bf5bd1d8d488bbd7b4fa5a934f7e4fc8/docs/ux/final-issues-acceptance/evidence/903/after/after-390-light.png)
- 1440×900: [BEFORE dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/16f88bc0bf5bd1d8d488bbd7b4fa5a934f7e4fc8/docs/ux/final-issues-acceptance/evidence/903/before/before-1440-dark.png) · [AFTER dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/16f88bc0bf5bd1d8d488bbd7b4fa5a934f7e4fc8/docs/ux/final-issues-acceptance/evidence/903/after/after-1440-dark.png) · [BEFORE light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/16f88bc0bf5bd1d8d488bbd7b4fa5a934f7e4fc8/docs/ux/final-issues-acceptance/evidence/903/before/before-1440-light.png) · [AFTER light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/16f88bc0bf5bd1d8d488bbd7b4fa5a934f7e4fc8/docs/ux/final-issues-acceptance/evidence/903/after/after-1440-light.png)

Варианты #906 (без production-изменений): [visual proposal](proposals/906-hero-qhd.md).

## Owner gates

1. #871: политика выбора сегодняшнего дня после уже прошедшего часа напоминания.
2. #906: высота и композиция Hero на QHD/2K; нужен visual proposal и явное решение.
3. Остальные `IMPLEMENTED_NEEDS_ACCEPTANCE`: визуальная/release-приёмка конкретных доказательств.

`MERGE=FORBIDDEN`, `DEPLOY=FORBIDDEN`, `OWNER_VISUAL_APPROVAL=PENDING`, `OWNER_RELEASE_APPROVAL=PENDING`.
