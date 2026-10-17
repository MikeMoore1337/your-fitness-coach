# Issue #998 — реализация Variant A

Статус: технически готовый Draft PR, ожидает owner visual acceptance. Merge и deploy не
выполнялись.

## Контракт и границы

- Issue: [#998](https://github.com/MikeMoore1337/your-fitness-coach/issues/998).
- PR: [#1046](https://github.com/MikeMoore1337/your-fitness-coach/pull/1046).
- Ветка: `codex/issue-998-rir-guidance-implementation`.
- Утверждённое направление: Variant A — короткая подсказка рядом с соответствующим понятием.
- Финальный application/evidence SHA: `096a4ededf95558f6996058e56826f50a1bd5f81`.
- Актуальный base при финальной синхронизации: `origin/master`
  `dc1daeb57bc7eded67a089b206e8f84375fea8d1`.
- Последняя синхронизация с этим base: merge `82da4ddec628e8c781b5c4c36ce8e9528da78787`.
- Изоляция: отдельный worktree существующей ветки реализации.

После снятия evidence в master вошёл CI-only commit #1090. Он не меняет application-код,
компоненты Issue #998 или визуальные поверхности; branch sync зафиксирован merge-коммитом
`82da4dde`.

Изменение сохраняет компактный current-set-first интерфейс из #826. В `ActiveSessionSummary`
подробности остаются свёрнутыми до действия пользователя; после раскрытия доступны
детерминированная прогрессия и её объяснение. RIR вынесен рядом с текущим подходом и не
мешает полям веса, повторов и завершения подхода. Алгоритм прогрессии, назначение программ,
backend/API/DB, offline queue, версии и обработка 409 не изменялись.

## Контекст и источники

| Термин     | Экран/компонент                      | Проверенный источник                                   | Реализованное объяснение                                                                                                                         |
| ---------- | ------------------------------------ | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| RIR        | TodayWorkout, текущий подход         | `/knowledge/training/repetitions-in-reserve`           | «Повторы в запасе» — субъективная оценка качественных повторов, которые ещё можно выполнить; поле необязательно, отсутствие оценки не равно нулю |
| Прогрессия | TodayWorkout / ProgressionGuidance   | `/knowledge/training/progressive-overload`             | Действующая детерминированная рекомендация остаётся источником решения; раскрытие показывает факты и ссылку на материал                          |
| Цикл       | ProgramBuilder, 8 тренировочных дней | подтверждённого публичного редакционного материала нет | Короткое описание последовательного восьмидневного цикла; в раскрытии явно показано `Источник: нет ссылки.`                                      |

Новые источники и непроверенные рекомендации не добавлялись.

## Текстовый и интеракционный контракт

- RIR: свёрнутое состояние `Что такое RIR?` находится после полей веса/повторов и кнопки
  завершения; внутри — краткое определение и `Подробнее на сайте`.
- Прогрессия: пользователь раскрывает `Что делать сейчас?`, затем native disclosure
  `Почему такой вес?`; действия применения рекомендации не менялись.
- Цикл: при восьми днях редактор показывает `Как устроен цикл?`; раскрытие не выдумывает
  ссылку и содержит `Источник: нет ссылки.`.
- Клавиатура: `Вес → Повторы → Завершить подход → Что такое RIR?`; Enter/Space раскрывают
  native disclosure, Escape закрывает RIR и возвращает фокус на summary.
- Доступность: сохранены native details/summary, ARIA-атрибуты, touch target от 44 px и
  reduced-motion контракт проекта.

## Evidence

Полный индекс финальных captures находится в [`evidence/README.md`](evidence/README.md).
В нём 48 AFTER-снимков: active workout (40: 320, 360, 393, 430 и 1440 px; Dark/Light;
compact, раскрытый summary, раскрытые подсказки и rest panel) и цикл редактора (8: 393 и
1440 px; Dark/Light; закрытая и открытая подсказка). Исторические BEFORE-снимки сохранены
отдельно и не выдаются за текущий baseline.

Все captures сняты Chromium Playwright на synthetic fixture data. WebKit прошёл тот же
Issue #998 matrix, но screenshots намеренно сняты только Chromium для сопоставимости.
Приватные пользовательские данные не использовались.

Физические iPhone/Safari, реальный Telegram Mini App, VoiceOver и production runtime остаются
`NOT_VERIFIED`.

## Проверки

- Vitest: 154 test files, 915 tests passed.
- Issue #998: Chromium 16/16 и WebKit 16/16.
- #826/V9-05: Chromium+WebKit 10/10.
- Mobile dock/safe-area regression: Chromium 13/13.
- Active workout completion/conflict/offline/rest regression: Chromium 18/18.
- TypeScript typecheck: passed.
- ESLint, русский UI-copy guard и thick-lime-edge guard: passed.
- Production build: passed.
- Prettier для изменённого Issue #998 E2E-файла: passed after formatting.
- Pre-commit для evidence-коммита: passed с проектным `.venv`; первый запуск штатно остановился
  на отсутствующем Windows `python` alias.

Repo-wide `prettier --check .` не запускался; форматирование посторонних исторических файлов
вне этой задачи не выполнялось.

## Следующий owner gate

Показать owner единый batch-пакет Dark/Light, 320/360/393/430/desktop и получить отдельное
подтверждение visual acceptance. После него всё ещё потребуются отдельные разрешения на merge
и production deploy.
