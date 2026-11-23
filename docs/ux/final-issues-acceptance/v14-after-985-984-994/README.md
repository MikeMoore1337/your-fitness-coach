# Product V14: единый AFTER для #985, #984 и #994

Пакет показывает проверенное приложение и исправление читаемости навигации Coach OS. Он собран для совместного рассмотрения трёх задач; он **не подтверждает финальную приёмку владельца, готовность к выпуску или закрытие Issues**. Независимый visual critique не проводился по выбранному владельцем режиму `SINGLE_MODEL`.

Код приложения на снимках и видео: [`f17758865616ea708dd798776080420f907630b2`](https://github.com/MikeMoore1337/your-fitness-coach/commit/f17758865616ea708dd798776080420f907630b2). База до исправления: [`4fbe2464591303f65ab941393a5a269bafc0d515`](https://github.com/MikeMoore1337/your-fitness-coach/commit/4fbe2464591303f65ab941393a5a269bafc0d515). Последующие коммиты ветки добавляют только тесты и этот пакет. Скриншоты выполнены на локальной Vite-сборке с синтетическими API-данными. Chromium и WebKit — браузерные движки Playwright; PWA и Telegram в тестах эмулируются.

## Coach OS: воспроизведённое исправление

При настоящем Chromium zoom 200% от исходных 393 × 852 px четыре подписи Coach OS обрезались. Измерение текста теперь включает Coach OS: когда места недостаточно, навигация перестраивается в две или одну колонку. Доступные имена, выбранное состояние, действия и обычная компоновка сохранены. Этот технический reflow не реализует отдельный дизайн Dock 4+1 из #1504.

| Тема | До, `dev` | После, исправленный код |
|---|---|---|
| Light | [BEFORE](994/before/chromium-zoom200-light-coach.png) | [AFTER](994/header/chromium-zoom200-light-coach.png) |
| Dark | [BEFORE](994/before/chromium-zoom200-dark-coach.png) | [AFTER](994/header/chromium-zoom200-dark-coach.png) |

До исправления новый тест чтения всех четырёх подписей падал; после — проходит в обеих темах с `chrome.tabs.getZoom() = 2`. Дополнительно проверены размеры целей не менее 44 CSS px, отсутствие пересечения ссылок, Enter, восстановление одной строки после уменьшения текста и положение действий над панелью. Эмуляция Telegram проверяет safe-area, но не заменяет настоящий WebView.

## #985: завершение тренировки

- [Sport и подтверждённый фикстурой рекорд, Chromium Dark 393 × 852](985/video/chromium-sport-and-record.webm); [пропуск движения](985/video/chromium-skip.webm).
- [Подход, Chromium Dark 393](985/screens/chromium-web-dark-393-set.png) · [итог и рекорд](985/screens/chromium-web-dark-393-summary.png) · [кардио, WebKit Light 393](985/screens/webkit-web-light-393-cardio.png).
- [Все 100 снимков](985/screens/): два движка, Dark/Light, Web/эмуляция PWA/TMA, 320/360/393/430 CSS px, плюс кардио. Full-page снимки фиксируют положение dock в момент съёмки.
- 68 сценариев прошли в Chromium/WebKit; два теста видеозаписи — в Chromium. Покрыты последний силовой подход и кардио, повторное открытие, пропуск, двойное нажатие, retry и background/resume в объёме тестовых фикстур. Тесты backend на `dev` до исправления: 19 passed, 4 skipped для итогов и таймера; backend не изменялся.
- Дополнительно 4/4 проверки в Chromium/WebKit подтвердили явное редактирование или возврат завершённого силового подхода и сохранение значений кардио по контракту #980. В составе отдельного прогона 24/24 прошли offline/reload/reconnect для рабочих, разминочных и активационных подходов, защита от устаревшего refetch, сохранение и восстановление таймера, simulated hidden-tab return, прерывание обратной связи и reduced motion. Этот прогон также включает случаи Nutrition/Progress ниже.

Фикстура выдаёт рекорд для видео; это не отдельное доказательство истории реального пользователя. [Предыдущий AFTER #985](https://github.com/MikeMoore1337/your-fitness-coach/blob/2b89cb36865a5067371973ce0fb2a8fe6a31a7d7/docs/ux-proposals/issue-985-after/README.md) содержит техническое сопоставление с [Sport-прототипом #982](https://github.com/MikeMoore1337/your-fitness-coach/blob/5e26a4724bb8e7cda5f20f92d6d69bca94baeb78/docs/ux-proposals/issue-982/SPEC.md): 560 мс, начальные opacity 0,85 и сдвиг 16 px, акценты фактов 180 мс с задержкой 90 мс, доступные сразу числа и пропуск. Ручное визуальное утверждение совпадения не заменено этими параметрами.

## #984: Progress и Nutrition

- [Progress: видео Chromium Light](984/video/progress-chromium-light.webm) · [WebKit Dark](984/video/progress-webkit-dark.webm).
- [Nutrition: видео Chromium Light](984/video/nutrition-chromium-light.webm) · [WebKit Dark](984/video/nutrition-webkit-dark.webm).
- [Все восемь видео](984/video/) и [64 снимка](984/screens/): Progress «Обзор»/«Тело», дневник и добавление, 320/360/393/430 CSS px, Chromium/WebKit, Dark/Light. Записи показывают переходы, Back/Forward и reduced motion в пределах сценария.
- 19 сценариев прошли, один WebKit touch-тест пропущен: управление в нём зависит от Chromium CDP. Проверены отдельные жесты, период/URL/история, черновик, клавиатура, вода, forced colors и reduced motion. Системный edge-back и поведение реальной клавиатуры эти фикстуры не доказывают.
- В дополнительном прогоне 24/24 также проверены защита от отмены записи воды, перенесённой другой вкладкой, и соответствие данных отчёта и кардио выбранному периоду в Chromium/WebKit.

Исторические [AFTER и измерения #984](https://github.com/MikeMoore1337/your-fitness-coach/blob/00ec18346d5da933f49edf3cb968ac9fa24b950f/docs/ux-proposals/issue-984-after/README.md) относятся к прежнему head PR и используются только как эталон. Некоторые фикстуры показывают сообщение о недоступных предложениях тренера; это тестовое состояние, а не вывод о production.

## #994: экраны и соответствие решениям

В [матрице снимков](994/matrix/) — 216 снимков шести маршрутов, 36 файлов измерений: Chromium/WebKit, Dark/Light; 320/360/390/393/430 × 852, 768/1024/1280/1440 × 900 CSS px. В этой съёмке проверены загрузка выбранного состояния, отсутствие `pageerror` и горизонтального переполнения; 36/36 сценариев прошли. Это не полное исследование всех состояний каждой страницы. Активная тренировка отдельно показана в #985.

| Область | Chromium Light, 393 px | Chromium Dark, 393 px | Desktop, Chromium Light, 1280 px |
|---|---|---|---|
| Today | [снимок](994/matrix/chromium-light-393-today.png) | [снимок](994/matrix/chromium-dark-393-today.png) | [снимок](994/matrix/chromium-light-1280-today.png) |
| Plan | [снимок](994/matrix/chromium-light-393-plan.png) | [снимок](994/matrix/chromium-dark-393-plan.png) | [снимок](994/matrix/chromium-light-1280-plan.png) |
| Nutrition | [снимок](994/matrix/chromium-light-393-nutrition.png) | [снимок](994/matrix/chromium-dark-393-nutrition.png) | [снимок](994/matrix/chromium-light-1280-nutrition.png) |
| Progress | [снимок](994/matrix/chromium-light-393-progress.png) | [снимок](994/matrix/chromium-dark-393-progress.png) | [снимок](994/matrix/chromium-light-1280-progress.png) |
| Profile | [снимок](994/matrix/chromium-light-393-profile.png) | [снимок](994/matrix/chromium-dark-393-profile.png) | [снимок](994/matrix/chromium-light-1280-profile.png) |
| Coach OS | [снимок](994/matrix/chromium-light-393-coach.png) | [снимок](994/matrix/chromium-dark-393-coach.png) | [снимок](994/matrix/chromium-light-1280-coach.png) |

| Аудит #993 / решение | Код и проверка | AFTER / статус |
|---|---|---|
| P1: текст и действие Today пересекались при увеличении | [PR #1501](https://github.com/MikeMoore1337/your-fitness-coach/pull/1501); на объединённой базе ранее выполнены проверки увеличенного текста | [Today](994/matrix/chromium-light-393-today.png); визуальная приёмка владельца — PENDING |
| P2: подписи личного dock при увеличении | [PR #1502](https://github.com/MikeMoore1337/your-fitness-coach/pull/1502); `dock-text-scaling.spec.ts`, Chromium/WebKit | [Today](994/matrix/chromium-dark-393-today.png); PENDING |
| Progress и заголовок тренировки при увеличении текста | [PR #1503](https://github.com/MikeMoore1337/your-fitness-coach/pull/1503); `v14-text-reflow.spec.ts` на базе — 76 сценариев совместно с dock | [Progress](994/matrix/chromium-light-393-progress.png), [тренировка](985/screens/chromium-web-dark-393-summary.png); PENDING |
| Общая шапка: утверждённый перенос при узкой ширине | [PR #1514](https://github.com/MikeMoore1337/your-fitness-coach/pull/1514); текущая проверка 12 passed, 2 WebKit zoom skipped | [AFTER шести маршрутов](994/header/); PENDING |
| Сокращённые подписи Coach OS на настоящем zoom | `AppShell.tsx`, `design-v2.css`; новый `coach-dock-reflow.spec.ts`: 28 passed; before-fail/after-pass на настоящем zoom | [BEFORE/AFTER](#coach-os-воспроизведённое-исправление); PENDING |
| Геометрия, кнопки, иконки, материалы и формы | [Исходный пакет #994](https://github.com/MikeMoore1337/your-fitness-coach/blob/8aaeb5d67f3aa111382b132a88f4d520a8e345d1/docs/ux-proposals/issue-994-review/README.md) предлагал сохранить показанные композиции и исправить шапку; это не evidence реализации | Текущая матрица покрывает показанные состояния; полная проверка всех форм, состояний и строк аудита — NOT_VERIFIED |

**ACCEPTED_DEVIATION:** ранее владелец согласился, что стресс с базовым шрифтом 32 px одновременно с zoom 200% при viewport 160–196 CSS px, где действие Today выходит за край, не блокирует основную матрицу. Источник — [PR #1502](https://github.com/MikeMoore1337/your-fitness-coach/pull/1502). Это не означает автоматического согласования других состояний.

## Проверки, производительность и границы

⚠️ **DEGRADED: single-context.** Вручную просмотрены новые снимки Coach OS в обычной мобильной и desktop-компоновке, Coach OS при настоящем zoom, итог тренировки и Progress. На просмотренных снимках подписи исправленной навигации читаются; desktop сохраняет отдельную компоновку. Full-page снимки содержат фиксированный dock в позиции съёмки, поэтому проверять доступность действий следует по интерактивным тестам. Это ограниченный последовательный просмотр, а не независимая оценка всех экранов и состояний.

- `npm run build` и `npm run lint` — PASS; проверка форматирования шести изменённых frontend-файлов — PASS. Полный Vitest — **192 файла, 1524 теста passed** с `TEMP/TMP` без символа `#`.
- Регрессия Coach OS и личной навигации: 62 passed, 2 skipped в первом общем прогоне; расширенная матрица Coach OS — 28 passed, включая эмуляцию TMA; существующие desktop/TMA/safe-area сценарии — 10 passed. Текущая проверка шапки и настоящего Chromium zoom — 12 passed, 2 skipped.
- `perf:check` — PASS с прежними лимитами. Сопоставимые локальные сборки до/после: `AppShell` JS **83070 → 83155 raw**, **24000 → 24047 gzip** байт; shared `design-v2` CSS **467554 → 467947 raw**, **67357 → 67426 gzip**. Входной JS после: **303839 raw / 95352 gzip**, бюджет **310000 / 96000**. Это не полевые замеры скорости или батареи.
- Windows `format:check` в чистом checkout сообщил о 683 файлах на исходном `dev` и 673 на чистом `master` с тем же Prettier; для проверенного файла Git blob содержит LF, checkout — CRLF. Это не доказывает причину каждого замечания.
- Impeccable 4.7.0: локальный context и static detector выполнены. Detector вернул код 2 и 22 `side-tab`-сигнала; сравнение с исходной базой дало те же 22 фрагмента. Они требуют контекстной оценки; detector не заменяет visual critique. Независимое ревью — **NOT_RUN**, `SINGLE_MODEL`.
- Во время части мокированных Sport-сценариев, включая дополнительный offline-прогон, локальный Vite сообщил об `ECONNREFUSED` для не перехваченных fixture-запросов к отсутствующему локальному API, в том числе `set-history`. Тесты прошли, но это ограничение окружения не позволяет утверждать полное отсутствие сетевых ошибок или проверку живого backend.
- Реальные iPhone/Safari, установленная PWA, Telegram WebView, системная клавиатура и VoiceOver — **NOT_VERIFIED**. Полевые frame timing, память и battery — **NO_DATA**. Ошибки JavaScript контролировались в 36 сценариях матрицы, не во всех возможных состояниях.

На исходном объединённом SHA [push CI](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/45070679905) успешен, но frontend/mobile jobs там пропущены. [PR #1515](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/45036888033) и [PR #1516](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/45069478596) имели зелёный `checks` на своих отдельных head. Актуальный CI ветки исправления нужно проверять на её конечном SHA отдельно.

На предшествующем head исправления `94a3fb522938993dad8ee9c9008c392ddaf94fdf` [автоматический CI](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/45133037636) завершился с зелёным агрегатом `checks` и 1524 passed в frontend unit. Предыдущий запуск того же head завершился тайм-аутом 5 секунд в неизменённом тесте лендинга; в успешном запуске тест занял 4,84 секунды. Причина задержки не установлена, и последующий успех её не объясняет.

Для воспроизведения матрицы шести экранов задайте абсолютный `YFC_V14_AFTER_DIR` и запустите из `frontend` после сборки: `npx playwright test --config=playwright.cross-browser.config.ts --project=chromium --project=webkit tests/e2e/v14-after-capture.spec.ts`. Каждый файл JSON рядом со снимками содержит ширины документа и собранные `pageerror`.

`985_VISUAL_QA=BLOCKED` и `984_VISUAL_QA=BLOCKED` до завершения необходимых независимых и непроверенных этапов. По #994 обнаруженное обрезание исправлено и протестировано, но полная UI-приёмка и owner AFTER approval остаются незавершёнными. Для закрытия #994 также нужны применимые разрешения выпуска, CI на master, SHA реально опубликованной версии и smoke. #985 и #984 автоматически не закрываются.
