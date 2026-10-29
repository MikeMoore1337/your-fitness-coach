# #1326 - редизайн «Центр управления», проверка v2 через AI Development Toolkit

## Статус

`DESIGN_DIRECTION_OWNER_ACCEPTED=A`; `FINAL_VISUAL=NOT_APPROVED`; `IMPLEMENTATION=NOT_STARTED`; `DEPLOY=NOT_DONE`. **Нельзя сливать этот Draft PR до явного подтверждения дизайна.**

### Почему v1 заменён

Предыдущий набор из 24 SVG имел ошибки относительно YFC: неправильный dock (пункты «Тренировка» и «Ещё»), одностороннюю толстую лаймовую грань, недостаточно компактный mobile-обзор. Макеты v1 заменены в этом PR.

## Проверка через Toolkit

- UX/UI Design Orchestra `audit-proposal`, TOOLKIT `bdc9223b7cfd33ea52cd8540e2e4921acc4cbe87` с тремя обязательными CI PASS; работа последовательно без реальных субагентов.
- Три **реально нарисанных и просмотренных** варианта: A1 карточный обзор, A2 компактный командный пульт, A3 приоритет действий. Выбран A2: минимальный вертикальный путь без потери текущей программы; A1 отклонён из-за длины, A3 из-за мелких плиток на 320.
- Impeccable, Taste, UI UX Pro Max **не запускались**: ссылки `REFERENCE_ONLY`, не выдавать за executed agents.
- Проверка точного текущего дизайн-контракта: `AGENTS.md`, `ACTIVE_DESIGN_SOURCE.md`, `DESIGN_GUARDRAILS.md`, `YFC_PRODUCT_UI_CONTRACT.md`.

## Визуальный пакет v2

SVG ниже - **векторные схемы**, не реальные production screenshots. Отдельно в беседе с владельцем предоставлены сгенерированные Chromium PNG и автономный HTML-прототип; путать их с проверкой YFC нельзя.

| Экран | Dark | Light |
|---|---|---|
| Обзор 320 | ![](toolkit-v2/dark-overview-320.svg) | ![](toolkit-v2/light-overview-320.svg) |
| Обзор 360 | ![](toolkit-v2/dark-overview-360.svg) | ![](toolkit-v2/light-overview-360.svg) |
| Обзор 393 | ![](toolkit-v2/dark-overview-393.svg) | ![](toolkit-v2/light-overview-393.svg) |
| Обзор 430 | ![](toolkit-v2/dark-overview-430.svg) | ![](toolkit-v2/light-overview-430.svg) |
| Desktop 1440 | ![](toolkit-v2/dark-overview-desktop.svg) | ![](toolkit-v2/light-overview-desktop.svg) |
| operations | ![](toolkit-v2/dark-operations-393.svg) | ![](toolkit-v2/light-operations-393.svg) |
| replace | ![](toolkit-v2/dark-replace-393.svg) | ![](toolkit-v2/light-replace-393.svg) |
| library | ![](toolkit-v2/dark-library-393.svg) | ![](toolkit-v2/light-library-393.svg) |
| create | ![](toolkit-v2/dark-create-393.svg) | ![](toolkit-v2/light-create-393.svg) |
| empty | ![](toolkit-v2/dark-empty-393.svg) | ![](toolkit-v2/light-empty-393.svg) |
| trainer | ![](toolkit-v2/dark-trainer-393.svg) | ![](toolkit-v2/light-trainer-393.svg) |
| delete | ![](toolkit-v2/dark-delete-393.svg) | ![](toolkit-v2/light-delete-393.svg) |
| loading | ![](toolkit-v2/dark-loading-393.svg) | ![](toolkit-v2/light-loading-393.svg) |
| error | ![](toolkit-v2/dark-error-393.svg) | ![](toolkit-v2/light-error-393.svg) |
| pending | ![](toolkit-v2/dark-pending-393.svg) | ![](toolkit-v2/light-pending-393.svg) |

## Функции и ограничения

1. Обзор: название, статус, цель, уровень, дни, просмотр состава и редактирование/личная копия только по существующим правам.
2. Четыре операции: назначения/версии (AssignedProgramDetails), замена (ProgramRecommendation + LegacyProgramRecommendation и расписание), библиотека/скрытые, создание/импорт (существующие ProgramBuilder и ProgramImportPanel). Редактор #1323 - тот же вход, без дублирования.
3. Доступ: PublicProgramSharePanel только владельцу, полноширинное удаление сразу под ним по #1229 и с тем же подтверждением.
4. Trainer read-only, empty/loading/error/pending, API 409 и активная тренировка сохраняют прежние ограничения. Deep links `view=manage`, `start=templates/create/generator`, фокус/скролл при возврате - обязательные критерии будущей реализации.
5. Mobile dock: **Сегодня / План / Питание / Прогресс / Добавить**, матовая панель, текущий пункт на общей капсуле, safe area, отсутствие толстых лаймовых боковых полос.
6. API/БД, права, история выполненных тренировок, автопубликация и самопроизвольное назначение не меняются.

## Проверки

Автономный HTML-макет, отдельно размещённый в беседе владельца: **33/33 PASS в Chromium** на 320/360/393/430/1440, Dark/Light, 10 экранов-состояний, навигация/возврат/тема, подтверждение/Escape. Это **не** React E2E и не доказательство доступности в Safari/WebKit, PWA, TMA или физическом iPhone.

## Следующий gate

Только после отдельного **явного утверждения конкретных финальных Dark/Light макетов** владельцем можно изменить React/CSS в `/app?section=programs&view=manage`, затем провести unit/Playwright Chromium+WebKit, реальный AFTER, iPhone/PWA/TMA, требуемый CI и получить отдельные разрешения на merge и deploy.
