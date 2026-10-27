# App Experience v3 · target IA

Это зафиксированный Stage 0 target contract для точечного улучшения текущего YFC. Он описывает UI
context, routing и navigation, а не новый auth/data contract или новый visual system.

Текущий production UI/components и работающие сценарии — source of truth. #387 не должен создавать
новый shell ради redesign: implementation начинается с существующих `AppShell`, `CoachPage`,
`TrainerModeSwitch`, router и personal surfaces.

## Неподвижные инварианты

1. Authenticated account остаётся одним identity. `Work` и `Personal` — persistent UI/navigation
   contexts, не две роли, не два аккаунта и не два владельца данных.
2. У trainer-capable аккаунта default authenticated workspace — `Work / Тренер`.
3. Явный переключатель `Work ↔ Personal` виден в trainer shell и сохраняет выбор при обычном
   перемещении/refresh в пределах разрешённого authenticated flow.
4. Переключение меняет только shell, navigation, copy и выбранную surface. Backend authz,
   ownership, client relationships, API identity и server-side validation не меняются.
5. Client-only аккаунт не видит бессмысленный переключатель и не получает trainer navigation.
6. Trainer может открыть собственные тренировки, питание, прогресс и профиль из `Personal`; client
   data остаётся только в `Work` и открывается через существующий server-side capability guard.
7. Trainer workspace и personal workspace могут иметь разные docks; `Для себя` — context switch,
   а не обычный destination внутри trainer dock.

## Целевая карта

```text
Authenticated account
├─ Work · Тренер (только trainer-capable)
│  ├─ Сегодня: существующий CoachToday / operations flow
│  ├─ Клиенты: существующий список → клиент → timeline / workout / progress / program
│  ├─ Программы: существующие assigned programs и builder
│  └─ Ещё: существующие trainer tools, catalog и account actions
└─ Personal · Для себя
   ├─ Сегодня: существующая собственная тренировка и recovery
   ├─ План: существующая программа и расписание
   ├─ Питание: существующий дневник и цели
   ├─ Прогресс: существующие history, measurements, reports
   └─ Профиль: существующие account, security, AI Coach, notifications
```

Для client-only корнем является только `Personal`; его navigation не оставляет пустых trainer
пунктов. Existing public, auth, onboarding, admin и report routes не переписываются в Stage 0.

## Proposed dock contract

Предлагаемый trainer dock — переиспользование уже существующих `CoachPage` tabs и их реальной
частоты/ценности:

| Trainer dock destination | Current production basis                                   | Почему остаётся primary                    |
| ------------------------ | ---------------------------------------------------------- | ------------------------------------------ |
| `Сегодня`                | `CoachOperationsPanel` + `CoachToday`, текущий default tab | ежедневный next action, attention и agenda |
| `Клиенты`                | `CoachPage` client list/detail, summaries и attention      | основная CRM-работа и выбор client context |
| `Программы`              | existing assigned programs и `ProgramBuilder`              | регулярная работа с назначениями и планами |
| `Ещё`                    | current `tools`, catalog и trainer/account actions         | редкие действия не перегружают dock        |

Personal dock возвращает текущий production `AppShell` dock: `Сегодня`, `План`, `Питание`,
`Прогресс`; `Упражнения` и `Профиль` остаются в существующей account/secondary navigation.
Не нужно заставлять один bottom dock обслуживать оба режима.

`Для себя` не является пятым trainer tab. Его естественное место — компактный context control
в существующем trainer header/utility area, рядом с текущим `TrainerModeSwitch` и account context:
на desktop он доступен до содержимого trainer page, на mobile остаётся sticky/видимым в верхней
части trainer surface и не конкурирует с bottom dock. Label должен показывать текущий context
(`Тренер`) и одно очевидное действие (`Для себя`); в personal mode обратное действие — `В кабинет
тренера`. Это предложение для #387, не новая Stage 0 production component.

## Контекстная модель

| Состояние          | Shell label                           | Доступные данные                                              | Что запрещено менять через UI |
| ------------------ | ------------------------------------- | ------------------------------------------------------------- | ----------------------------- |
| Trainer + Work     | `Work · Тренер`                       | собственные рабочие задачи и разрешённые client relationships | identity/authz/ownership      |
| Trainer + Personal | `Personal · Для себя`                 | только собственные personal surfaces                          | client data visibility        |
| Client-only        | `Personal · Для себя` или client copy | только собственные personal surfaces                          | Work switch и trainer routes  |
| Demo trainer       | `Демо · Работа тренера`               | только versioned session fixture                              | production account/API writes |

## Navigation и переходы

Stage 1 должен сохранить существующие URL/deep-link compatibility и реализовать context через
текущий router/allowlisted state. Target flow:

```text
trainer login/auth restore → existing /coach → existing trainer Today
trainer Work → `Для себя` → existing /app?section=today → existing personal dock
personal mode → `В кабинет тренера` → existing /coach → last allowed trainer tab/context
client-only login/auth restore → existing /app → existing personal dock, no switch
current /app?section=... → corresponding existing personal surface
current /demo              → demo-only context without production-data handoff
```

Последний trainer tab и personal section можно сохранять как bounded UI navigation state; это не
auth/authz, не identity и не ownership. Client IDs и private data должны по-прежнему проверяться
server-side. Это mapping для следующего implementation task, не инструкция менять route прямо сейчас.

## Visual/interaction contract для будущей реализации

- production YFC visual language — source of truth: current typography, spacing, cards, controls,
  Liquid Glass, lime/black/white color system, icons, Light/Dark and shell;
- улучшать существующие surfaces точечно по evidence; не делать global redesign или marketing
  composition внутри authenticated work screens;
- trainer workspace не должен выглядеть как отдельное приложение;
- mobile-first, desktop не теряет плотность trainer operations;
- `Для себя` должен быть быстрым, очевидным, mobile-friendly и не занимать место destination;
- keyboard focus, `forced-colors`, safe-area, keyboard overlap и Telegram BackButton сохраняются;
- workout сохраняет текущую block → exercise → set hierarchy до #391;
- catalog/detail/media improvements остаются #389/#395/#390 boundaries;
- новый media, download, AI people imagery и runtime feature flags не входят в IA task;
- старый Stage 0 prototype с hero/cards/новой типографикой/отдельным shell — rejected visual
  exploration и не является design specification.
