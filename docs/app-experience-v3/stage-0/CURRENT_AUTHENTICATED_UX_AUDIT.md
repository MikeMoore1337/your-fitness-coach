# Issue #386 · аудит текущего authenticated UX

Дата среза: 20.09.2026. Источник: текущий `master` после refresh до
`c4cb1681ba8302447307d9012e47666af5ba34ca`, исходный React/API code, существующие demo и
authenticated Playwright fixtures. Production UI, API, DB и media в Stage 0 не изменялись.

## Owner visual/product decision

Текущий production YFC UI — source of truth и visual baseline. App Experience v3 — эволюция
существующего приложения, а не новое приложение и не глобальный authenticated redesign. В будущих
этапах нужно сначала искать точечное улучшение существующего flow/component; новый pattern или
navigation допустим только при доказанном UX-ограничении текущей архитектуры.

Текущий production trainer workspace визуально устраивает владельца. Основная проблема — не
trainer dashboard design, а entry/routing/context switching:

- trainer-capable user сейчас добирается через `Профиль → Кабинет тренера`;
- trainer должен после authentication попадать в существующий `/coach`;
- `Для себя` должно быть быстро доступно из trainer context и возвращать существующий personal
  YFC, а не новый personal shell;
- trainer и personal могут иметь разные docks, потому что это разные рабочие contexts;
- client-only user остаётся в текущем personal YFC без trainer abstraction.

Подготовленный Stage 0 prototype не является design specification. Его крупные hero/cards,
типографика, отдельный shell, dashboard-композиция и визуальные directions — экспериментальная
IA-иллюстрация для истории Stage 0 и считаются rejected visual exploration для #387. Production
переноса этих стилей не предполагается.

## Текущая поверхность

| Контекст                              | Вход                              | Реальное поведение сейчас                                                                        | Результат аудита                                                             |
| ------------------------------------- | --------------------------------- | ------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| Клиентский authenticated              | `/app`                            | fallback — `Сегодня`; `section` выбирает `today/progress/programs/catalog/nutrition/profile`     | Рабочий личный shell; отдельного рабочего переключателя нет                  |
| Trainer-capable, личное использование | `/app?section=today`              | Личные `Сегодня`, `План`, `Питание`, `Прогресс`; `Упражнения` и `Профиль` в account navigation   | Данные тренера не смешиваются, но personal — фактический default             |
| Trainer workspace                     | `/coach`                          | server-backed guard `user.is_coach`; tabs `Сегодня`, `Клиенты`, `Программы`, `Ещё · инструменты` | Визуально accepted production flow; основной gap — вход и context switching  |
| Trainer context switch                | `TrainerModeSwitch`               | `Для себя` → `/app?section=today`, `Клиенты` → `/coach`                                          | Локальный switch внутри coach surface, не persistent global Work/Personal    |
| Demo                                  | `/demo`                           | `demo-curated-v2`, три сценария: тренировка, питание/прогресс, работа тренера                    | Один production-shaped component tree; session-only, без real account writes |
| Report/deep link                      | `/app/report`, query/hash handoff | Authenticated report и focused return через History API                                          | Query/deep-link flow существует; переходы нужно сохранить при IA change      |

## Shell и навигация

`frontend/src/app/AppShell.tsx` сейчас показывает четыре primary destinations: `Сегодня`, `План`,
`Питание`, `Прогресс`. `Упражнения`, `Профиль и настройки` и, при `is_coach`, `Кабинет тренера`
живут в account/secondary navigation. На mobile shell использует bottom navigation и отдельную
панель дополнительных ссылок; breakpoint — `max-width: 899px`. Desktop использует rail и utility
область. Existing theme toggle, PWA prompt, focus return, Escape и Telegram overlay BackButton
остаются частью текущего shell contract.

`frontend/src/shared/navigation/router.tsx` использует History API и `popstate`. Прямые ссылки на
workout feedback, progress detail, report и demo handoff имеют специальные return semantics.
Изменение IA не должно превращать query/deep link в новый identity или ownership signal.

