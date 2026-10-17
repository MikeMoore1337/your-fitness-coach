# Evidence — Issue #998

Финальный пакет AFTER для Draft PR [#1046](https://github.com/MikeMoore1337/your-fitness-coach/pull/1046).

- Evidence/source SHA: [`096a4ed`](https://github.com/MikeMoore1337/your-fitness-coach/tree/096a4ededf95558f6996058e56826f50a1bd5f81/docs/ux/issue-998-rir-guidance-implementation/evidence).
- Merged-result mobile snapshots: [`1981b294`](https://github.com/MikeMoore1337/your-fitness-coach/commit/1981b294).
- Актуальный base после синхронизации: [`dc1daeb`](https://github.com/MikeMoore1337/your-fitness-coach/commit/dc1daeb57bc7eded67a089b206e8f84375fea8d1).
- Последующий sync merge после evidence: [`82da4dd`](https://github.com/MikeMoore1337/your-fitness-coach/commit/82da4ddec628e8c781b5c4c36ce8e9528da78787). Он содержит только CI-изменения и не меняет эти captures.

Снимки сделаны Playwright Chromium на synthetic fixture data. Они показывают браузерный AFTER,
но не доказывают поведение на физическом iPhone/Safari, в нативном Telegram, с VoiceOver или
в production.

## Active workout

Каждый ряд содержит четыре состояния: `compact` — закрытый current-set-first summary,
обычный — раскрытый summary с видимой рекомендацией прогрессии, `open` — раскрытые RIR и
прогрессия, `rest` — панель отдыха после завершения подхода.

| Тема  | Ширина | Compact                                | Summary                        | Подсказки открыты                   | Rest panel                          |
| ----- | -----: | -------------------------------------- | ------------------------------ | ----------------------------------- | ----------------------------------- |
| Dark  |    320 | [PNG](after-dark-320-compact.png)      | [PNG](after-dark-320.png)      | [PNG](after-dark-320-open.png)      | [PNG](after-dark-320-rest.png)      |
| Dark  |    360 | [PNG](after-dark-360-compact.png)      | [PNG](after-dark-360.png)      | [PNG](after-dark-360-open.png)      | [PNG](after-dark-360-rest.png)      |
| Dark  |    393 | [PNG](after-dark-393-compact.png)      | [PNG](after-dark-393.png)      | [PNG](after-dark-393-open.png)      | [PNG](after-dark-393-rest.png)      |
| Dark  |    430 | [PNG](after-dark-430-compact.png)      | [PNG](after-dark-430.png)      | [PNG](after-dark-430-open.png)      | [PNG](after-dark-430-rest.png)      |
| Dark  |   1440 | [PNG](after-dark-desktop-compact.png)  | [PNG](after-dark-desktop.png)  | [PNG](after-dark-desktop-open.png)  | [PNG](after-dark-desktop-rest.png)  |
| Light |    320 | [PNG](after-light-320-compact.png)     | [PNG](after-light-320.png)     | [PNG](after-light-320-open.png)     | [PNG](after-light-320-rest.png)     |
| Light |    360 | [PNG](after-light-360-compact.png)     | [PNG](after-light-360.png)     | [PNG](after-light-360-open.png)     | [PNG](after-light-360-rest.png)     |
| Light |    393 | [PNG](after-light-393-compact.png)     | [PNG](after-light-393.png)     | [PNG](after-light-393-open.png)     | [PNG](after-light-393-rest.png)     |
| Light |    430 | [PNG](after-light-430-compact.png)     | [PNG](after-light-430.png)     | [PNG](after-light-430-open.png)     | [PNG](after-light-430-rest.png)     |
| Light |   1440 | [PNG](after-light-desktop-compact.png) | [PNG](after-light-desktop.png) | [PNG](after-light-desktop-open.png) | [PNG](after-light-desktop-rest.png) |

## Program editor

Снимок ограничен schedule section редактора, чтобы текст цикла оставался читаемым в review.
Закрытое состояние показывает native disclosure `Как устроен цикл?`; открытое также содержит
явный fallback `Источник: нет ссылки.`.

| Тема  | Ширина | Подсказка закрыта                      | Подсказка открыта                           |
| ----- | -----: | -------------------------------------- | ------------------------------------------- |
| Dark  |    393 | [PNG](after-program-dark-393.png)      | [PNG](after-program-dark-393-open.png)      |
| Dark  |   1440 | [PNG](after-program-dark-desktop.png)  | [PNG](after-program-dark-desktop-open.png)  |
| Light |    393 | [PNG](after-program-light-393.png)     | [PNG](after-program-light-393-open.png)     |
| Light |   1440 | [PNG](after-program-light-desktop.png) | [PNG](after-program-light-desktop-open.png) |

## BEFORE и границы приёмки

Исторический BEFORE был снят из исходного состояния baseline [`4c92832`](https://github.com/MikeMoore1337/your-fitness-coach/commit/4c92832415d4eb994cf6b849a67074742f07ea50). Он сохранён в этой папке для сравнения, но не используется как текущая master-база.

Проверка через Chromium и WebKit прошла для Issue #998; screenshots намеренно оставлены
Chromium-only для единого визуального источника. Owner visual acceptance, merge, deploy,
physical-device и production gates остаются отдельными решениями.
