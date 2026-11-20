# Design V2: motion

## Роль motion

Motion объясняет причинно-следственную связь: изменение state, подтверждение действия, обновление
данных и пространственное появление временного слоя. Он не является отдельным декоративным слоем и
не должен замедлять workout, nutrition logging, auth или recovery.

## Утверждённые semantic tokens

Task `74A` закрепила значения после production pilot и owner checkpoint:

| Token                   |                     Значение | Семантика                                                   |
| ----------------------- | ---------------------------: | ----------------------------------------------------------- |
| `--motion-press`        |                      `120ms` | press и compact feedback                                    |
| `--motion-state`        |                      `180ms` | validation, selection, confirmation, expand и small overlay |
| `--motion-spatial`      |                      `260ms` | dialog, drawer, sheet и совместимая geometry update         |
| `--motion-data`         |                      `560ms` | только первое появление meaningful chart geometry           |
| `--motion-data-total`   |                      `760ms` | максимальный бюджет chart sequence                          |
| `--motion-data-stagger` |                       `25ms` | ограниченный stagger внутри одной series                    |
| `--motion-ease`         | `cubic-bezier(0.2, 0, 0, 1)` | спокойная interruptible curve без bounce                    |

Compatibility aliases `--motion-fast`, `--motion-standard` и `--motion-slow` временно остаются для
существующих стилей, но новые правила используют semantic tokens. Page-local durations для той же
причинности запрещены.

## Иерархия и causality

1. **Immediate feedback:** pressed/focus/validation и подтверждение ввода.
2. **State transition:** current set → completed, rest start/end, loading → content, retry → result.
3. **Spatial transition:** dialog, drawer, sheet и временный navigation context.
4. **Data transition:** progress/chart update только там, где движение помогает понять изменение.

Если несколько изменений происходят вместе, current action получает первый perceptual signal;
secondary panels не анимируются одновременно ради эффекта. Interaction и focus доступны сразу и не
ждут окончания decoration. Новое действие прерывает предыдущий transition без queue.

## Shared patterns

- `Button`, `IconButton`, поля, tabs и legacy-compatible actions используют `press/state` tokens.
- Общий `.modal` получает один spatial entrance; focus trap/return выполняется синхронно с semantic
  open/close, а не после анимации.
- `AppShell` More sheet и shared toast сохраняются в DOM на bounded exit, становятся `inert` и
  удаляются после `animationend` или короткого fallback. Быстрый повторный action прерывает exit.
- Disclosure сообщает open state поворотом canonical glyph; body остаётся в document flow.
- Shared skeleton использует bounded shimmer не более трёх циклов, поэтому hidden/offscreen loading
  не создаёт бесконечную декоративную работу. Текстовый loading state остаётся source of truth.
- Error, permission, destructive warning и raw numerical value появляются сразу. Motion не
  задерживает recovery и не заменяет shape, text или ARIA state.

## Data visualization

Канонический trigger реализует `useSemanticMotion` и shared `DataViz`:

- full reload/первая успешная загрузка запускает entrance один раз;
- below-fold chart ждёт первого входа в viewport;
- новый period или новая сигнатура данных получает короткий `update`, а не false zero reset;
- same-data refetch, theme toggle, resize/orientation, selection, TMA foreground resume и повторный
  observer callback не запускают entrance заново;
- background/hidden-document/TMA inactive отменяет незавершённый transition и оставляет final state;
- axes, labels, selected detail, table alternative и ARIA с первого кадра содержат финальные данные;
- `missing` не становится zero, disconnected intervals не соединяются, подтверждённый `0` остаётся
  видимым фактом.

`TimeSeriesChart` раскрывает actual series слева направо. Rise начинается от математического zero
только когда он входит в truthful scale, иначе — от нижней границы plot. `QuantitativeProgress` и
`RankedBars` могут расти от явной baseline; `TaskProgress` и `StepProgress` показывают только
подтверждение состояния. Count-up с временно неверными числами запрещён.

## Product-wide eligibility matrix

`Animate` означает использование shared feedback уже на поверхности или через общий primitive;
`Static` — осознанное отсутствие entrance. Матрица не требует декоративной анимации каждой страницы.