`frontend/src/pages/miniapp/MiniAppPage.tsx` принимает section из URL и при отсутствии запроса
выбирает `today` (исключения — invite/auth recovery ведут в profile). `CoachPage` по умолчанию
выбирает trainer `today`, а `client_id` открывает список/деталь клиента.

## Audit matrix по сценариям

| Сценарий                | Текущий путь                | Что проверено по исходнику/fixture                                                       | Наблюдение для Stage 0                                                         |
| ----------------------- | --------------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Client-only home        | `/app`                      | `MiniAppPage` + `AppShell`                                                               | Личный контекст понятен; Work switch не нужен                                  |
| Trainer-capable default | `/app`                      | `user.is_coach` влияет на account destination, не на fallback section                    | Default остаётся personal-first; это целевой gap, не Stage 0 bug               |
| Trainer Today           | `/coach`                    | `CoachOperationsPanel`, `CoachToday`, attention, agenda, invite                          | Действия и summaries уже production-shaped; нуждаются в единой IA-рамке        |
| Multi-client operations | `/coach?client_id=...`      | `platform-api` fixture: Anna, Boris, Maria и pending Elena; summaries/attention/programs | Representative states готовы для будущего review, второй fake backend не нужен |
| Own data                | `/app?section=today`        | `platform-api` browser session + personal endpoints                                      | Личные тренировки, питание, прогресс остаются отдельными surface               |
| Catalog/search          | `/app?section=catalog`      | `ExerciseCatalog`                                                                        | Сейчас substring search; alias/taxonomy gap зафиксирован в catalog-v2 docs     |
| Exercise detail/media   | catalog card → guide dialog | manifest/API contract и guide components                                                 | Media placement можно проектировать; новый media pipeline не входит в Stage 0  |
| Active workout          | Today → workout             | existing workout fixtures и offline/PWA contract                                         | Иерархия block → exercise → set должна быть сохранена                          |
| Demo                    | `/demo?scenario=trainer`    | `demo-session.ts`, `demo-mode.spec.ts`                                                   | Curated trainer/client states подходят для owner review                        |
| Refresh/back/deep links | History API + query/hash    | `NavigationProvider`, TMA BackButton hooks                                               | Contract должен остаться route/context-only                                    |

## Catalog и media baseline

Актуальный `docs/exercises/catalog-v2/CURRENT_CATALOG_AUDIT.md` фиксирует после 120B–120D:

- 182 stored seed rows и 181 canonical search card;
- 168 `strength` и 14 `cardio`;
- manifest schema v2: 347 media items и 419 локальных файлов/derivatives;
- provenance/alt/SHA-256 для текущего manifest и human-v1 responsive files;
- aliases, machine/path tags и file-level review остаются versioned catalog contract, а не задачей
  по UI-прототипу.

Это audit baseline. Stage 0 не пересчитывает, не переименовывает и не мигрирует каталог, не
создаёт aliases и не добавляет/генерирует/downloads media. Будущие FREE/self-host pipeline и
расширение каталога остаются отдельными boundaries.

## Выводы и границы

1. Current product уже имеет две реальные authenticated surfaces — личную `/app` и trainer `/coach`,
   но не имеет единого persistent Work/Personal context model в navigation shell.
2. `is_coach` — capability/authz signal; он не должен превращаться в новую identity или скрытый
   frontend-only permission boundary. Existing `require_coach` backend guard сохраняется.
3. Demo и existing `platform-api` fixtures покрывают representative client/trainer/own-data states;
   Stage 0 не создаёт второй mock backend.
4. Текущие production typography, spacing, cards, controls, Liquid Glass treatment, color system,
   Light/Dark behavior, icon language и shell — baseline для следующих implementation stages.
5. Stage 0 prototype сохраняется только как isolated IA/click-path artifact; его visual language,
   hero, cards, typography и navigation styling отвергнуты как production direction.

Все design observations ниже — рекомендации/target gaps для следующих этапов, а не unresolved
BLOCKER/HIGH текущего diff.
