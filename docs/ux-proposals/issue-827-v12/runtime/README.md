# #827 — реализация утверждённого A1

30.10.2026 владелец принял A1 и разрешил доставку в dev: «Принимаю A1. Можно катить в dev». Продолжается существующий PR [#1313](https://github.com/MikeMoore1337/your-fitness-coach/pull/1313), база `dev=b5212e1db7867ed2b0a8b9f297272988afc42b78`. Master, production и #830/#831/#1201 не входят в эту доставку. Issue #827 не объявляется завершённой по одному макету или CI.

`MuscleWorkloadDistribution` заменяет прежнее распределение в существующем разделе «Прогресс». Список и детальная панель используют единственный DOM-узел подробностей: справа от 1180px, сразу после выбранной строки на меньшей ширине. Сохранены нативные раскрытия упражнений и тренировок, усечённая история и доступные текстовые значения. Кабинет тренера продолжает использовать прежний `MuscleWorkloadList`.

Календарь #835, выбор года, общий период, показатели, DataConfidence, история упражнений, AppShell и inline «Добавить» сохранены. Частота дополнена количеством тренировок и сравнением с предыдущим равным периодом. Периоды используют прежний `useTrainingAnalytics`; загрузка, ошибка и повторная загрузка остаются в существующем query. Новых зависимостей, API, подсчётов backend, миграций, анатомических изображений и глобальных токенов нет. **env change required: no**.

## Реальные изображения

AFTER — работающая React-страница, без замены DOM макетом. Для воспроизводимых состояний API возвращает [12 snapshots](../fixtures.json), рассчитанных настоящим `build_training_analytics` по синтетической SQLite и каноническому каталогу. Это браузерная проверка отображения существующего API, не доказательство PostgreSQL/production или реального Telegram WebView. BEFORE использует исходники двух изменённых компонентов из `774dbec8406f6ca192b3679efb2bff8f2a959564`; остальная оболочка и данные совпадают. APPROVED — ранее утверждённые HTML-монтажи того же baseline.

- [BEFORE / APPROVED / AFTER — mobile Dark](comparison-dark-393.png), [mobile Light](comparison-light-393.png), [desktop Dark](comparison-dark-1440.png), [desktop Light](comparison-light-1440.png).
- [Mobile Dark/Light: распределение и источники](owner-mobile.png).
- [Desktop Dark](after-chromium-dark-populated-1440.png), [Desktop Light](after-chromium-light-populated-1440.png).
- [Неполные и пустые данные](owner-states.png).
- [Текущий null / предыдущие три подхода — mocked TMA WebKit](a11y-null-webkit-dark-393.png).

Все 144 сочетания: 320/360/393/430, 768/1024, 1280/1440/1920px × Dark/Light × Chromium/WebKit × populated/incomplete/empty/all_unmapped. В [matrix.json](matrix.json) указаны геометрия, шрифты, исходные файлы и соответствующие контактные листы. 48 файлов `matrix-{browser}-{theme}-{state}-{mobile|tablet|desktop}.png` состоят из настоящих пикселей браузера. Полные оригиналы и полноразмерные модули находятся в ignored `.artifacts/tasks/827/evidence/runtime-matrix/`.

Основной агент открыл native AFTER, сравнения, состояния и mocked TMA. Независимые специалисты непосредственно просмотрели все 48 итоговых листов и дополнительные полноразмерные снимки нижних групп, mobile и desktop. Это отдельная визуальная приёмка, дополненная техническими проверками геометрии.

## Цикл исправлений

1. Начальный desktop AFTER не прошёл визуальное сравнение: 44px внутренних отступов вместо 24px, вступление переносилось лишней строкой. Исправлены scoped отступы и ширина текста; повторный просмотр восьми native AFTER/detail дал PASS.
2. Пустой shared EmptyState сначала отличался от A1: центрированный Inter, серая пунктирная карточка. Scoped CSS восстановил Oswald, сплошную рамку и левое выравнивание. Дополнительная проверка обнаружила оставшееся `justify-items:center`; исправлен корень. Все 72 empty/unmapped сочетания пересняты, начало текста проверено относительно padding; независимый повторный просмотр всех 24 листов дал PASS.
3. На 320px значение «Вспомогательное: 16» может переходить на следующую строку внутри сравнения. Текст целиком читается; это допустимый reflow. Более лёгкий вес текста WebKit наблюдался и в утверждённом макете; шрифты Inter/Oswald загружены в обоих движках.

## Фактический контракт

Готовые `completed_set_count`, роли, session count, частота и изменения читаются напрямую из training analytics. Масштаб полос — максимум двух ролей в видимом ответе; это геометрия, не коэффициент эффективности. Роли показаны раздельно. Сумма групп не выдаётся за уникальные подходы, а group total не пересчитывается сложением полос.

`current=null` и `previous=null` остаются отсутствием данных; нулевые зарегистрированные значения остаются нулями. Без обеих сторон delta не появляется. `completed_sets_without_muscle_metadata` относится к подходам с нулём мышечных связей; предупреждение не утверждает полноту всех вторичных аннотаций. Новых recovery/fatigue/readiness/medical выводов нет.

Один backend regression проверяет смешанные роли одной группы в одной тренировке: семь уникальных подходов, два без связей, трицепс 5 (2 primary / 3 secondary), одна distinct тренировка, частота 1,0, nullable previous/current. Сумма значений групп больше общего числа уникальных подходов. Сервис и schema не изменены.

## Выполненные проверки

| Проверка                        | Доказательство                                                                                                                                |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend API regression          | 16 PASS: training_analytics, progress_periods, advanced_set_semantics; отдельные SQLite, basetemp и cache                                     |
| Frontend unit regression        | 166 файлов, 1107 тестов PASS; два workers                                                                                                     |
| Canonical Playwright            | 50 PASS: по 25 Chromium/WebKit, включая 7 новых/обновлённых и 18 календарных сценариев #835                                                   |
| Runtime visual matrix           | 144 PASS; после исправлений empty/unmapped повторены все 72 применимых сочетания                                                              |
| Accessibility/browser semantics | 12 PASS: Web 320/1440 и mocked TMA 393, обе темы/движка; keyboard, focus, ARIA tree/controls, forced-colors semantics, reduced-motion ≤0,01ms |
| Контраст текста                 | Минимум 5,07:1 среди проверенных пар, включая края выбранного градиента; [accessibility.json](accessibility.json)                             |
| Source quality                  | TypeScript, ESLint, Russian UI guard, lime-edge guard, Prettier изменённых файлов, Ruff и diff check PASS                                     |
| Build/budget                    | Vite build PASS; entry JS 296909 raw / 93389 gzip при неизменных бюджетах 310000 / 96000                                                      |

На Windows обычный полный `format:check` обнаруживает CRLF в существующих файлах. Полный Prettier с `end-of-line=auto` прошёл; посторонние файлы не переформатированы. Обязательный стандартный LF check в GitHub CI остаётся включённым. Проверка доступного ARIA tree не заменяет запуск настоящего screen reader. Native AT, физический iPhone и настоящий Telegram-клиент — **NOT_VERIFIED**.

Независимое code review охватило runtime, CSS, встраивание, unit-тесты и Coach caller; блокеров нет. Автор нового backend-теста не выдавал его за независимо проверенный: основной агент отдельно прочитал этот тест. Независимое visual QA заполненного, неполного и двух пустых состояний — PASS после исправлений.

## Статус этого пакета

| Поле                     | Статус и граница                                                                                                      |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| ANATOMY_ASSET_PROVENANCE | PASS — исследование сохранено в родительском отчёте; сторонняя графика не используется                                |
| VISUAL_CONCEPTS          | PASS — три композиции; A1 выбран владельцем                                                                           |
| CODEX_DESIGN_VISUAL_QA   | PASS — исходные макеты                                                                                                |
| OWNER_VISUAL_APPROVAL    | PASS — явное принятие A1 и разрешение dev в текущем чате                                                              |
| RUNTIME_IMPLEMENTATION   | PASS — существующий экран React, реальные переключения и состояния                                                    |
| FACTUAL_DATA_ACCURACY    | PASS — существующий API, backend/API/frontend regression; production не проверялась                                   |
| MOBILE_VISUAL_QA         | PASS — фактические снимки 320/360/393/430                                                                             |
| DESKTOP_VISUAL_QA        | PASS — 1280/1440/1920; также 768/1024                                                                                 |
| LIGHT_DARK_QA            | PASS — все четыре состояния                                                                                           |
| CHROMIUM_WEBKIT_QA       | PASS — 144 фактических сочетания и независимый просмотр                                                               |
| ACCESSIBILITY_QA         | PASS — перечисленные автоматизированные/браузерные проверки; native AT NOT_VERIFIED                                   |
| INDEPENDENT_REVIEW       | PASS — code и actual screenshot review; блокеров нет                                                                  |
| CI_EXACT_HEAD            | NOT_RUN в статическом пакете; фактический итог точного pushed HEAD фиксируется отдельно в PR/Issue                    |
| DEV_INTEGRATION          | NOT_RUN в статическом пакете; merge, post-push CI и Windows health/RBAC/feature smoke фиксируются после их выполнения |

Актуальные SHA, aggregate `checks`, merge и DEV receipts публикуются в [существующем комментарии #827](https://github.com/MikeMoore1337/your-fitness-coach/issues/827#issuecomment-6515401187). Это операционные факты GitHub, не локальный контроллер доставки. Отдельное принятие владельцем реального AFTER и физического устройства здесь не заявляется.