| Поверхность                                            | Решение                    | Обоснование/паттерн                                                                                                         |
| ------------------------------------------------------ | -------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Landing                                                | `Controlled exception`     | Owner-approved hero `73A` сохраняет bounded EnergyFlow/device entrance; controls используют shared tokens, ниже fold static |
| Public training/nutrition/knowledge, guides, exercises | `Animate controls`         | Shared press/focus и disclosure; article text, headings и lists static                                                      |
| Privacy/legal, not-found                               | `Static content`           | Критический текст и recovery доступны сразу; только action feedback                                                         |
| `/login`, verify/reset и Telegram fallback             | `Animate state`            | Initial composition, provider busy/error и email mode; redirect/focus/error без задержки                                    |
| `/join/:token`                                         | `Animate controls`         | Loading/retry/confirmation через shared states; invitation facts static                                                     |
| Today и AppShell/navigation                            | `Animate state/spatial`    | Active selection и Progress context update; permanent rail static; More sheet interruptible                                 |
| Active workout/history                                 | `Animate confirmation`     | Completed set, rest и next action; exercise lists при первом render static                                                  |
| Programs/exercises                                     | `Animate controls/overlay` | Shared buttons, disclosure и modal entrance; builders и dense lists static                                                  |
| Nutrition/search/recipes/copy/barcode                  | `Animate data/state`       | Успешная add/update, daily context, toast и shared modal; loading/error facts immediate                                     |
| Progress/reports/measurements/confidence               | `Animate data`             | Canonical charts и progress; confidence copy/raw values static                                                              |
| Onboarding/profile/account/notifications               | `Animate state`            | Tabs, validation, save/retry, disclosure, toast и confirmation; privacy warnings static                                     |
| Trainer/Coach workspace                                | `Animate controls/state`   | Client/context selection, disclosure, saved feedback; dense tables static                                                   |
| Root Admin                                             | `Animate controls/overlay` | Shared action/modal feedback; data-dense tables и permissions static                                                        |
| Demo cabinet                                           | `Animate context`          | Scenario/revision/reset/handoff; prepared metrics remain factual and immediately readable                                   |
| Mobile Web/mocked TMA                                  | `Same contract`            | Те же triggers/timings; safe area, keyboard, lifecycle и BackButton не создают replay                                       |

WeekStrip анимирует selection/status feedback и disclosure glyph. В согласованных экземплярах
с навигацией по неделям разрешены горизонтальное следование за пользовательским жестом и короткий
прерываемый settle. Свайп переключает не более одной разрешённой недели, не выбирает дату и не
вызывает мутаций; кнопки, прокрутка скрытых дней, ограничения навигации, доступность и reduced motion
сохраняются. Для остальных WeekStrip запрет движения всей недели остаётся. Ограниченное исключение
согласовано владельцем для [#982](https://github.com/MikeMoore1337/your-fitness-coach/issues/982)
по [пакету прототипов](https://github.com/MikeMoore1337/your-fitness-coach/blob/5e26a4724bb8e7cda5f20f92d6d69bca94baeb78/docs/ux-proposals/issue-982/SPEC.md).
Route/page carousel, large-list stagger, incompatible chart morph, platform haptics и admin row motion
не внедрены: для них нет отдельной доказанной пользы в `74A`.

## Mobile Web и Telegram Mini App

- Transition не анимирует safe-area, keyboard inset или viewport height и не использует layout
  measurements на каждом кадре.
- `viewportChanged`, safe-area events, theme change, `activated/deactivated` и document visibility не
  перезапускают data entrance и не повторяют toast/haptic.
- BackButton активен во время `opening/open/closing`; первый Back немедленно возвращает focus
  trigger и начинает bounded exit, повторный Back не создаёт второй transition.
- Orientation/resize сохраняет данные, scroll context и focus. Mobile Web и mocked TMA используют
  один component tree и одинаковые timings.
- Реальный Android/iOS Telegram smoke не заменяется mock-harness и указывается отдельно в evidence.

## Reduced motion и другие accessibility modes

При `prefers-reduced-motion: reduce` chart interpolation, spatial movement, shimmer, parallax и
decorative loops отсутствуют; final geometry появляется сразу. Focus, error, success, loading и
navigation сохраняют text/shape feedback. Smooth scroll не используется.

Keyboard/touch selection работает во время и после animation. Live regions не объявляют каждый
кадр. `forced-colors` сохраняет solid/dashed/marker differences; `200%` zoom и long labels не меняют
semantic order и не вызывают горизонтальный overflow.

Print/PDF/export всегда получают статичное конечное состояние. CSS/JS failure не скрывает
смысловые данные или table alternative.

## Performance contract

- CSS transform/opacity/reveal предпочтительнее layout animation.
- Запрещены per-frame React state, unbounded `requestAnimationFrame`, repeated layout read/write,
  auto-playing decoration и новые animation/chart dependencies без отдельного доказательства.
- Motion не создаёт CLS; bundle и low-end trace сравниваются с baseline.
- После `animationend` или bounded fallback component возвращается в `idle/closed`, поэтому
  background/offscreen состояние не расходует постоянный CPU.

Task `75` отвечает за отдельный performance hardening и не реализуется в рамках `74A`.

## Запрещённая анимация

- bounce/spring у routine controls;
- looping pulse/glow вокруг lime;
- parallax, floating blobs, sparkles и autoplay decoration;
- stagger всего списка при каждом открытии;
- count-up, который временно показывает неверное значение;
- layout shift ради entrance effect;
- анимация, скрывающая или задерживающая error/recovery;
- motion без reduced-motion fallback.
