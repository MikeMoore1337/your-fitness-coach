# YFC final issue coverage matrix

Аудит выполнен 2026-10-11 по GitHub Issue, комментариям владельца, связанным PR, актуальным веткам, исходникам, тестам и Checks. Срез кода: `origin/master=a70fa8a1493c2f1ad0711c3143ab7700c96a92f4`; мобильный интеграционный PR #927 — `06cc0dbeaae04479cedfac1f7b860aa51dadd326` (source fix `be3d2a2a0ffac3e27c44029578f3354197387736`, evidence `f3475375f5b7ba59814ae4b9ccb8a78138cb1b08`).

Статусы означают покрытие отдельных критериев, а не только наличие номера Issue в PR:

- `IMPLEMENTED_VERIFIED` — критерии подтверждены кодом и адресными проверками; остаётся обычная приёмка/релизный gate.
- `IMPLEMENTED_NEEDS_ACCEPTANCE` — техническая реализация и проверки есть, требуется визуальная или release-приёмка владельца.
- `PARTIALLY_IMPLEMENTED` — подтверждена только часть критериев.
- `NOT_IMPLEMENTED` — в актуальном production-коде нет требуемой реализации и отсутствует действующий owner gate, позволяющий начать её в этом пакете.
- `NOT_IMPLEMENTED_OWNER_GATE` — требуемой production-реализации нет; Issue остановлена зафиксированным owner gate, поэтому локальное предложение/evidence не объявляется AFTER.
- `BLOCKED_OWNER_INPUT` — дальнейшее поведение требует решения владельца.
- `NOT_REPRODUCED` — заявленный дефект не воспроизведён в текущем состоянии.
- `INTENDED_BEHAVIOR` — проверенный сценарий соответствует контракту и не является дефектом.

## #859 — [Mobile UX Audit][Index] План, Прогресс и связанные дефекты — журнал владельца 2026-10-08

**Приоритет:** индексный реестр. **Итог:** `IMPLEMENTED_NEEDS_ACCEPTANCE`.

| Критерий | Состояние | PR/commit, код и тесты | Доказательство, остаток, owner gate |
|---|---|---|---|
| Реестр дочерних мобильных требований #860–#874 | Проверен | #915 `e88ba039…`, #927 `f3475375…`; матрица и issue history | [Issue #859](https://github.com/MikeMoore1337/your-fitness-coach/issues/859), [PR #915](https://github.com/MikeMoore1337/your-fitness-coach/pull/915), [PR #927](https://github.com/MikeMoore1337/your-fitness-coach/pull/927) |
| Не создавать отдельную реализацию индексной задачи | Выполнено | Изменений по самой #859 нет | Остальные строки ниже оценивают каждое дочернее требование отдельно; закрытие — после owner acceptance пакета |

## #860 — V9-01: «Показать изменения» не открывает preview замены упражнения

**Приоритет:** P1. **Итог:** `IMPLEMENTED_NEEDS_ACCEPTANCE`.

