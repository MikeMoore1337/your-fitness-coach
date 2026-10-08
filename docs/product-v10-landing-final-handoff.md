# Product v10 — B × C × Current YFC — final implementation handoff

Дата: 08.10.2026, Europe/Moscow. **Owner design approval: PASS.** Этот документ
фиксирует approved design contract и staged implementation map; public cutover остаётся
отдельным gate #858.

## Начать здесь

1. Versioned visual references находятся в [`docs/design/references/product-v10-landing/`](design/references/product-v10-landing/): compact athlete teaser (desktop/mobile × dark/light), preserved Coach Today (desktop/mobile × dark/light) и glass-header close-ups.
2. Интерактивная gallery, motion preview и full-page snapshots остаются локальным review evidence в ignored `.artifacts`; они не являются production runtime и не входят в versioned PRs.
3. `HANDOFF.md` из sandbox был сверён с approved состоянием и перенесён сюда как durable section map, CTA/route matrix, component reuse map, ограничения claims и verification record.

Исходники sandbox находятся уровнем выше: `design.tsx`, `refinement.css`, `build.cjs`, `audit-current.cjs`, `verify.cjs`, `motion.cjs`. Bundle и assets внутри deliverables можно просматривать без React dev-server и без API. Для пересборки используется уже установленный esbuild из `frontend/node_modules`. Новых зависимостей нет.

Запуск из корня репозитория:

```powershell
node .artifacts/tasks/landing-v10-refinement/build.cjs
node .artifacts/tasks/landing-v10-refinement/verify.cjs
```

Сервер запускается **из deliverables**, а не из корня репозитория:

```powershell
D:/Pet-projects/your-fitness-coach/.venv/Scripts/python.exe -m http.server 8789 --bind 127.0.0.1
```

## 1. Что утверждено и что ещё нет

Owner выбрал сочетание B (кинематографичная спортивная подача), C (продуктовый цикл и полноценный Coach OS) и Current YFC (существующая идентичность). Финальная визуальная итерация утверждена; отдельная owner authorization на implementation дана после завершения design gate.

Это один финальный вариант. Дополнительные hero-концепции не создавались: сохранение узнаваемого «Сила в действии» оказалось сильнее новой словесной идентичности. Для тренера предложено «Ваш метод в действии» в той же композиционной грамматике.

В staged implementation PR production routes, API, модели, Demo service и SEO-файлы не
изменяются. Новые athlete и trainer композиции используют существующие production components и
локальные synthetic preview states; browser verification проверяет отсутствие API-вызовов при
рендере.

### Durable handoff contract

- `LANDING_FINAL_DESIGN_OWNER_APPROVAL=PASS` зафиксирован в Issue #852.
- `LANDING_HANDOFF_PERSISTED=PASS` означает этот versioned документ и выбранные visual references; ignored gallery не является единственным источником.
- `LANDING_IMPLEMENTATION=ATHLETE_COACH_STAGED` после C4: production public cutover остаётся отдельным gate #858.
- `CONTROLLER=ABSENT`: не добавлять controller, leases, lifecycle state machine, delivery owner, очередь или recovery orchestration.

## 2. Источники и визуальный аудит production

Основной контракт возможностей: `docs/product-v10-landing-read-only-proposal.md`, прочитанный на предыдущем этапе, и текущий source. Проверенный локальный HEAD: `bd8f2bdd33341f1a8e7cd8e6b2384c38d67d307f`. Production осмотрен отдельно по публичному URL `https://your-fitness-coach.ru/`, без входа и без запуска изменяющих demo-действий.

Источник live-снимков: `current/`. `current/audit.json` содержит URL, заголовок, текущие demo href, порядок секций, computed button values, размеры и page errors. Chromium desktop 1440×1000 и mobile 390×844; обе темы. В этих четырёх состояниях horizontal overflow и JS page errors не обнаружены. Это не полный аудит accessibility, не provenance соответствия runtime конкретному SHA и не field performance.

Визуально подтверждены:

- наклонный Oswald и лаймовая вторая строка «Сила в действии»;
- существующая силовая фотография и явная спортивная энергия;
- кнопка: `rgb(178,245,32)` = `#b2f520`, radius `14px`, border `1px`, min-height `48px`, Inter;
- стеклянная вторичная кнопка с фирменной обводкой;
- StrengthScene с двумя положениями гантели и явным пояснением ручной записи;
- подготовленная демонстрация прогресса с 6 220 кг, 11 тренировками и индексом 100 → 104,2%; это синтетические данные, не efficacy claim;
- полноценная работа темы, desktop navigation и mobile menu;
- trainer block находится после workout/nutrition/progress, поэтому тренерский рассказ начинается поздно.

**Что уже хорошо:** выразительная идентичность, реальные продуктовые объяснения, demo boundary, Web/TMA и честные ограничения графика. Это сохранено.

**Что улучшаем:** общий hero-copy слишком широк для ответа «почему YFC»; доказательство тренерской ценности ограничивается фотографией и текстом; связка питания, плана и покупок не показана; программа сначала скрыта за входной фотографией демо. Выводы качественные, не основаны на измеренной конверсии.

## 3. Полная карта решений по текущему Landing

