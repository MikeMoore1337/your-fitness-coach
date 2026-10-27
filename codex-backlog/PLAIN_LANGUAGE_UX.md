# Plain-language UX - release contract

Default UI is understandable to a person without prior fitness terminology. Advanced terminology remains available through progressive disclosure.

## Compact-first и progressive disclosure

Canonical addendum: `codex-backlog/ux-reset/COMPACT_FIRST_UX_CONTRACT.md`.

- Primary action и текущая операция всегда видимы; пользователь не раскрывает секцию ради
  единственного базового действия.
- Secondary, detail и advanced content по умолчанию compact/collapsible/contextual, если без него
  можно завершить текущую задачу.
- Допустим максимум один уровень disclosure внутри summary card; длинная форма, большой график,
  история или несколько самостоятельных действий переходят на detail screen/sheet.
- Collapsed summary обязан объяснять содержание: короткий title, один ключевой status/metric и не
  более одного действительно нужного quick action.
- Выразительный semantic visual treatment концентрируется на meaningful compact surfaces;
  expanded functional content остаётся спокойным и читаемым.
- Mobile Web/TMA являются первичным ограничением, desktop получает осмысленный reflow, а не широкое
  длинное полотно.
- Expandable control обязан поддерживать semantic button, `aria-expanded`, keyboard/focus, touch,
  screen reader state, stable scroll и `prefers-reduced-motion`.

Compact-first не разрешает удалять полезную функциональность, скрывать validation/error state,
схлопывать секцию во время ввода или строить nested accordion.

## Terminology

| Technical term | Default Russian UI |
|---|---|
| RIR | Повторы в запасе |
| working set | Рабочий подход |
| warm-up set | Разминочный подход |
| drop set | Дроп-сет - объяснить при первом использовании |
| superset | Суперсет - два упражнения подряд |
| failure set | Подход до отказа |
| adherence | Соблюдение плана |
| progression | Увеличение нагрузки |
| deload | Облегчённая неделя |
| training block | Тренировочный блок |
| primary muscle | Основная мышечная группа |
| secondary muscle | Дополнительная мышечная группа |
| data confidence | Достаточно ли данных для вывода |

## RIR control

```text
Повторы в запасе

Сколько повторов вы ещё могли бы сделать
с хорошей техникой?

0   Больше не смог бы
1   Ещё примерно 1 повтор
2   Ещё примерно 2 повтора
3   Ещё примерно 3 повтора
4+  Осталось много сил
```

`RIR` допустим вторично: `Повторы в запасе (RIR)`.

## Beginner workout

Default:

```text
Вес
Повторы
Готово
```

Advanced disclosure:

```text
Дополнительно
  Повторы в запасе
  Тип подхода
  Суперсет
  Заметка
```

## Analytics

Bad:

```text
Training adherence: 83%
RIR coverage insufficient
Primary muscle exposure
```

Good:

```text
Выполнено 10 из 12 тренировок - 83%

Пока мало данных об интенсивности.
Повторы в запасе отмечены только в нескольких подходах.

Рабочие подходы по мышечным группам
```

Use three disclosure levels:

1. short conclusion;
2. concrete factual reason;
3. optional methodology/details.

## Nutrition

Clearly distinguish:

- день заполнен;
- день заполнен частично;
- записей нет;
- пользователь сознательно отметил, что не ел/не отслеживал.

Never describe an unlogged day as `0 ккал`.

## Trainer context

Always show who is being managed:

```text
Клиент: Иван Петров
```

Actions name the target:

```text
Назначить программу Ивану Петрову
Изменить цели КБЖУ Ивана Петрова
```

## TMA

Use short action-oriented text. Long explanations belong to Public Web; TMA uses only concise contextual help and exercise technique.

## Release test

A novice can register, finish onboarding, choose a program, complete a workout, understand a progression hint, log food, add measurements and read Progress without external terminology lookup.

A trainer can directly enable Trainer mode, invite a client, assign a program and review results without interpreting internal role terminology.

## Russian-first fitness terminology

YFC is Russian-first in user-facing product copy.

- Built-in program and template names, split names and generic fitness concepts must be understandable in Russian without English fitness vocabulary.
- Internal enum values, slugs, API fields and source identifiers may remain English.
- Do not expose unexplained `Beginner`, `Intermediate`, `Advanced`, `Full Body`, `Upper/Lower`, `Push/Pull/Legs`, `Hypertrophy` or similar generic English labels in Russian UI.
- Prefer: `для начинающих`, `средний уровень`, `продвинутый уровень`, `всё тело`, `верх/низ`, `рост мышц`, `развитие силы`.
- Established proper program names or abbreviations may remain only when identity matters and the user-facing label explains them in Russian, for example `толкай/тяни/ноги (PPL)` or `PHUL (сила и рост мышц, верх/низ)`.
- User-created names are not rewritten merely because the user chose English. This rule governs built-in/system-authored content and generated defaults.
- New built-in templates and generated default labels require regression coverage against untranslated generic English labels.
