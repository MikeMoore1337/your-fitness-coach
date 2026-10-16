# Issue #998 — реализация Variant A

Статус: production-реализация подготовлена, ожидает owner visual acceptance. Merge и deploy не
разрешены.

## Контракт и границы

- Issue: [#998](https://github.com/MikeMoore1337/your-fitness-coach/issues/998).
- Утверждённое направление: Variant A — компактная подсказка рядом с соответствующим понятием.
- Discovery-пакет: `codex/issue-998-rir-guidance-discovery-local` на `24e77a1a9f3e72420a570bb988c5bcaaf6ed7455`.
- Baseline: `origin/master` на `4c92832415d4eb994cf6b849a67074742f07ea50`.
- Изоляция: ветка `codex/issue-998-rir-guidance-implementation` в отдельном worktree.

Изменения не трогают выполнение подхода, расчёт прогрессии, назначение программ, редактор, API,
данные пользователя или скрытый AI Coach. `frontend/src/styles/design-v2.css` не изменён.

## Матрица контекста и источников

| Термин     | Экран/компонент                            | Проверенный источник                                                                                                 | Реализованное объяснение                                                                                                                          | Состояние источника |
| ---------- | ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| RIR        | TodayWorkout, текущий подход               | `knowledge-rir-v1`, `/knowledge/training/repetitions-in-reserve`, опубликовано/проверено `2026-08-22`                | «Повторы в запасе» — субъективная оценка качественных повторов, которые ещё можно выполнить; поле необязательное, отсутствие оценки не равно нулю | ссылка есть         |
| Прогрессия | TodayWorkout / ProgressionGuidance         | `knowledge-progressive-overload-v1`, `/knowledge/training/progressive-overload`, опубликовано/проверено `2026-08-22` | Действующая детерминированная рекомендация остаётся источником решения; раскрытие объясняет факты и даёт ссылку на материал                       | ссылка есть         |
| Цикл       | ProgramBuilder, последовательная программа | подтверждённого публичного редакционного материала нет                                                               | Короткое описание восьмидневного последовательного цикла; в раскрытии явно показано `Источник: нет ссылки.`                                       | нет ссылки          |

Тексты сверены с `frontend/src/content/publicContent.json`, `docs/workout-rir.md` и
`docs/progression-guidance.md`. Нового источника или рекомендации без источника не добавлено.

## Текстовый и интеракционный контракт

- RIR: свернутое состояние `Что такое RIR?`; раскрытие находится после полей веса/повторов и
  кнопки завершения, поэтому не занимает первый экран ввода. Внутри — короткое определение и
  `Подробнее на сайте`.
- Прогрессия: существующее native `<details>` получает точный summary `Почему такой вес?` и
  ссылку `Подробнее о прогрессии`; действия «Применить» и «Оставить текущую нагрузку» не менялись.
- Цикл: существующая строка в редакторе стала свернутой `Как устроен цикл?`; fallback без
  выдуманной ссылки — `Источник: нет ссылки.`.
- Клавиатура: порядок для текущего подхода `Вес → Повторы → Завершить подход → Что такое RIR?`;
  Enter/Space раскрывают native disclosure, Escape закрывает RIR и возвращает фокус на summary.
- Доступность: сохранены native details/summary, `aria-expanded` существующего ContextualHelp,
  44px touch targets и reduced-motion контракт проекта.

## Evidence

Полный пакет из 30 synthetic browser screenshots (BEFORE 10 + AFTER 20) находится в
[`evidence/README.md`](evidence/README.md). AFTER снят Chromium на финальном исходнике, BEFORE —
на baseline `4c92832415d4eb994cf6b849a67074742f07ea50`; ширины: 320, 360, 393, 430 и desktop
1440 CSS px, обе темы. Open-capture содержит раскрытые RIR и progression disclosures.

Evidence использует только synthetic fixture data. Физический iPhone/Safari, реальный Telegram
Mini App и VoiceOver не выдаются за проверенные.

## Проверки

- Vitest: `150` test files, `886` tests passed.
- Targeted Chromium: Issue #998 responsive matrix `10/10`, keyboard/TMA `2/2`, существующие
  TMA progression/contextual-help regression `2/2`.
- Targeted WebKit: Issue #998 responsive matrix `10/10`.
- Typecheck, ESLint и русский UI-copy guard: passed.
- Production build: passed.
- Pre-commit: passed при запуске через проектный `.venv`; первый запуск был заблокирован отсутствующим
  Windows `python` alias, затем тот же hook прошёл с явным `.venv` в PATH.
- Изменённые файлы проходят Prettier. Repo-wide `prettier --check .` выявляет 512 исторически
  неформатированных файлов вне этого изменения и не исправлялся в рамках Issue #998.

## Следующий owner gate

Показать owner полный batch-пакет Dark/Light, 320/360/393/430/desktop и получить отдельное
подтверждение visual acceptance. После него всё ещё потребуется отдельное прямое разрешение на
merge и затем отдельное разрешение на deploy.
