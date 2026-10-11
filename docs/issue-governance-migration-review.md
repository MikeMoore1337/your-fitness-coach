# Предварительный обзор миграции Issues

Снимок: 2026-10-12, открытые Issues (только чтение). Основан на названиях, **не** на содержимом всех описаний и не на подтверждённой готовности DoR.

- Открытых Issues: **82**
- Открытых Pull Requests: **12**
- Существующие задачи не переименованы и не закрыты. Эта таблица - **предложение для owner review**, не инструкция безусловного применения.
- Поля Priority, Effort, Status, Parent/Sub-issues и Blocking намеренно **не угаданы** по одному заголовку. Сначала нужно изучить содержимое Issue, связанные PR и текущий lifecycle.
- Строки «проверить» могут объединять bug и улучшения; перед миграцией требуется решение по классификации.
- Предыдущие префиксы в заголовках, например [P1], нельзя считать точным действующим Priority до проверки контрактов задач.
- Продуктовые задачи остаются в исходных версиях V11/V12/V13.

| Issue | Текущее название | Предлагаемый префикс | Уверенность |
|---|---|---|---|
| [#960](https://github.com/MikeMoore1337/your-fitness-coach/issues/960) | [UI Backlog][Workout] Плановый и фактический отдых: таймер, история, отчёты и Coach OS | [UI Backlog] | проверить |
| [#959](https://github.com/MikeMoore1337/your-fitness-coach/issues/959) | [UI Backlog][Index] Единый журнал UI/UX-идей и улучшений YFC | [UI Backlog] | высокая |
| [#957](https://github.com/MikeMoore1337/your-fitness-coach/issues/957) | V13-08 - Сквозная приёмка Nutrition v13 и production release | [Product V13] | высокая |
| [#956](https://github.com/MikeMoore1337/your-fitness-coach/issues/956) | V13-07 - Необязательные заметки: голод, сытость и контекст приёма пищи | [Product V13] | высокая |
| [#955](https://github.com/MikeMoore1337/your-fitness-coach/issues/955) | V13-06 - Надёжный фото- и текстовый ввод питания: качество и бесплатный провайдер | [Product V13] | высокая |
| [#954](https://github.com/MikeMoore1337/your-fitness-coach/issues/954) | V13-05 - Coach OS: планирование и проверка питания клиента | [Product V13] | высокая |
| [#953](https://github.com/MikeMoore1337/your-fitness-coach/issues/953) | V13-04 - Объяснимые предложения питания и коррекция рациона | [Product V13] | высокая |
| [#952](https://github.com/MikeMoore1337/your-fitness-coach/issues/952) | V13-03 - Цели КБЖУ по дням и тренировочным циклам | [Product V13] | высокая |
| [#951](https://github.com/MikeMoore1337/your-fitness-coach/issues/951) | V13-01 - Быстрый поиск, массовый выбор продуктов и порции | [Product V13] | высокая |
| [#950](https://github.com/MikeMoore1337/your-fitness-coach/issues/950) | V13-00 - Factual Nutrition UX baseline & release contracts | [Product V13] | высокая |
| [#949](https://github.com/MikeMoore1337/your-fitness-coach/issues/949) | Product v13 - Nutrition Intelligence & Fast Logging | [Product V13] | высокая |
| [#948](https://github.com/MikeMoore1337/your-fitness-coach/issues/948) | [Nutrition][Mobile][P1] Выдача поиска: названия и пищевая ценность обрезаны, продукты не различить | [Bug] | высокая |
| [#947](https://github.com/MikeMoore1337/your-fitness-coach/issues/947) | [Nutrition][Mobile][P1] Выделение продукта: контраст текста пропадает на лаймовой подложке | [Bug] | высокая |
| [#946](https://github.com/MikeMoore1337/your-fitness-coach/issues/946) | [Nutrition][Mobile][P1] Поиск продукта: открытая клавиатура перекрывает поле и результаты | [Bug] | высокая |
| [#931](https://github.com/MikeMoore1337/your-fitness-coach/issues/931) | Hermes: исправить проверку предыдущего prompt manifest при обновлении/rollback | [Bug] | проверить |
| [#920](https://github.com/MikeMoore1337/your-fitness-coach/issues/920) | [Programs][P1][Cycle] Редактирование повторяющейся программы на лету без потери истории и статистики | [Product V12] | высокая |
| [#919](https://github.com/MikeMoore1337/your-fitness-coach/issues/919) | [Programs][P1][Cycle] Повтор короткого шаблона 1/3/... недель на произвольный срок программы | [Product V12] | высокая |
| [#918](https://github.com/MikeMoore1337/your-fitness-coach/issues/918) | [Programs][P1][UX] Настройка произвольной периодизации и типов недель - owner-gated UI | [Product V12] | высокая |
| [#917](https://github.com/MikeMoore1337/your-fitness-coach/issues/917) | [Programs][P1][Periodization] Раздельная прогрессия и аналитика лёгких/средних/тяжёлых недель | [Product V12] | высокая |
| [#916](https://github.com/MikeMoore1337/your-fitness-coach/issues/916) | [Programs][P1][Periodization] Необязательные типы недель и циклы произвольной длины - domain foundation | [Product V12] | высокая |
| [#914](https://github.com/MikeMoore1337/your-fitness-coach/issues/914) | [Mobile][P1][Active Workout] Таймер отдыха: ошибочное переключение подхода и быстрые +30/+60 сек | [Bug] | высокая |
| [#913](https://github.com/MikeMoore1337/your-fitness-coach/issues/913) | [Product v13][V13-02][NI-10] Детальный PDF-адаптер отчёта FatSecret в тот же импорт питания | [Product V13] | высокая |
| [#912](https://github.com/MikeMoore1337/your-fitness-coach/issues/912) | [Product v13][V13-02][NI-09] Безопасный импорт по ссылке на отчёт FatSecret (URL transport) | [Product V13] | высокая |
| [#906](https://github.com/MikeMoore1337/your-fitness-coach/issues/906) | [Landing][UI][P2] Hero на 2K-мониторах: увеличить высоту и исправить кадрирование фото | [UI Backlog] | проверить |
| [#905](https://github.com/MikeMoore1337/your-fitness-coach/issues/905) | [DemoCabinet][P1] Разобраться с 403 на истории упражнения /api/v1/programs/exercises/1001/history | [Bug] | высокая |
| [#904](https://github.com/MikeMoore1337/your-fitness-coach/issues/904) | [DemoCabinet][P1] Разобраться с 403 на GET /api/v1/coach/inbox в демо тренера | [Bug] | высокая |
| [#903](https://github.com/MikeMoore1337/your-fitness-coach/issues/903) | [Landing][UI][P2] Убрать квадратные обводки у круглых оценок «Проверки недели» | [UI Backlog] | высокая |
| [#888](https://github.com/MikeMoore1337/your-fitness-coach/issues/888) | [Product v13][V13-02][NI-08] Комплексные QA, безопасность, производительность и релизные проверки | [Product V13] | высокая |
| [#887](https://github.com/MikeMoore1337/your-fitness-coach/issues/887) | [Product v13][V13-02][NI-07] Опциональный перенос дат и истории приёмов пищи в личный дневник YFC | [Product V13] | высокая |
| [#886](https://github.com/MikeMoore1337/your-fitness-coach/issues/886) | [Product v13][V13-02][NI-06] Создание шаблонов повторяющихся приёмов пищи из импорта | [Product V13] | высокая |
| [#885](https://github.com/MikeMoore1337/your-fitness-coach/issues/885) | [Product v13][V13-02][NI-05] Интерфейс импорта CSV/PDF по файлу или ссылке, предпросмотр и подтверждение | [Product V13] | высокая |
| [#884](https://github.com/MikeMoore1337/your-fitness-coach/issues/884) | [Product v13][V13-02][NI-04] Адаптер FatSecret CSV для фактического формата русского дневника | [Product V13] | высокая |
| [#883](https://github.com/MikeMoore1337/your-fitness-coach/issues/883) | [Product v13][V13-02][NI-03] Публикация импортированных продуктов в общий каталог YFC и безопасная дедупликация | [Product V13] | высокая |
| [#882](https://github.com/MikeMoore1337/your-fitness-coach/issues/882) | [Product v13][V13-02][NI-02] Безопасный общий механизм загрузки, предпросмотра и подтверждения импорта | [Product V13] | высокая |
| [#881](https://github.com/MikeMoore1337/your-fitness-coach/issues/881) | [Product v13][V13-02][NI-01] Контракт CSV FatSecret, нормализация и эталонные обезличенные данные | [Product V13] | высокая |
| [#880](https://github.com/MikeMoore1337/your-fitness-coach/issues/880) | [Product v13][V13-02][Nutrition Import] FatSecret -> YFC: общий каталог продуктов и перенос питания | [Product V13] | высокая |
| [#874](https://github.com/MikeMoore1337/your-fitness-coach/issues/874) | [Mobile][P1][Report] Отчёт о прогрессе: обрезанный период, таблицы, печать/PDF и повторяющиеся предупреждения | [Bug] | проверить |
| [#873](https://github.com/MikeMoore1337/your-fitness-coach/issues/873) | [Mobile][P2][Progress Details] Тело, Тренировки, Питание, Кардио и История - меньше вложенности и повторов | [UI Backlog] | высокая |
| [#872](https://github.com/MikeMoore1337/your-fitness-coach/issues/872) | [Programs][P1][Import] XLSX-матрицы недель: независимые от цвета типы, ручной выбор и preview/confirm | [Product V12] | высокая |
| [#871](https://github.com/MikeMoore1337/your-fitness-coach/issues/871) | [Mobile QA][P2] Малые экраны: итоги тренировки, справочник и дата напоминания | [Bug] | проверить |
| [#870](https://github.com/MikeMoore1337/your-fitness-coach/issues/870) | [Mobile][P2][Profile UX] Профиль: обрезанные цели, дубли меню и тесные списки предпочтений | [UI Backlog] | проверить |
| [#869](https://github.com/MikeMoore1337/your-fitness-coach/issues/869) | [Mobile][P2][Nutrition UI] Кнопки гидратации и вложенные разделы питания | [UI Backlog] | проверить |
| [#868](https://github.com/MikeMoore1337/your-fitness-coach/issues/868) | [Mobile][P1][UX-05] Глобальное «+ -> Вода» должно открывать блок гидратации | [Bug] | высокая |
| [#867](https://github.com/MikeMoore1337/your-fitness-coach/issues/867) | [Mobile][P1][UI-03] Сквозная геометрия: горизонтальное переполнение, нижний dock и плавающий + | [Bug] | высокая |
| [#866](https://github.com/MikeMoore1337/your-fitness-coach/issues/866) | [Mobile][P1][UX-11/12] Компактные завершённые упражнения без огромных карточек и прижатых границ | [UI Backlog] | высокая |
| [#865](https://github.com/MikeMoore1337/your-fitness-coach/issues/865) | [Mobile][P1][UX-10] «Прогресс»: компактный обзор, навигация и пустые состояния | [UI Backlog] | высокая |
| [#864](https://github.com/MikeMoore1337/your-fitness-coach/issues/864) | [Mobile][P1][UX-09] «План»: компактное расписание ближайших 8 недель | [UI Backlog] | высокая |
| [#863](https://github.com/MikeMoore1337/your-fitness-coach/issues/863) | [Mobile][P1][UX-08] «План»: перестроить иерархию, свернуть рекомендации, историю и управление | [UI Backlog] | высокая |
| [#862](https://github.com/MikeMoore1337/your-fitness-coach/issues/862) | [Mobile][P1][UX-07] Редактор программы: крестик, вложенные рамки, узкие поля и иерархия дней | [UI Backlog] | проверить |
| [#861](https://github.com/MikeMoore1337/your-fitness-coach/issues/861) | [Mobile][P1][UX-01] Поиск и выбор упражнений: результаты перекрываются и тесны при клавиатуре | [Bug] | высокая |
| [#860](https://github.com/MikeMoore1337/your-fitness-coach/issues/860) | [Mobile][P1][FUNC-04] V9-01: «Показать изменения» не открывает preview замены упражнения | [Bug] | высокая |
| [#859](https://github.com/MikeMoore1337/your-fitness-coach/issues/859) | [Mobile UX Audit][Index] План, Прогресс и связанные дефекты - журнал владельца 2026-10-08 | [UI Backlog] | высокая |
| [#851](https://github.com/MikeMoore1337/your-fitness-coach/issues/851) | [V11-SC-01][P1] Pin application base images and publish backend/bot SBOMs | [Product V11] | высокая |
| [#850](https://github.com/MikeMoore1337/your-fitness-coach/issues/850) | [V11-RUN-01][P1] Harden application containers without runtime regressions | [Product V11] | высокая |
| [#849](https://github.com/MikeMoore1337/your-fitness-coach/issues/849) | [V11-REC-01][P0 / NOT_PROVEN] Off-host recovery contract and clean-host restore evidence | [Product V11] | высокая |
| [#848](https://github.com/MikeMoore1337/your-fitness-coach/issues/848) | [V11-DB-01][P0] Fail-closed PostgreSQL connection budget before rollout | [Product V11] | высокая |
| [#835](https://github.com/MikeMoore1337/your-fitness-coach/issues/835) | V12-09 - 365-day Activity Heatmap | [Product V12] | высокая |
| [#834](https://github.com/MikeMoore1337/your-fitness-coach/issues/834) | V12-08 - Hevy / Strong / FitNotes Workout History Import | [Product V12] | высокая |
| [#833](https://github.com/MikeMoore1337/your-fitness-coach/issues/833) | V12-07 - Workout History Import Foundation | [Product V12] | высокая |
| [#832](https://github.com/MikeMoore1337/your-fitness-coach/issues/832) | V12-06 - Unilateral / Per-side Set Semantics | [Product V12] | высокая |
| [#831](https://github.com/MikeMoore1337/your-fitness-coach/issues/831) | V12-05 - Licensed Exercise Catalog Expansion | [Product V12] | высокая |
| [#830](https://github.com/MikeMoore1337/your-fitness-coach/issues/830) | V12-04 - Licensed Exercise Catalog Inventory & Gap Analysis | [Product V12] | высокая |
| [#828](https://github.com/MikeMoore1337/your-fitness-coach/issues/828) | V12-03 - Copy Completed Workout as Text | [Product V12] | высокая |
| [#827](https://github.com/MikeMoore1337/your-fitness-coach/issues/827) | V12-02 - Factual Muscle Map | [Product V12] | высокая |
| [#826](https://github.com/MikeMoore1337/your-fitness-coach/issues/826) | V12-01 - Current-set-first Active Workout | [Product V12] | высокая |
| [#825](https://github.com/MikeMoore1337/your-fitness-coach/issues/825) | Product v12 - Training Experience & Exercise Intelligence | [Product V12] | высокая |
| [#824](https://github.com/MikeMoore1337/your-fitness-coach/issues/824) | V11-09 - Final acceptance and continuous engineering guard | [Product V11] | высокая |
| [#823](https://github.com/MikeMoore1337/your-fitness-coach/issues/823) | V11-08 - Repository cleanup and final product polish | [Product V11] | высокая |
| [#822](https://github.com/MikeMoore1337/your-fitness-coach/issues/822) | V11-07 - Observability and production performance evidence | [Product V11] | высокая |
| [#821](https://github.com/MikeMoore1337/your-fitness-coach/issues/821) | V11-06 - CI efficiency, determinism and regression truth | [Product V11] | высокая |
| [#820](https://github.com/MikeMoore1337/your-fitness-coach/issues/820) | V11-05 - Data integrity, concurrency and recovery hardening | [Product V11] | высокая |
| [#819](https://github.com/MikeMoore1337/your-fitness-coach/issues/819) | V11-04 - Test quality, coverage and regression truth | [Product V11] | высокая |
| [#818](https://github.com/MikeMoore1337/your-fitness-coach/issues/818) | V11-03 - Frontend, Web, Mobile and TMA performance | [Product V11] | высокая |
| [#817](https://github.com/MikeMoore1337/your-fitness-coach/issues/817) | V11-02 - Backend/API and PostgreSQL performance | [Product V11] | высокая |
| [#816](https://github.com/MikeMoore1337/your-fitness-coach/issues/816) | V11-01 - Code health and targeted refactoring | [Product V11] | высокая |
| [#815](https://github.com/MikeMoore1337/your-fitness-coach/issues/815) | V11-00 - Factual baseline, profiling and measurable budgets | [Product V11] | высокая |
| [#814](https://github.com/MikeMoore1337/your-fitness-coach/issues/814) | Product v11 - Engineering Excellence & Product Polish | [Product V11] | высокая |
| [#324](https://github.com/MikeMoore1337/your-fitness-coach/issues/324) | [Roadmap] SEO & Organic Growth: Wave 1 completion → evidence → product-led conversion → Hermes → scalable catalog | [Growth] | высокая |
| [#323](https://github.com/MikeMoore1337/your-fitness-coach/issues/323) | [Task 290 / SEO Growth Stage 5] Scalable organic catalog: Wave 2 expansion, Food SEO quality gates and authority assets | [Growth] | высокая |
| [#322](https://github.com/MikeMoore1337/your-fitness-coach/issues/322) | [Task 289 / SEO Growth Stage 4] Hermes Growth Operator: evidence-driven opportunity pipeline and content distribution | [Growth] | высокая |
| [#321](https://github.com/MikeMoore1337/your-fitness-coach/issues/321) | [Task 288 / SEO Growth Stage 3] Product-led SEO conversion and referral loops | [Growth] | высокая |
| [#320](https://github.com/MikeMoore1337/your-fitness-coach/issues/320) | [Task 287 / SEO Growth Stage 2] Evidence-based SEO observation, optimization and Wave 2 decision | [Growth] | высокая |

## Открытые PR, которые нужно сохранить

- [#958](https://github.com/MikeMoore1337/your-fitness-coach/pull/958) - fix(ui): stabilize mobile food picker #946-#948
- [#944](https://github.com/MikeMoore1337/your-fitness-coach/pull/944) - fix(landing): implement cinematic Hero variant B (#906)
- [#941](https://github.com/MikeMoore1337/your-fitness-coach/pull/941) - docs: publish final issues acceptance matrix and evidence index
- [#939](https://github.com/MikeMoore1337/your-fitness-coach/pull/939) - fix(demo): restore trainer inbox and exercise history transport (#904 #905)
- [#936](https://github.com/MikeMoore1337/your-fitness-coach/pull/936) - fix(landing): remove square weekly score borders (#903)
- [#927](https://github.com/MikeMoore1337/your-fitness-coach/pull/927) - fix(ui): safe rest timer #914 integrated with approved #915
- [#915](https://github.com/MikeMoore1337/your-fitness-coach/pull/915) - feat(ui): approved Rhythm YFC mobile package #859
- [#911](https://github.com/MikeMoore1337/your-fitness-coach/pull/911) - fix(notifications): guard past calendar reminder dates (#871)
- [#910](https://github.com/MikeMoore1337/your-fitness-coach/pull/910) - fix(profile): show full selected goal on mobile (#870)
- [#909](https://github.com/MikeMoore1337/your-fitness-coach/pull/909) - [Mobile #869] Preserve full water preset labels at narrow widths
- [#908](https://github.com/MikeMoore1337/your-fitness-coach/pull/908) - [Mobile #868] Open quick water controls once without resetting drafts
- [#907](https://github.com/MikeMoore1337/your-fitness-coach/pull/907) - [Mobile #860] Reveal exercise replacement feedback and preview

## Следующая проверка

Перед массовой записью: сравнить с живыми GitHub данными, прочитать описание каждой Issue, проверить связи и связанные PR, получить согласование таблицы и только затем изменять метаданные небольшими группами с повторным чтением.