| Текущее решение | Решение | Сохраняется | Изменение и польза |
|---|---|---|---|
| Hero спортсмена | EVOLVE | Фото, «Сила в действии», наклон, лайм, общий характер | Выбор аудитории, ясный цикл и подзаголовок; посетитель понимает следующий шаг |
| Фотографические сцены | KEEP_AS_IS / REPOSITION | Только существующие marketing assets | Trainer photo становится hero тренера; nutrition photo сохраняет эмоциональную главу |
| StrengthScene | KEEP_AS_IS | Исходный компонент, CSS, пары фото, easing, 2→3, disclosure | Только на странице спортсмена; у тренера не дублируется |
| Scroll-bound механика | KEEP_AS_IS | Исходные passive listeners, rAF, interpolation, reduced motion | Не заменена новым видео/параллаксом; нет нового scroll-jacking |
| Входная фотография LandingPractice | REPLACE_WITH_JUSTIFICATION (только entry presentation) | Сам интерактивный тренировочный сценарий | В sandbox программа видна сразу. Преимущество: понятен предмет действия до клика; runtime lazy/demo boundaries в будущем сохранить |
| Интерактивная тренировка | EVOLVE | Реальный TrainingScenario и его UI | В sandbox получает local fixture; будущий production должен переиспользовать существующий Demo API, не этот локальный reducer |
| Питание | EVOLVE | Фото, тема, шрифты, controls | Три понятных состояния: план, покупки, дневник; факт не возникает сам |
| Прогресс | KEEP_AS_IS / EVOLVE | Реальный LandingProgressContent, TimeSeriesChart, числа, индекс, disclosure | Рядом вопрос недельной проверки; отдельная synthetic иллюстрация, не приватная authenticated view |
| Тренерский блок | EVOLVE + REPOSITION | Coach OS facts и фирменная фотография | В режиме тренера — отдельные шесть глав, без повторения athlete narrative |
| Athlete Coach OS teaser | REPLACE_WITH_COMPACT_PROMO | Связь со страницей тренера и реальные Coach OS возможности | После athlete-прогресса, перед объяснением различий и Demo; без фотографии, без auth/DemoCabinet; CTA переключает audience на coach |
| Шаблоны подключения | EVOLVE | Версия плана и отдельные действия invite/программа/check-in | Назначение шаблона подключения не назначает программу автоматически |
| Web/TMA continuity | KEEP_AS_IS / REPOSITION | Один аккаунт, общие основные данные | После демо-сценариев; краткое упоминание также в hero |
| Переходы к демо | EVOLVE (presentation only) | Существующие scenario entry points | Selected audience задаёт первый сценарий; backend и Demo engine не изменять |
| Athlete Coach OS teaser | REPLACE_WITH_COMPACT_PROMO | Existing coach capabilities: clients, program versions, reviews, confirmed next step | Один компактный promotional block после athlete proof; повтор в coach path отсутствует |
| Навигация | EVOLVE | PublicShell, Продукт/Демо/Вопросы, theme, login/menu | Добавлен audience choice в hero. Menu Escape/focus, anchors остаются |
| CTA | EVOLVE | Геометрия, токены, hover/pressed/focus, Glass | Owner mandate: primary свои данные; secondary настоящий demo; отдельный anchor локального примера |
| Theme toggle | KEEP_AS_IS | Реальный AppThemeToggle/useWebTheme | В галерее есть принудительные темы для проверки; production default не меняется |
| FAQ / прозрачность | EVOLVE | Данные, demo isolation, человеческое решение | Добавлены явные границы ручных сообщений и роли независимого тренера |
| Footer | EVOLVE | BrandLockup, продуктовые/служебные ссылки | Явная роль YFC; реальные legal URL необходимо согласовать |
| Избранные статьи | REPOSITION | Существующая публичная content surface | Не включены в основной proof-path макета. В реализации сохранить вторичный вход к знаниям/статьям в footer, не удалять routes или SEO |
| Прозрачная полоса всей шапки | KEEP_AS_IS | Исходные PublicShell + landing.css, blur, границы, тема, mobile и scroll | Непрозрачный sandbox override удалён. Desktop: фон 28%, blur 12px; mobile: 22%, blur 8px. Glass не распространяется на обычные секции |

## 4. Финальное повествование

### Для себя

Hero с текущей силовой сценой → четыре шага цикла → оригинальная StrengthScene → интерактивная тренировка → питание (план/покупки/дневник) → прогресс и проверка недели → компактный Coach OS teaser → локальный интерактивный Coach OS пример → отличие связанного контекста → три demo-сценария → Web/TMA → FAQ → CTA → footer.

В hero: «Сила в действии». Подзаголовок: «Тренируйтесь по плану. Сопоставляйте питание, результаты и самочувствие — чтобы выбрать следующий шаг». Primary: «Начать со своими данными». Secondary: «Попробовать демо тренировки». Компактная tertiary-кнопка: «Посмотреть пример тренировки». После прогресса один promotional teaser: «Вы тренер? Знакомьтесь с Coach OS.» с CTA «Возможности для тренера», который меняет audience на тренерскую версию лендинга.

### Для тренера