| Критерий | Состояние | PR/commit, код и тесты | Доказательство и остаток |
|---|---|---|---|
| Видимая реакция на «Показать изменения» | Реализовано | [PR #907](https://github.com/MikeMoore1337/your-fitness-coach/pull/907), `9a6594af1d674eaf4ca1bc419b0569c5a5a6c036`; replacement preview components | Frontend unit/E2E в PR #907 и интеграционных Checks #915/#927 |
| Корректные preview/apply | Реализовано | `frontend/src/features/workouts/WorkoutAdaptation.tsx`, связанные adaptation API/types | Playwright V9-01 preview/apply |
| Ошибка или отсутствие альтернатив | Реализовано | состояние error/empty в adaptation flow | Адресные V9-01 тесты |
| Retry | Реализовано | retry action в adaptation flow | Playwright retry path |
| Безопасность текущей тренировки | Реализовано | замена ограничена untouched exercise; фактические данные защищены | Playwright `does not offer replacement after target has actual data`, safety-stop |
| Будущая программа не изменяется | Реализовано | mutation scoped to current workout/exercise | Desktop/mobile V9-01 scope tests |
| Владелец принимает интегрированный UI | Ожидает | #915/#927 сохраняют изменения без дубля #907 | Требуется `IMPLEMENTED_AWAITING_OWNER_APPROVAL` для релиза |

## #861 — Поиск и выбор упражнений: результаты перекрываются и тесны при клавиатуре

**Приоритет:** P1. **Итог:** `NOT_IMPLEMENTED_OWNER_GATE`.

| Критерий | Состояние | Факт |
|---|---|---|
| Отдельная доступная область выбора | Не реализовано | В актуальном графе нет отдельного PR/коммита по #861 |
| Сохранение черновика редактора | Не подтверждено | Нет адресного production-факта и теста |
| Поиск длинных названий и выбор | Не подтверждено | Нет отдельного acceptance evidence |
| Техника как отдельное действие | Не подтверждено | Не найдено изменение scope |
| Клавиатура, закрытие, восстановление фокуса | Не реализовано | Нет теста #861 |
| Отсутствие перекрытий | Не подтверждено | Не считать общую mobile-регрессию доказательством |
| Owner approval | Требуется до реализации | В истории Issue зафиксирован `STOP_OWNER_UI_APPROVAL`; реализацию не начинал |

## #862 — Редактор программы: крестик, поля, дни и сохранение

**Приоритет:** P1. **Итог:** `NOT_IMPLEMENTED_OWNER_GATE`.

| Критерий | Состояние | Факт |
|---|---|---|
| Заголовок и закрытие в одной строке | Не реализовано | Нет PR по #862 |
| Читаемые поля повторений | Не подтверждено | Нет адресного evidence |
| Несколько дней и перестановка упражнений | Не подтверждено | Доменный контракт не изменялся |
| Сохранение и защита несохранённых изменений | Не подтверждено | Нет acceptance test |
| Скрытые параметры не теряются | Не подтверждено | Нет targeted regression |
| Owner approval | Требуется до реализации | В истории Issue зафиксирован `STOP_OWNER_UI_APPROVAL`; не смешивать с #861 |

## #863 — «План»: иерархия, рекомендации, история и управление

**Приоритет:** P1. **Итог:** `NOT_IMPLEMENTED_OWNER_GATE`.

| Критерий | Состояние | Факт |
|---|---|---|
| Текущая программа, неделя/этап и ближайшая тренировка | Не подтверждено | Нет отдельного production change по #863 |
| Понятное главное действие и компактное управление | Не подтверждено | Нет acceptance evidence |
| История и рекомендации доступны | Не подтверждено | Нет адресного теста |
| Нет бессмысленных повторных сообщений | Не подтверждено | Нет регрессионного доказательства |
| Четырёхнедельный этап не смешивается с 8-недельным горизонтом | Не подтверждено | Не менял алгоритм календаря без реализации задачи |

## #864 — «План»: компактное расписание ближайших 8 недель

**Приоритет:** P1. **Итог:** `NOT_IMPLEMENTED_OWNER_GATE`.

| Критерий | Состояние | Факт |
|---|---|---|
| Компактные ближайшие тренировки | Не реализовано | Нет PR по #864 |
| Раскрытие полного горизонта и сохранение всех 8 недель | Не подтверждено | Нет адресного теста |
| Корректные статусы и контекстное управление | Не подтверждено | Нет acceptance evidence |
| Доступна последняя строка | Не подтверждено | Нет геометрического теста |
| Алгоритм календаря не меняется | Сохранён | Изменений алгоритма в рамках аудита нет |

## #865 — «Прогресс»: компактный обзор, навигация и пустые состояния

**Приоритет:** P1. **Итог:** `PARTIALLY_IMPLEMENTED`.

| Критерий | Состояние | PR/код и тесты | Остаток |
|---|---|---|---|
| Верхняя навигация разделов | Реализовано ранее | #915 `e88ba039…`, #927 `f3475375…`; `frontend/src/features/progress/` | Повторно не переносилась |
| Компактный обзор и заголовок | Частично | Progress UI входит в согласованный пакет B | Полный acceptance #865 не закрыт |
| Выбранный период | Частично | Сегменты/selected-state проверялись в #927 | Нет полной матрицы метрик/пустых состояний |
| Достоверные показатели и отсутствие повторных предупреждений | Не подтверждено | Нет отдельного #865 evidence | Нужна адресная реализация/проверка |
| Переходы в подразделы | Частично | Навигация существует | Подразделы и report flow оцениваются отдельно #873/#874 |

## #866 — Компактные завершённые упражнения

**Приоритет:** P1. **Итог:** `NOT_IMPLEMENTED_OWNER_GATE`.

| Критерий | Состояние | Факт |
|---|---|---|
| Компактная карточка завершённого упражнения | Не реализовано | Нет PR по #866 |
| Сохранение фактических результатов | Не подтверждено | Нельзя считать общей active-workout регрессией |
| Доступная техника и корректные отступы | Не подтверждено | Нет targeted test |
| Компактные пустые личные настройки | Не подтверждено | Нет evidence |
| Отсутствие потери данных | Не подтверждено | V12 #826 не активировался |

## #867 — Сквозная геометрия: переполнение, dock и плавающий +

**Приоритет:** P1. **Итог:** `IMPLEMENTED_NEEDS_ACCEPTANCE`.

| Критерий | Состояние | PR/commit, код и тесты | Постоянное evidence |
|---|---|---|---|
| Нет горизонтального переполнения | Подтверждено | #927 `be3d2a2…`; `design-v2.css`; `active-workout-experience.spec.ts` | [Chromium AFTER 320 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/chromium/resting-dock-320-dark.png) |
| Последние элементы доступны при реальных положениях scroll | Исправлено | `TodayWorkout.tsx` re-queries committed set and reserves dock clearance | [Chromium AFTER 430 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/chromium/resting-dock-430-light.png) |
| Current set CTA не перекрывается dock | Исправлено | `useLayoutEffect` + post-queue reconciliation, 8 px safe gap | [WebKit AFTER 320 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/webkit/resting-dock-320-dark.png) |
| Видимый следующий set не перекрывается dock | Исправлено | geometry checks include next visible controls and `elementFromPoint` | [WebKit AFTER 393 light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/after/webkit/resting-dock-393-light.png) |
| Safe-area, нижняя навигация, клавиатура, touch и TMA | Подтверждено адресно | 68 Chromium #914/#867 tests; 8 WebKit geometry tests; existing TMA/reload/offline tests | [provenance](https://github.com/MikeMoore1337/your-fitness-coach/blob/f3475375f5b7ba59814ae4b9ccb8a78138cb1b08/docs/ux/final-issues-acceptance/evidence/867/provenance.json) |
| Не считать нормальный scroll под стеклом дефектом | Сохранено | Проверяется только недоступность/hit-test, а не сам факт прокрутки | Owner visual/release acceptance остаётся |

## #868 — Глобальное «+ → Вода»

**Приоритет:** P1. **Итог:** `IMPLEMENTED_NEEDS_ACCEPTANCE`.

| Критерий | Состояние | PR/commit, код и тесты | Остаток |
|---|---|---|---|
| Прямой переход к гидратации | Реализовано | [PR #908](https://github.com/MikeMoore1337/your-fitness-coach/pull/908), `5023563aba71f11cf742a3a6b6d49d9d8bfb105f` | Владелец принимает интегрированный маршрут |
| Фокус на блоке воды | Реализовано | hydration route/focus logic in #908 | Проверено в targeted E2E |
| Черновики не сбрасываются | Реализовано | #908 preserves draft state | Повторный переход покрыт тестом |
| Корректная browser history | Реализовано | #908 navigation contract | Release acceptance pending |

## #869 — Кнопки гидратации и вложенные разделы питания

**Приоритет:** P2. **Итог:** `PARTIALLY_IMPLEMENTED`.

| Критерий | Состояние | PR/commit и код | Остаток |
|---|---|---|---|
| Полные подписи объёмов воды | Реализовано | [PR #909](https://github.com/MikeMoore1337/your-fitness-coach/pull/909), `c56cc2b37347d781846bf80566634ba19c900525`; nutrition UI | Owner acceptance pending |
| Дневник питания | Не подтверждено в полном acceptance | Existing diary preserved | Нет полного #869 evidence |
| Быстрый ввод | Частично | Existing quick add and #927 sheet preserved | Нужен сквозной acceptance |
| План питания | Не подтверждено | No dedicated implementation in #915/#927 | Остаток |
| Список покупок | Не подтверждено | No dedicated implementation in #915/#927 | Остаток |
| История | Не подтверждено | Existing route not audited to #869 criteria | Остаток |
| Все действия и данные сохраняются | Частично | No business logic changes | Нужна regression matrix |

## #870 — Профиль: обрезанные цели, дубли меню и списки предпочтений

**Приоритет:** P2. **Итог:** `PARTIALLY_IMPLEMENTED`.

| Критерий | Состояние | PR/commit и код | Остаток |
|---|---|---|---|
| Полное отображение выбранной цели | Реализовано | [PR #910](https://github.com/MikeMoore1337/your-fitness-coach/pull/910), `e35b988ecb9ba71f0e169c68596f2d53096f7373` | Owner acceptance pending |
| Настройки и предпочтения не удаляются | Сохранено | Profile components unchanged outside display fix | Нужна полная acceptance проверка |
| Нет дублирующего меню | Не подтверждено | No independent proof in #910 | Остаток |
| Списки предпочтений удобны на mobile | Не подтверждено | No full #870 audit evidence | Остаток |
| Раскрытый экран не обязан быть initial state | Сохранено | No forced initial-open behavior added | Остаток acceptance |

## #871 — Малые экраны: итоги тренировки, справочник и дата напоминания

**Приоритет:** P2. **Итог:** `BLOCKED_OWNER_INPUT`.

| Критерий | Состояние | PR/commit и проверки | Остаток/решение владельца |
|---|---|---|---|
| Calendar guard не допускает прошедшие даты | Реализовано/проверено | [PR #911](https://github.com/MikeMoore1337/your-fitness-coach/pull/911), `578f5704cac780c02720e84cff2a96cdb7dd481e`; guard tests | Не менять INTENDED сценарии без новых доказательств |
| Итоги тренировки и справочник на малых экранах | Не подтверждено полностью | No dedicated production implementation | Независимо от owner gate требует отдельного acceptance |
| Сегодня выбрано, но час напоминания уже прошёл | Заблокировано | Product semantics отсутствует | Сравнение: (A) перенести на следующий допустимый день — безопаснее для предсказуемости; (B) сохранить сегодня и показать явное предупреждение — сохраняет намерение, но требует повторного действия; рекомендация владельцу — B только с явным подтверждением пользователя, иначе A. Решение не придумывалось в коде |

## #873 — Подробные подразделы Прогресса

**Приоритет:** P2. **Итог:** `NOT_IMPLEMENTED_OWNER_GATE`.

| Критерий | Состояние | Факт |
|---|---|---|
| Тело | Не подтверждено | Нет отдельной реализации/evidence |
| Тренировки | Не подтверждено | Нет отдельной реализации/evidence |
| Питание | Не подтверждено | Нет отдельной реализации/evidence |
| Кардио | Не подтверждено | Нет отдельной реализации/evidence |
| Самочувствие | Не подтверждено | Нет отдельной реализации/evidence |
| История | Не подтверждено | Нет отдельной реализации/evidence |
| Реальные метрики, редактирование, раскрытия, графики и no-data semantics | Не подтверждено | Нули вместо отсутствующих данных не вводились |

## #874 — Отчёт о прогрессе: таблицы, печать/PDF и предупреждения

**Приоритет:** P1. **Итог:** `NOT_IMPLEMENTED_OWNER_GATE`.

| Критерий | Состояние | Факт |
|---|---|---|
| Прогресс → Скачать отчёт → период | Не подтверждено | Нет полного production flow evidence |
| Выбор упражнений и просмотр | Не подтверждено | Нет targeted test |
| Все периоды и mobile geometry | Не подтверждено | Нет evidence |
| Таблицы и русская типографика | Не подтверждено | Нет independent PDF proof |
| Нет ложного сравнения при одной записи | Не подтверждено | Server-owned calculations не менялись |
| Browser PDF и server PDF численно совпадают | Не подтверждено | Нет print/server artifact |
| В печати нет интерактивных контролов | Не подтверждено | Нет print regression |
| Приватность экспорта/публикации | Не подтверждено | Нет acceptance evidence |

## #903 — Убрать квадратные обводки у круглых оценок «Проверки недели»

**Приоритет:** P2. **Итог:** `IMPLEMENTED_NEEDS_ACCEPTANCE`.

| Критерий | Состояние | PR/commit и проверки | Evidence/остаток |
|---|---|---|---|
| Круглая шкала 1–5 без квадратных рамок | Реализовано | [PR #936](https://github.com/MikeMoore1337/your-fitness-coach/pull/936), source [`733933a7`](https://github.com/MikeMoore1337/your-fitness-coach/commit/733933a73a3bc27ca596b9efb00751105a539a86); `landing-v10.css` | [E2E spec](https://github.com/MikeMoore1337/your-fitness-coach/blob/c40a64eedb467bb33938a1cf6165d5878ed0d56b/frontend/tests/e2e/landing-903.spec.ts), [BEFORE/AFTER evidence](https://github.com/MikeMoore1337/your-fitness-coach/tree/c40a64eedb467bb33938a1cf6165d5878ed0d56b/docs/ux/final-issues-acceptance/evidence/903) |
| Selected-state остаётся видимым | Реализовано | Circular lime-tinted selected surface/inset ring | Визуальная приёмка владельца pending |
| Focus-visible сохраняется | Реализовано | `input:focus-visible + span` outline; pointer selection не добавляет focus ring | Chromium и WebKit targeted по 8 passed (оба публичных маршрута) |
| Native radio semantics | Реализовано | Native inputs retained | Typecheck/lint/build passed |
| Touch target ≥44×44 | Реализовано | CSS label min dimensions and E2E geometry | Owner visual acceptance pending |
| Dark/light, mobile/desktop, `/` и `/for-athletes` | Реализовано | `landing-903.spec.ts` — Chromium 8 и WebKit 8 passed локально; PR #936 head [`c40a64ee`](https://github.com/MikeMoore1337/your-fitness-coach/commit/c40a64eedb467bb33938a1cf6165d5878ed0d56b) | GitHub Checks для нового head остаются release gate; owner visual acceptance pending |

## #904 — 403 на GET `/api/v1/coach/inbox` в демо тренера

**Приоритет:** P1. **Итог:** `IMPLEMENTED_NEEDS_ACCEPTANCE`.

| Критерий | Состояние | PR/commit и тесты | Остаток |
|---|---|---|---|
| Воспроизвести запрос и снять sanitized response | Выполнено | [PR #939](https://github.com/MikeMoore1337/your-fitness-coach/pull/939), `3c2d0e2783a8cecf02aa13adc5a68af9900abd13`; `backend/tests/test_demo.py` | CI/release acceptance pending |
| Проверить user/role/scope/ownership | Выполнено | Trainer scenario returns 200; self-training scenario remains 403 | No RBAC weakening |
| Исправить demo transport минимально | Выполнено | `backend/fitminiapp_api/services/demo_transport.py` adds trainer-only synthetic fixture | Production endpoints unchanged |
| Positive/negative auth tests | Выполнено | 21 demo tests passed; trainer 200, self-training 403 | Owner/release acceptance pending |
| No writes to real user DB | Выполнено | Synthetic response only; count invariant asserted | No production mutation |
| Chromium/WebKit | Частично подтверждено | API tests plus CI smoke; no production browser credentials used | Post-merge demo smoke remains release gate |

## #905 — 403 на `/api/v1/programs/exercises/1001/history` в демо

**Приоритет:** P1. **Итог:** `IMPLEMENTED_NEEDS_ACCEPTANCE`.

| Критерий | Состояние | PR/commit и тесты | Остаток |
|---|---|---|---|
| Воспроизвести 403 и определить контракт | Выполнено | PR #939 root cause: missing demo transport handler | CI/release acceptance pending |
| Trainer/self-training scope | Выполнено | Trainer fixture 1001 returns 200; unknown exercise/scenario remains 403 | Ownership checks retained |
| Positive/negative tests and no foreign data | Выполнено | `backend/tests/test_demo.py`, 21 passed | Owner/release acceptance pending |
| No production writes | Выполнено | Synthetic validated response, no DB mutation | No production mutation |
| Chromium/WebKit | Частично подтверждено | Transport and smoke checks; real production verification intentionally not claimed | Post-deploy gate if needed |

## #906 — Hero на 2K-мониторах

**Приоритет:** P2. **Итог:** `NOT_IMPLEMENTED_OWNER_GATE`.

| Критерий | Состояние | Факт и дальнейшее действие |
|---|---|---|
| Высота Hero, кадрирование лица/объектов, пропорции | Предложено, production не менялся | [Локальное сравнение BEFORE/A/B](evidence/906/README.md); runtime `733933a73a3bc27ca596b9efb00751105a539a86` |
| 1440×900, 1920×1080, 2560×1440 | Снято как proposal | [Athletes QHD BEFORE/A/B](evidence/906/README.md) · [Trainers QHD BEFORE/A/B](evidence/906/README.md) |
| Обе темы и обе аудитории | Снято как proposal | Chromium, dark/light, `/for-athletes` и `/for-trainers`; production AFTER отсутствует |
| Парные BEFORE/A/B | Опубликованы | [evidence/906](evidence/906/README.md) и [provenance](evidence/906/provenance.json) |
| Owner approval | Требуется | Владелец выбирает A или B и допустимую высоту; до этого не создавать production PR |

## Исключённая из этого аудита задача

`#872` явно исключена последним запросом владельца. XLSX import без исходного файла и отдельного согласования не начинался.

## Прямой визуальный индекс для частично подтверждённых и owner-gated Issues

Все ссылки ниже закреплены за конкретными SHA. `reference` означает, что кадр показывает существующий маршрут или общий компонент, но не закрывает весь acceptance criterion; такой кадр не повышает статус Issue до реализованной.

| Issue | BEFORE / PROPOSAL / AFTER evidence | Runtime и предел доказательства |
|---|---|---|
| #861 | [AFTER reference: Plan 320 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-320-dark-programs.png) · [light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-320-light-programs.png) | Mobile release runtime; search/editor keyboard criteria отсутствуют |
| #862 | [AFTER reference: Plan 360 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-360-dark-programs.png) · [light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-360-light-programs.png) | Общий Plan reference; editor save/hidden params не доказаны |
| #863 | [AFTER reference: Plan 320 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-320-dark-programs.png) · [light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-320-light-programs.png) | Общий Plan reference; full hierarchy/history/recommendations не доказаны |
| #864 | [AFTER reference: Plan 393 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-393-dark-programs.png) · [light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-393-light-programs.png) | Общий Plan reference; 8-week horizon/last row не доказаны |
| #865 | [AFTER reference: Progress 320 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-320-dark-progress.png) · [light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-320-light-progress.png) | Compact overview reference; metrics/empty-state acceptance partial |
| #866 | [AFTER reference: workout 360 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-360-dark-workout.png) · [light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-360-light-workout.png) | Active workout reference; completed-exercise acceptance absent |
| #869 | [AFTER reference: Nutrition 393 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-393-dark-nutrition.png) · [light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-393-light-nutrition.png) | Nutrition reference; diary/plan/grocery/history remains partial |
| #870 | [PR #910](https://github.com/MikeMoore1337/your-fitness-coach/pull/910) | No trustworthy profile screenshot in this package; visual acceptance absent |
| #873 | [AFTER reference: Progress 430 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-430-dark-progress.png) · [light](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-430-light-progress.png) | Progress reference; detailed subsections/no-data semantics unproven |
| #874 | [AFTER reference: Progress 393 dark](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/38b302a3b0ea3df3dfa6ffd2c46e68ac08b6d92f/docs/ux/mobile-release-859-914/after/chromium-393-dark-progress.png) · [browser PDF](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/ee92508da30ed5eed5e3e3914754515e4a278c25/docs/ux/mobile-859-glass-polish/pdf/browser-after.pdf) · [server PDF](https://raw.githubusercontent.com/MikeMoore1337/your-fitness-coach/ee92508da30ed5eed5e3e3914754515e4a278c25/docs/ux/mobile-859-glass-polish/pdf/server-after.pdf) | Browser/server artifacts exist, but current full report contract is not proven |

## Технические gates и ограничения

- #907–#911 не изменялись.
- `MASTER_SHA=c922851b082dfbacc580d78f9e6e5dc60cb23522`; master не изменялся.
- `MERGE=FORBIDDEN`, `DEPLOY=FORBIDDEN`, production mutations не выполнялись.
- #871 (семантика прошедшего часа напоминания) и #906 (visual Hero) требуют решения владельца.
- #861–#864, #866, #873, #874, #906 имеют реальные недостающие production части и явно помечены `NOT_IMPLEMENTED_OWNER_GATE`; их нельзя объявлять выполненными по общей интеграции #915/#927.