Hero с текущим trainer photo → цикл → сохранённый Coach Today / «Не потерять важное» (#coach-work) → подключение клиента (#coach-connect) → назначение программы (#coach-program) → Client 360 / факты (#coach-facts) → Check-in / Review Workspace (#coach-review) → preview/confirm применения версии к нескольким клиентам (#coach-decision) → черновик/подтверждение сообщения (#coach-followup) → адаптированное отличие → только trainer Demo CTA → Web/TMA → тренерские FAQ → CTA → footer. Athlete-only секций в этом DOM нет.

В hero: «Ваш метод в действии». Подзаголовок: «Программы, проверки и история клиента — в одном рабочем пространстве. Видеть важное. Выбирать следующий шаг». Primary: «Начать как тренер». Secondary: «Попробовать демо для тренера». Компактная tertiary-кнопка: «Как работает Coach OS».

Переключение меняет не роль аккаунта, а публичный рассказ: hero/photo, список выгод, порядок секций, primary CTA, первый демо-сценарий. В sandbox параметр `audience` сохраняет выбор, Back восстанавливает его, `theme` сохраняет тему. Production route/canonical decision здесь не реализован.

Coach OS — не отдельная корпоративная CRM. Те же шрифты, кнопки и спортивная фотография; без KPI-плиток бизнеса, командных ролей, биллинга и обещаний auto-send. Тренер — независимый пользователь, YFC не сторона договора тренер–клиент.

## 5. Что реально переиспользовано в sandbox

| Компонент/ресурс | Как использован | Boundary для будущей реализации |
|---|---|---|
| `shared/ui/PublicShell.tsx` | Прямой import | Сохранить текущий shell, не делать второе Landing SPA |
| `BrandLogo.tsx` / BrandLockup | Прямой import, theme-aware assets | Не перерисовывать знак/wordmark |
| `Icon.tsx` / iconGlyphs | Прямой import | Существующий каталог уже содержит glyphs с upstream provenance (включая Lucide); это не новая замена иконографии. Новые icon packs не добавлены |
| `Glass.tsx`, `GlassInteractions.tsx`, `liquid-glass.css` | Прямые imports | `glassProps` только у ссылок/кнопок переключения и secondary actions. Обычные product panels непрозрачные |
| `AppThemeToggle`, `useWebTheme` | Через PublicShell; прямой theme hook | Текущий механизм тем; локальный storage только origin sandbox |
| `StrengthScene.tsx` / CSS | Прямой import без правок | Весь current mechanism оставить; изменение длительности не принято |
| `LandingChapter` | Прямой import | Сохранять semantic reveal/reduced-motion behavior |
| `TrainingScenario` | Прямой import + local fixture | Это synthetic preview; не переносить sandbox reducer вместо Demo API |
| `LandingProgressContent` / `TimeSeriesChart` | Прямой import | Две сводные точки и индекс должны остаться честно подписанными |
| `LandingPractice` | Изучен; прямой import не использован из-за API action | В implementation предпочтительно адаптировать existing entry, сохранив lazy-load и query boundary |
| CoachToday / CoachReviewWorkspace / rollout / workflow templates | Изучены, сцена воспроизведена на synthetic данных | Не монтировать авторизованный компонент с настоящим clientId на публичной странице |
| `WeeklyCheckInCard` | Изучены facts/questions/adjustment, recovery question и шкала 1–5 | Публичный образец не пишет check-in и не раскрывает данные аккаунта |
| `fonts.css`, `design-system.css`, `landing.css`, `public-shell.css` | Прямые imports | Новые sandbox rules описывают композицию, а не замену токенов |
| `marketing/*.webp`, `brand/*`, fonts | Копия текущих repo assets в изолированный output | Новых внешних фото/генераций/шрифтов нет |

### Токены и визуальные инварианты

- Lime: `--v2-lime` / `--landing-green`, текущий `#b2f520`.
- Dark paper: `#090b0b`; light paper: текущие `#fff`/shell theme values. Новая палитра не введена.
- Type: `--font-display` Oswald, `--font-sans` Inter. Hero сохраняет italic; размеры и переносы адаптированы к новому switch и subhead.
- Controls: `--radius-control` 14 px, min-height 48 px у Landing action и 44 px у компактных controls, 1 px border. Основная кнопка остаётся лаймовой, secondary — текущий glass.
- Panels: `--radius-panel` 24 px, `--landing-line`, непрозрачный paper.
- Motion: текущие `--motion-state` 180 ms и `--motion-ease`; pressed без transform согласно override Design V2. Focus остаётся явным.

## 6. Motion specification и доказательства

`motion-preview.webm` — запись настоящего local Chromium render 1280×800, normal motion. `motion-manifest.json` содержит последовательность.

1. Athlete hero: краткое вступление текста. Доступ к CTA не ждёт завершения.
2. Audience switch: текст 260 ms (opacity .6→1, translateY 8→0); фотография 420 ms (.4→.7). Повторный выбор доступен немедленно; effect cleanup отменяет предыдущую animation.
3. StrengthScene: исходная scroll-driven интерполяция и фазы 0/1/2; сохранено пояснение, что запись выполняет человек. Никакого распознавания движения.
4. Product state: 180 ms короткое появление панели. Значение/состояние меняется по действию сразу, а не после таймера.
5. Chapter reveal и Glass pointer response — существующие компоненты, без новых motion dependencies.

Reduced motion: выключены hero/panel movement, плавная прокрутка; original StrengthScene показывает завершённое состояние без длинного sticky. Все controls и текст сохраняются. Визуальная смена audience/photo без motion остаётся мгновенной.

**Не реализовано заранее:** autoplay video hero, full-page parallax, новый timeline/scroll owner, бесконечные фоновые эффекты. Они не нужны для утверждённого направления.

## 7. Mobile и состояния

- 320/360/390/430: switch в отдельной строке hero, CTA вертикально, ясный следующий шаг до глубоких разделов; фотографии имеют отдельный crop.
- 768: промежуточная композиция проверена, таблицы/controls не вылезают за viewport.
- 1280/1440: двухколоночные proof-сцены и крупные фотоглавы; Coach OS не превращается в корпоративную панель.
- Cycle — 2×2 на mobile; смысловые продуктовые панели — одна колонка; без горизонтальных каруселей.
- Mobile navigation: открыть/закрыть, Escape возвращает focus кнопке; theme/switch доступны клавиатуре.
- CTA: default, hover, pressed, focus; «свои данные» открывает существующий /app в новой вкладке. Legal boundary-dialog остаётся локальным. Диалог закрывается Escape.
- Workout: today → active → completed sets → summary; реальный TrainingScenario, local-only state.
- Nutrition: план не создаёт факт; дневник меняется только после явного действия.
- Weekly review: раскрытие вопроса и выбор восстановления 1–5; ответ остаётся в memory sandbox.
- Coach: факты → изменения → предварительный просмотр → подтверждение; отдельно draft edit → confirmation. Реальной отправки нет.

## 8. Проверенные возможности и запреты claims

Опоры текущего source: `CoachToday.tsx`, `CoachReviewWorkspace.tsx`, `CoachWorkflowTemplates.tsx`, `services/coach_program_rollout.py` (preview/confirmed), `services/coach_workflow_templates.py` (confirm draft), `services/nutrition_plan.py` (planned/consumed), `GroceryList.tsx`, `WeeklyCheckInCard.tsx`, existing Landing/demo source.

Для посетителя показаны программа/подходы, питание, планирование/покупки, динамика и проверка недели. Для тренера — клиент, назначение, review, безопасное подтверждение, onboarding templates и сообщение с подтверждением. Изоляция private notes сохранена: в публичной сцене их нет.

AI Coach, часы, видеоанализ, Multi-Coach runtime, marketplace, team roles, payment processing не заявлены. Ни отзывов, ни счётчиков клиентов, ни гарантии результата/абсолютной безопасности. Сравнение «запись/контекст» не утверждает отсутствие аналогичных функций у всех конкурентов.

## 9. Проверки и ограничения

`verification.json`: 28 сочетаний (2 аудитории × 2 темы × 7 ширин). Проверены горизонтальный overflow, clipping видимого текста, состояния темы, локальные interactions, меню, FAQ, dialog, audience keyboard navigation и Back. Намеренно визуально скрытое `.sr-only` описание графика исключено из detector clipping, но не удалено из DOM.

Full-page snapshots: 8. Предметные proposed comparison crops: 5. Current evidence: 4 hero theme/device состояния + training/progress/trainer/CTA + StrengthScene. Дополнительно: `coach-promo-dark-1440.png`, `coach-promo-dark-390.png`, `coach-promo-light-1440.png`, `coach-promo-light-390.png`. Это целевые материалы, а не десятки почти одинаковых hero.

Нет API/external requests из prototype при проверенных действиях. CSP — дополнительная техническая граница. Production baseline собран анонимно, без credentials. Конверсия и field CWV не измерялись; physical-device, Safari, real Telegram, screen-reader полноценный аудит не выполнены. Browser viewport evidence не равно physical-device proof.

Sandbox bundle включает текущие styles/component dependencies ради точного reuse и не является оптимизированным production payload. Не копировать весь bundle/legacy CSS в новый production entry. Будущая задача должна сохранить существующие lazy boundaries и измерить runtime bundle/LCP/CLS на актуальном build.

## 10. Минимальный будущий implementation scope — только после отдельного owner prompt

1. Сверить current protected master, Issue/spec и окончательное визуальное решение. Не использовать этот HEAD как freeze/redeploy target.
2. В существующем LandingPage ввести публичный audience context, hero copy/photo, порядок уже существующих sections и demo entry. Не менять auth role.
3. Переиспользовать PublicShell, текущие buttons/icons/glass/theme, StrengthScene и existing demos. Не переносить sandbox app как второй production SPA.
4. Адаптировать LandingPractice entry; сохранить query error/retry, isolation, lazy loading и analytics distinction synthetic/real.
5. Добавить минимальные synthetic proof-scenes для планирования/покупок и Coach OS только в согласованном объёме. Не импортировать authenticated queries/private notes в public surface.
6. Связать weekly review proof с фактическим контрактом. Не вводить автоматические медицинские/тренировочные рекомендации.
7. Проверить публичную навигацию `/` и `/for-trainers`, Back/forward, UTM, canonical/fallback. Не вводить `/coach-demo` или `/for-athletes` без отдельного решения. Существующие demo href из live audit сохранить совместимыми.
8. Обновить allowlisted audience/CTA measurement на существующих событиях, без персональных/health данных и без нового провайдера.
9. Проверить доступность, обе темы, reduced-motion, failure/no-JS/fallback, реальный demo contract, SEO regression и performance. Подготовить bounded visual evidence, затем применимые Checks и GitHub Flow — только в рамках будущей авторизации.

Вероятные production files для будущего diff: `pages/landing/LandingPage.tsx`, `landing.css`, при необходимости `LandingPractice.tsx`; минимальный новый public proof component. Shared tokens/Icon/BrandLogo/Glass/StrengthScene менять не требуется. Routes/metadata/demo runtime — только если конкретное утверждённое решение действительно этого требует.

## 11. Оставшиеся owner design decisions

1. Утвердить единую композицию: athlete «Сила в действии», coach «Ваш метод в действии», общий переключатель и разный порядок сцен.
2. Проверить финальную композицию обязательной owner CTA-иерархии: свои данные → настоящий demo → локальный пример. Сам приоритет уже зафиксирован владельцем, не является открытым вариантом.
3. Утвердить финальную подачу сохранённых встроенных synthetic planning/coach states рядом с отдельным existing demo entry. Текущий trainer demo подтверждает client/workout/comment; нельзя объявлять всю предложенную v10 sequence уже доступной в текущем demo.
4. Утвердить default audience «Для себя» и использование существующей системной темы. Gallery defaults — инструмент review, не новое продуктовое правило.
5. Утвердить обращение на «вы» в новом copy; исходный StrengthScene содержит «ты» и намеренно не переписан. Если нужна полная унификация, это небольшой отдельный copy diff будущей задачи.
6. Согласовать actual legal URLs и вторичный вход к статьям/базе знаний в footer. Ни legal content, ни public SEO routes не удалять ради макета.

После выбора нужен **отдельный явный prompt на implementation**. Одобрение направления не является разрешением продолжить автоматически.

## 12. Исправления #852 и точные переходы

| Элемент | Текст кнопки | Ожидаемое действие | Destination | Реальный продуктовый маршрут |
|---|---|---|---|---|
| Hero + финал / спортсмен | Начать со своими данными | Открыть существующий вход/старт | app | /app |
| Hero + финал / тренер | Начать как тренер | Авторизация → server capability check → явное согласие при необходимости → Coach Today без Профиля | trainer intent | /app?trainer_intent=1 |
| Hero + финал / спортсмен | Попробовать демо тренировки | Настоящий изолированный демо-кабинет | demo/self_training | /demo?cabinet=1&scenario=self_training&section=today |
| Hero + финал / тренер | Попробовать демо для тренера | Настоящий тренерский демо-кабинет | demo/trainer | /demo?cabinet=1&scenario=trainer&section=trainer |
| Hero / спортсмен | Посмотреть пример тренировки | Прокрутить локальный пример | landing/#training | /#training |
| Hero / тренер | Как работает Coach OS | Прокрутить локальный пример | landing/#coach-work | /#coach-work |
| Меню / спортсмен | Демо | Настоящий демо-кабинет спортсмена | demo/self_training | /demo?cabinet=1&scenario=self_training&section=today |
| Меню / тренер | Демо | Настоящий демо-кабинет тренера | demo/trainer | /demo?cabinet=1&scenario=trainer&section=trainer |
| Меню | Войти | Существующая авторизация | login | /login |
| Сценарии демо | Попробовать демо тренировки | Настоящий демо-кабинет | demo/self_training | /demo?cabinet=1&scenario=self_training&section=today |
| Сценарии демо | Попробовать демо питания | Настоящий демо-кабинет питания | demo/nutrition | /demo?cabinet=1&scenario=nutrition&section=nutrition |
| Сценарии демо | Попробовать демо для тренера | Настоящий демо-кабинет тренера | demo/trainer | /demo?cabinet=1&scenario=trainer&section=trainer |
| Прогресс | Попробовать демо прогресса / Открыть прогресс | Открыть раздел прогресса существующего демо | demo/progress | /demo?cabinet=1&scenario=self_training&section=progress |

Маршруты /app, /login и /demo разрешаются через `appUrlForHostname`, `loginUrlForHostname`, `demoUrlForHostname`. Для public hostname это `https://app.your-fitness-coach.ru`. Anchor-пути остаются на Landing. В sandbox используются production-host links; при реализации не переносить фиксированный hostname, использовать текущий hostname.

`cabinetScenarioUrl` в `frontend/src/pages/landing/LandingPage.tsx` (локальная функция) задаёт today/nutrition/trainer. Sandbox только повторяет href-контракт; не создаёт сессию. Будущая реализация переиспользует эту функцию, `frontend/src/pages/demo/DemoCabinet.tsx`, `frontend/src/features/demo/demoRoute.ts` и действующий session loader. Запрещён второй demo engine.

`PublicContentPage.tsx` и staged trainer CTA используют bounded `/app?trainer_intent=1`. После
авторизации существующий тренер попадает в Coach Today; новый тренер видит существующее
согласие с условиями и явное подтверждение, затем существующую server-authoritative активацию
и Coach Today / первое приглашение без поиска в Профиле. Отказ сохраняет личный аккаунт. Один
маркетинговый клик, hash или произвольный query-параметр не активирует capability; Telegram
transport-параметры разрешены только в signed launch. Сохранение intent, auth callbacks,
согласие и активация реализованы в #875 без нового endpoint или второго Coach OS компонента.

Проверка маршрутов — инспекция href и исходников, без входа в аккаунт или создания production demo-сессий. `route-matrix.json` содержит машинно-читаемую таблицу; `cta-verification.json` — проверенные href и клики по локальным anchors. `header-verification.json` — текущий production и prototype, desktop/mobile, темы, аудитории, scroll и отключённый backdrop-filter. Versioned close-ups шапки: [`header-comparison-1440.png`](design/references/product-v10-landing/header-comparison-1440.png), [`header-comparison-390.png`](design/references/product-v10-landing/header-comparison-390.png).

StrengthScene импортируется без изменений только для спортсмена; тёмные контекстные секции переходят в исходную белую сцену. Normal-motion sticky-дистанция остаётся исходной; reduced-motion не добавляет пустой экран.

#852 закрыт после merge docs-only PR. #853–#858 и #875 остаются отдельными bounded
implementation tasks с указанными зависимостями. Рабочая галерея и её zip-пакет находятся в
ignored/local evidence; GitHub остаётся источником versioned contract.

## 13. Финальная доработка: tertiary и отдельный тренерский рассказ

| Решение | KEEP / REPLACE / SHARED | Итог |
|---|---|---|
| Athlete cinematic path | KEEP | StrengthScene, TrainingScenario, питание/покупки, прогресс/неделя сохранены |
| Принятые glass header и demo semantics | KEEP | Те же PublicShell, tokens и маршруты |
| Маленькие текстовые preview links | REPLACE | Tertiary outline 14px radius, 44px min-height, 12px Inter 600, компактная ширина по тексту; контекст «Интерактивный пример» |
| Дублирование athlete-секций у тренера | REPLACE | Шесть самостоятельных глав о работе тренера |
| Brand, SectionTitle, LandingChapter, buttons, theme, motion | SHARED | Одни primitives, не две независимые реализации |
| Отличие, Web/TMA, Demo, FAQ, footer | SHARED | Общая композиция; trainer copy, anchors, FAQ и trainer-only demo entry |

Tertiary остаётся семантической ссылкой для якоря. Оба варианта используют один класс. Hover меняет подложку/обводку; focus-visible лаймовый, pressed усиливает тёмную подложку и лаймовую границу. Текущий Design V2 shell отменяет transform hover/active; этот инвариант сохранён. Enter переносит фокус на целевую секцию и прокручивает к ней с 24px отступом. Исходная glass-шапка не sticky и уходит при прокрутке; она не закрывает заголовок. Reduced motion выключает smooth-scroll. Компоненты доступны без мыши. Это всё sandbox, production не затронут.

### Источники тренерских сцен и ограничения

- Подключение и план: `frontend/src/features/coach/CoachWorkflowTemplates.tsx`. Версия плана подключения не выполняет автоматически отдельные шаги назначения программы и проверки.
- Назначения / версии / несколько клиентов: `CoachProgramOperations.tsx`, `CoachProgramBulkOperations.tsx`, `backend/fitminiapp_api/services/coach_program_rollout.py`. Выбор → preview по клиентам → явное подтверждение. В сцене смена выбора сбрасывает preview, пустой выбор блокирует действие. Применение показано к будущим тренировкам; история выполненного не переписывается. Backend errors/conflicts не симулируются как полноценный runtime.
- Coach Today / Inbox / Client 360: текущие CoachToday и обзор связанного клиента. Показаны только синтетические факты плана, выполнения и проверки, никаких приватных заметок.
- Проверки: `CoachReviewWorkspace.tsx`; выполненные/плановые тренировки, самооценка, честное отсутствие сопоставимых изменений, ручная отметка проверки. Никакого readiness-score или медицинской интерпретации.
- Сопровождение: `CoachWorkflowTemplates.tsx`; создание → редактирование → подтверждение черновика. В настоящем продукте создаётся внутреннее уведомление; локальная сцена ничего не отправляет.

Сцены независимые иллюстрации этапов, а не второй сквозной demo runtime. Принятие приглашения помечено как «показать»; тренер не принимает согласие от имени клиента. Все Alexey/Marina и числовые значения синтетические. Существующий DemoCabinet не объявляется полным отражением новых публичных сцен.

### Evidence

`proposed/hero-self-tertiary.png`, `proposed/hero-coach-tertiary.png`; `trainer-section-flow.png`; существующие восемь full-page снимков обновлены, включая coach mobile dark/light. `tertiary-states.png` показывает default/hover/focus/pressed; `tertiary-verification.json` проверяет pressed и keyboard desktop/mobile. `trainer-verification.json` фиксирует клавиатурный якорь, отсутствие athlete-секций, шесть interactions, invalidated preview, запрет пустого выбора и explicit message confirmation. Общая responsive matrix — 28 состояний. `motion-preview.webm` обновлён.

Финальное visual approval дано владельцем 08.10.2026. #875 — самостоятельная implementation-задача, не часть этого design handoff.

## 14. Финальная minor-доработка athlete Coach OS teaser

Публичная athlete-страница теперь содержит ровно один компактный teaser после `#progress` и перед `#difference`/`#demo`:

`Вы тренер? Знакомьтесь с Coach OS.`

Описание сообщает только существующие Coach OS возможности: подключение клиентов, версии программ, проверки и подтверждение следующего шага. Фотография убрана из этого перехода; ordinary panels не получили glass. `Возможности для тренера` использует текущую lime-кнопку и `?audience=coach`, поэтому не открывает `/login` и не создаёт DemoCabinet. В athlete-ветке полноценный Coach Today и остальные trainer-only scenes не монтируются. В coach-ветке teaser отсутствует, сохранён полноценный Coach Today / «Не потерять важное», а шесть утверждённых тренерских глав не изменены.

Карта секций после корректировки:

| Аудитория | Порядок |
|---|---|
| Для себя | Hero → цикл → StrengthScene → тренировка → питание → прогресс/недельный обзор → Coach OS teaser → локальный Coach OS пример → различие YFC → Demo → Web + TMA → FAQ → CTA → footer |
| Для тренера | Hero → цикл → Coach Today / «Не потерять важное» → подключение клиента → программа/версия → Client 360 / факты → Check-in / Review Workspace → preview/confirm применения → черновик/подтверждение сообщения → различие YFC → Demo → Web + TMA → FAQ → CTA → footer |

Versioned evidence: [`coach-promo-dark-1440.png`](design/references/product-v10-landing/coach-promo-dark-1440.png), [`coach-promo-dark-390.png`](design/references/product-v10-landing/coach-promo-dark-390.png), [`coach-promo-light-1440.png`](design/references/product-v10-landing/coach-promo-light-1440.png), [`coach-promo-light-390.png`](design/references/product-v10-landing/coach-promo-light-390.png), [`coach-today-dark-1440.png`](design/references/product-v10-landing/coach-today-dark-1440.png), [`coach-today-dark-390.png`](design/references/product-v10-landing/coach-today-dark-390.png), [`coach-today-light-1440.png`](design/references/product-v10-landing/coach-today-light-1440.png), [`coach-today-light-390.png`](design/references/product-v10-landing/coach-today-light-390.png). Ignored verification artifacts дополнительно фиксируют уникальный Coach Today в coach-ветке, отсутствие Coach Today и trainer-only scenes в athlete-ветке, URL hash-нормализацию и отсутствие overflow во всех четырёх состояниях.

Тренерская ветка после этого изменения не затронута. Production files, PR, merge, deploy, auth/API и новые routes не создавались.

## 15. Терминальное состояние

```text
LANDING_DESIGN_DIRECTION=B+C+CURRENT_YFC
CURRENT_YFC_VISUAL_IDENTITY=PRESERVED
LANDING_TOP_GLASS_HEADER=PRESERVED
LANDING_COACH_PROMO_ON_ATHLETE=COMPACT
LANDING_ATHLETE_TRAINER_ONLY_SECTIONS=HIDDEN
LANDING_DEMO_CTA_SEMANTICS=CORRECTED
LANDING_TERTIARY_CTA=REFINED
LANDING_TRAINER_FULL_JOURNEY=APPROVED
LANDING_TRAINER_COACH_TODAY=PRESERVED
LANDING_TRAINER_AUDIENCE_DIFFERENTIATION=PASS
LANDING_TRAINER_POST_AUTH_ACTIVATION=DEFERRED_TO_ISSUE_875
LANDING_INTERACTIVE_PREVIEWS=PRESERVED
LANDING_DESIGN_HANDOFF=UPDATED
LANDING_FINAL_DESIGN_OWNER_APPROVAL=PASS
LANDING_HANDOFF_PERSISTED=PASS
LANDING_IMPLEMENTATION=ATHLETE_COACH_STAGED
LANDING_PUBLIC_CUTOVER=NOT_STARTED
PRODUCT_V10_CONVEYOR=READY_FOR_C5
CONTROLLER=ABSENT
GITHUB_FLOW=AUTHORITATIVE
env change required: no
```

Этот документ и visual references остаются versioned source of truth для bounded implementation
PRs. Production public cutover, merge/deploy runtime, production configuration и новые delivery
processes этим staged PR не меняются. Git/GitHub остаётся operational source of truth.

## 16. C2 staged implementation map (#853)

Подготовительная архитектура переиспользует существующие primitives и не меняет текущие
публичные рендеры до финального cutover:

| Boundary | Staged source | Contract |
|---|---|---|
| Audience route context | `frontend/src/pages/landing/landingAudience.ts` | `athlete` = `/` (canonical) и `/for-athletes` (context alias); `coach` = `/for-trainers`; search/hash сохраняются при переключении |
| Accessible switch | `frontend/src/pages/landing/LandingAudienceSwitch.tsx` | обычные ссылки с `aria-current`, native browser history, русский label «Для себя / Для тренера» |
| Shared composition shell | `frontend/src/pages/landing/LandingV10Shell.tsx` | существующий `PublicShell`, `BrandLockup`, `AppThemeToggle`, existing login destination; audience content injected as children |
| Staged shell styles | `frontend/src/pages/landing/landing-v10.css` | geometry/focus/responsive rules for audience switch and staged composition; glass material остаётся у shared `PublicShell`/`Glass` |
| Proof | `frontend/tests/unit/pages/landing/LandingAudienceSwitch.test.tsx` | route mapping, canonical contract, UTM/hash preservation, ARIA state and shared-shell composition |

`/` и текущий `/for-trainers` намеренно продолжают рендерить существующие production pages;
новый shell не подключён в `AppRoutes`, не добавляет indexable route и не публикует
незаполненную страницу. #854 добавляет athlete scenes в этот composition, #855 — trainer
scenes, а #858 остаётся единственным public cutover/release gate. Никакой второй shell,
router, analytics store или controller не создаётся.

## 17. C3 athlete staged implementation map (#854)

Athlete composition собрана в staged shell и не подключена к текущему `/` до финального
cutover #858. Все previews синтетические и локальные; реальные пользовательские данные не
читаются и не записываются.

| Boundary | Staged source | Contract |
|---|---|---|
| Athlete composition | `frontend/src/pages/landing/LandingV10AthletePage.tsx` | hero → plan/action/facts/decision cycle → existing `StrengthScene` → existing `LandingPractice` → nutrition preview → progress/weekly review → one compact Coach OS teaser → Web/TMA continuity |
| Existing product proof | `StrengthScene.tsx`, `LandingPractice.tsx`, `LandingProgress.tsx` | current scroll-bound movement, isolated demo API boundary and prepared progress preview are reused without a second demo engine |
| Nutrition truth | `LandingV10AthletePage.tsx` | local tabs distinguish plan, purchases and diary; planned ≠ consumed; missing entry ≠ zero |
| Compact Coach OS teaser | `LandingV10AthletePage.tsx` | appears exactly once on athlete composition; CTA is `/for-trainers`, not auth or DemoCabinet; no Coach Today/trainer-only scene is rendered |
| Responsive/theme layer | `frontend/src/pages/landing/landing-v10.css` | desktop/mobile grids, compact teaser, focus states and dark/light-safe surfaces; shared tokens, buttons, icons and glass shell stay in use |
| Proof | `frontend/tests/unit/pages/landing/LandingV10AthletePage.test.tsx` | story landmarks, one teaser/no trainer scene, nutrition state, local weekly review, trainer href and no API call on render |

`AppRoutes` и текущие `/` и `/for-trainers` остаются без изменений. Это staged athlete и
trainer implementation для следующего bounded demo task #856; production replacement и SEO
indexation остаются deferred to #858.

```text
LANDING_DESIGN_DIRECTION=B+C+CURRENT_YFC
LANDING_ATHLETE_NARRATIVE=STAGED
LANDING_ATHLETE_COACH_PROMO=COMPACT_SINGLE
LANDING_ATHLETE_TRAINER_ONLY_SECTIONS=HIDDEN
LANDING_ATHLETE_DEMO_ENGINE=REUSED
LANDING_ATHLETE_RESPONSIVE=PASS
LANDING_IMPLEMENTATION=ATHLETE_STAGED
LANDING_PUBLIC_CUTOVER=NOT_STARTED
PRODUCT_V10_CONVEYOR=READY_FOR_C4
CONTROLLER=ABSENT
GITHUB_FLOW=AUTHORITATIVE
env change required: no
```

### C3 verification record

- `frontend/tests/unit/pages/landing/LandingV10AthletePage.test.tsx`: 4/4 passed; full frontend
  Vitest: 140 files, 772 tests passed.
- TypeScript build, ESLint and Russian UI guard, targeted Prettier and Vite production build passed.
- Local Chromium preview of the staged-only route passed four states: 390×844 and 1440×900,
  light and dark, with the Coach OS teaser present once, no Coach Today/trainer-only copy, and
  the trainer CTA pointing to `/for-trainers`.
- The local visual screenshots remain ignored review evidence under `.artifacts`; no production
  route or deployment was changed by #854.

## 18. C4 trainer staged implementation map (#855)

Тренерская композиция собрана в том же staged shell и не подключена к текущему
`/for-trainers` до финального cutover #858. В DOM тренерской ветки нет athlete-only
`StrengthScene`, интерактивной тренировки, питания или athlete-прогресса; все product scenes
ниже синтетические и локальные.

| Boundary | Staged source | Contract |
|---|---|---|
| Trainer composition | `frontend/src/pages/landing/LandingV10CoachPage.tsx` | hero «Ваш метод в действии» → рабочий цикл → Coach Today/«Не потерять важное» → подключение клиента → версия программы → Client 360 факты → обратная связь/проверка → решение, safe rollout и черновик сообщения → Web/TMA → coach CTA |
| Coach Today proof | `LandingV10CoachPage.tsx` | одна локальная сцена с вкладками «Факты / Изменения / Сообщение»; подтверждение и сообщение явно помечены как пример; API, реальные клиенты и private notes не читаются |
| Coach-native scenes | `LandingV10CoachPage.tsx` | onboarding клиента, версии программы, factual review, check-in and explicit trainer decision use synthetic Alexey/Marina data; no auto-send, payment gateway, multi-coach or AI decision claim |
| Safe rollout boundary | `LandingV10CoachPage.tsx` | выбор клиентов → локальный preview → explicit «Подтвердить в примере»; выполненная история не переписывается; draft confirmation is separate |
| Shared visual layer | `LandingV10Shell.tsx`, `LandingAudienceSwitch.tsx`, `landing-v10.css` | existing PublicShell, brand lockup, buttons, icons, tokens, glass header, theme and reduced-motion contracts are reused; no second landing shell or demo engine |
| Proof | `frontend/tests/unit/pages/landing/LandingV10CoachPage.test.tsx` | six chapter order, absence of athlete sections, local Coach Today/program/review/follow-up interactions, existing `/app` and trainer demo hrefs, no fetch on render |

Порядок шести coach-native глав: `coach-today → connect → program → facts → review →
decision`. `coach-decision` содержит два независимых локальных preview: safe rollout с явным
подтверждением и черновик сообщения с отдельным подтверждением. Это не сквозной demo runtime.

```text
LANDING_TRAINER_NARRATIVE=STAGED
LANDING_TRAINER_CHAPTERS=6
LANDING_TRAINER_ATHLETE_SECTIONS=ABSENT
LANDING_TRAINER_COACH_TODAY=LOCAL_PREVIEW
LANDING_TRAINER_SAFE_ROLLOUT=LOCAL_EXPLICIT_CONFIRM
LANDING_TRAINER_DEMO_ENGINE=DEFERRED_TO_C5
LANDING_TRAINER_RESPONSIVE=PASS
LANDING_IMPLEMENTATION=ATHLETE_COACH_STAGED
LANDING_PUBLIC_CUTOVER=NOT_STARTED
PRODUCT_V10_CONVEYOR=READY_FOR_C5
CONTROLLER=ABSENT
GITHUB_FLOW=AUTHORITATIVE
env change required: no
```

### C4 verification record

- `frontend/tests/unit/pages/landing/LandingV10CoachPage.test.tsx`: 4/4 passed; targeted
  TypeScript, Russian UI guard and Prettier passed.
- Local Chromium staged preview checked 390×844 and 1440×900 in Light/Dark. Hero, audience
  switch, six chapter order, coach-only scenes, light/dark panels, CTA contours and no-overflow
  mobile composition were inspected; existing `/` and `/for-trainers` were not rewired.
- Production implementation, demo session creation, authentication, private data access and
  deploy were not performed. The next bounded stage is #856 for the existing trainer demo path.

## 19. C5 trainer demo entry and evidence map (#856)

Trainer demo CTAs point to the existing isolated `DemoCabinet` route. The staged coach page and
the current public `/for-trainers` page use the same hostname-aware URL builder; no new public
route, session runtime, fixture engine or product screen is introduced.

| Boundary | Source | Contract |
|---|---|---|
| Trainer demo destination | `frontend/src/shared/navigation/appUrl.ts` | `demoCabinetUrlForHostname(hostname, 'trainer', 'trainer')` resolves to `/demo?cabinet=1&scenario=trainer&section=trainer` locally and the existing app subdomain on the public hostname |
| Staged coach CTA | `frontend/src/pages/landing/LandingV10CoachPage.tsx` | hero and final «Попробовать демо для тренера» links enter the real trainer demo contour, while the nearby «Как работает Коуч ОС» link remains an in-page preview anchor |
| Existing public entry | `frontend/src/content/publicContent.json`, `frontend/src/pages/public/PublicContentPage.tsx` | `/for-trainers` keeps one related card «Демо кабинета тренера» with the same trainer destination and demo click event |
| Demo runtime | `frontend/src/pages/demo/DemoCabinet.tsx`, `frontend/src/features/demo/demoApi.ts`, `frontend/src/features/demo/demoRoute.ts` | one existing synthetic trainer session, Coach Today → attention/client/workout/progress/operations/task/return route, current reset/exit/focus/history behavior |
| Boundary | `DemoCabinet` demo boundary and existing demo transport | «Демо-режим · данные не сохраняются» remains visible; invitations and real account writes are not available in the public session |
| Proof | `frontend/tests/unit/pages/landing/LandingV10CoachPage.test.tsx`, `frontend/tests/e2e/demo-mode.spec.ts` | both staged trainer CTAs and the public `/for-trainers` click-through are checked against the actual rendered demo cabinet, with mobile/desktop themes, back/forward and mutation boundary assertions |

Exact CTA → destination → browser state contract:

```text
/for-trainers → «Демо кабинета тренера»
  → /demo?cabinet=1&scenario=trainer&section=trainer
  → heading «Что требует действия?» + «Демо-режим · данные не сохраняются»
  → synthetic Coach Today; no direct real mutation request

staged coach hero/final CTA → /demo?cabinet=1&scenario=trainer&section=trainer
  → the same existing DemoCabinet state; «Как работает Коуч ОС» remains an in-page preview
```

```text
LANDING_TRAINER_DEMO_ENGINE=REUSED_EXISTING
LANDING_TRAINER_DEMO_ENTRY=PUBLIC_FOR_TRAINERS_AND_STAGED_COACH_CTA
LANDING_TRAINER_DEMO_BOUNDARY=NO_REAL_WRITES_OR_PRIVATE_DATA
LANDING_TRAINER_DEMO_RESPONSIVE=CHECKED
LANDING_TRAINER_DEMO_HISTORY=CHECKED
LANDING_IMPLEMENTATION=ATHLETE_COACH_DEMO_STAGED
LANDING_PUBLIC_CUTOVER=NOT_STARTED
PRODUCT_V10_CONVEYOR=READY_FOR_C6
CONTROLLER=ABSENT
GITHUB_FLOW=AUTHORITATIVE
env change required: no
```

### C5 verification record

- Full frontend Vitest passed: 141 files, 777 tests. The unit contract covers both staged coach
  demo CTAs and retains the in-page Coach OS preview anchor separately from the real demo
  destination.
- TypeScript, Vite production build, ESLint, Russian UI guard and targeted Prettier passed.
- The Playwright contract starts from `/for-trainers`, clicks the public trainer demo entry,
  asserts the rendered `DemoCabinet` screen and explicit no-save boundary, checks the disabled
  invite action, runs mobile/light and desktop/dark states, and returns through browser back and
  forward without leaving the isolated demo route.
- The existing trainer route remains the only demo runtime; no production route, backend API,
  account, private note, real invitation, notification or deploy is added by C5.

## 20. C6 public CTA, route and SEO preparation (#857)

C6 подготовил публичный контур без подключения staged V10 compositions к production Landing.
Текущие `/` и `/for-trainers` сохраняют действующие страницы до финального cutover #858.

| Boundary | Source | Contract |
|---|---|---|
| Athlete route | `frontend/src/main.tsx`, `backend/fitminiapp_api/main.py` | `/` остаётся canonical indexable athlete route; `/for-athletes` обслуживается как context alias с сохранением query/hash в браузере и без отдельной sitemap entry |
| Athlete alias SEO | `frontend/src/shared/seo/metadata.ts`, `backend/fitminiapp_api/seo.py` | alias отдаёт `noindex, follow`, canonical `https://your-fitness-coach.ru/`, root public fallback и не создаёт structured-data duplicate |
| Host boundary | `backend/fitminiapp_api/middleware/canonical_host.py` | application host redirects `/for-athletes` на public host, query сохраняется; `/app`, `/login`, `/coach`, `/admin`, API и demo boundaries не ослаблены |
| Demo CTA semantics | `frontend/src/pages/landing/LandingPage.tsx`, `frontend/src/shared/navigation/appUrl.ts` | real `DemoCabinet` links use the shared hostname-aware `demoCabinetUrlForHostname`; in-page navigation is explicitly labelled `Сценарии демо` and does not emit demo success |
| Own-data and trainer CTA | current `LandingPage`, staged `LandingV10AthletePage`, `PublicContentPage` | own-data links remain `/app`; the compact trainer teaser switches to `/for-trainers` while preserving campaign/hash context; trainer entry keeps `trainer_landing_cta_clicked` and now uses the bounded `/app?trainer_intent=1` continuation; capability activation and Coach Today redirect stay owned by #875 |
| Attribution and analytics | existing `captureFirstTouchAttribution`, `productEvents`, Yandex boundary | UTM/first-touch stays allowlisted and immutable; CTA/demo events carry only existing enums and surface; no raw URL, account/health data, private notes or phantom success event is introduced |
| No-JS and index map | backend SEO renderer and sitemap | `/for-athletes` has meaningful root fallback, `/for-trainers` remains the existing canonical trainer page, and only manifest/article canonical URLs enter sitemap |

The chosen header decision from the #857 clarification is the in-page label `Сценарии демо`:
it points to the existing scenario showcase, where each visible scenario link enters the real
isolated demo route. The public copy therefore does not claim a preview anchor is a completed demo.

### C6 verification record

- Added route/metadata regression coverage for direct `/for-athletes`, root canonicalization,
  `noindex, follow`, no-JS fallback, sitemap exclusion and application-host redirect behavior.
- Landing unit coverage now checks alias metadata and shared real-demo URL construction; the
  production landing browser contract uses the explicit `Сценарии демо` label.
- Targeted frontend Vitest, TypeScript, ESLint/Russian UI guard and Prettier passed; targeted
  backend SEO/host tests and Ruff passed. The full repository frontend format baseline remains
  the previously recorded pre-existing failure on 448 files and was not mass-formatted.
- Cross-browser landing coverage passed 27/27 on Chromium, Firefox and WebKit with desktop,
  mobile, light/dark, keyboard and direct-alias cases; the existing mocked TMA smoke suite passed
  33/33. TMA-specific public cutover behavior remains deferred until the final #858 integration.
- Production Landing cutover, authentication, trainer capability activation, external analytics
  delivery, PR merge, deployment and production smoke remain deferred to #875/#858.

```text
PRODUCT_V10_C6=COMPLETE
LANDING_ATHLETE_ROUTE=/
LANDING_ATHLETE_CONTEXT_ALIAS=/for-athletes
LANDING_ATHLETE_ALIAS_INDEXATION=NOINDEX_FOLLOW_CANONICAL_ROOT
LANDING_TRAINER_ROUTE=/for-trainers
LANDING_DEMO_CTA_SEMANTICS=SCENARIO_SHOWCASE_WITH_REAL_LINKS
LANDING_FIRST_TOUCH_ATTRIBUTION=EXISTING_ALLOWLIST_REUSED
LANDING_ANALYTICS=EXISTING_PRIVACY_SAFE_BOUNDARY_REUSED
LANDING_PUBLIC_CUTOVER=NOT_STARTED
PRODUCT_V10_CONVEYOR=READY_FOR_C8
CONTROLLER=ABSENT
GITHUB_FLOW=AUTHORITATIVE
env change required: no
```

## 21. C8 authenticated trainer intent and Coach Today handoff (#875)

C8 adds the bounded post-auth continuation without changing the public Landing cutover. Every
trainer CTA enters the existing auth surface with the exact destination `/app?trainer_intent=1`.
After authentication the application performs a server capability check. An already active
trainer is sent directly to `/coach` (Coach Today); a personal account sees the existing trainer
capability facts, limits and terms confirmation, then the existing idempotent capability API is
called only after an explicit checkbox and button action. The decline path replaces the intent
with `/app?section=today` and never routes through Profile.

| Boundary | Source | Contract |
|---|---|---|
| Bounded auth intent | `frontend/src/shared/auth/trainerIntent.ts`, `frontend/src/shared/auth/oauthRecovery.ts`, `backend/fitminiapp_api/services/auth_redirects.py` | exact trainer destination only; Telegram transport parameters may accompany it; hashes, duplicate intent and arbitrary query values do not activate the flow; external/open redirects remain rejected |
| Public CTA handoff | `frontend/src/pages/public/PublicContentPage.tsx`, `frontend/src/pages/landing/LandingV10CoachPage.tsx` | trainer hero/final CTAs retain `trainer_landing_cta_clicked` and lead to the auth continuation; generic athlete Login and DemoCabinet links are unchanged |
| Authenticated continuation | `frontend/src/main.tsx`, `frontend/src/features/trainer/TrainerIntentFlow.tsx` | capability GET decides active → `/coach` or inactive → existing consent; cancel uses the personal Today route; no URL-driven or silent role activation |
| Consent/API boundary | `frontend/src/features/trainer/TrainerCapabilityConsent.tsx`, `frontend/src/features/profile/TrainerCapabilityCard.tsx`, `/api/v1/me/trainer-capability` | existing Russian terms UI/styles are shared between Profile and post-auth flow; existing lock/idempotency/audit API and `accepted_terms: true` request are reused; no second Coach OS implementation |
| Analytics | existing `productEvents` and AuthProvider login markers | generic login started/completed, trainer landing CTA, application started/completed, activation and workspace events remain truthful; activation success is emitted only when the API returns `activated_now` |
| TMA/history | `isTrainerIntentLocation`, `NavigationProvider`, existing AuthGate | signed Telegram launch can retain allowlisted transport query; explicit consent remains required; cancel/activation replace the intent entry and avoid a stale scroll position |

The terms confirmation is not a new material UI surface: the existing Profile consent markup and
`trainer-capability.css` were extracted once and rendered in both contexts. No owner visual gate
was introduced by C8. The existing Coach Today page and its authorization checks remain the only
authenticated trainer workspace.

```text
PRODUCT_V10_C8=COMPLETE
LANDING_TRAINER_INTENT_DESTINATION=/app?trainer_intent=1
LANDING_TRAINER_CAPABILITY=EXISTING_API_REUSED
LANDING_TRAINER_TERMS_UI=EXISTING_CONSENT_REUSED
LANDING_TRAINER_POST_AUTH=/coach
LANDING_TRAINER_SILENT_ACTIVATION=DISABLED
LANDING_TRAINER_TMA_INTENT=ALLOWLISTED_TRANSPORT_ONLY
LANDING_PUBLIC_CUTOVER=NOT_STARTED
PRODUCT_V10_CONVEYOR=READY_FOR_C7
CONTROLLER=ABSENT
GITHUB_FLOW=AUTHORITATIVE
env change required: no
```

### C8 verification record

- Targeted trainer/profile Vitest and auth redirect unit tests passed: 4 test files, 11 tests;
  existing Profile activation/idempotency tests remain green.
- Frontend typecheck, Vite production build, ESLint/Russian UI guard and changed-file Prettier
  passed. Backend redirect allowlist tests passed (13 selected tests) with Ruff check/format.
- Chromium Playwright auth smoke passed the current `/for-trainers` CTA, explicit consent and
  activation, and a signed Telegram launch with `tgWebAppPlatform` transport query (3/3).
- No production Landing route was switched, no production API/configuration was changed, and no
  deploy, merge or external analytics delivery was performed by the local C8 implementation.
