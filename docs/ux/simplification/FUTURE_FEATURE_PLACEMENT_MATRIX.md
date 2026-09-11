# Матрица размещения будущих функций

Статус: IA-контракт локального redesign. Указанная точка входа не означает, что функция уже
реализована или прошла свой trigger/human/evidence gate.

| Контракт                          | Entry point                                                                   | Глубина                     | Почему не выше                                                          | Fallback                                                                                 | Mobile/TMA                                                               |
| --------------------------------- | ----------------------------------------------------------------------------- | --------------------------- | ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `92B` AI capability-aware routing | global `AI Coach` entry; подробные настройки в `Профиль → AI Coach`           | 1 global entry + 2 settings | routing/provider — внутренняя надёжность, не пользовательская навигация | AI unavailable/disabled/retry-safe; продукт работает без AI                              | короткая entry-ссылка, без provider detail; safe retry и BackButton      |
| `93` / `93B` program import       | `План → Управление программой → Импортировать программу`                      | 2 → focused flow            | upload/preview/ambiguities требуют отдельного контекста и подтверждения | сохранить исходный input, показать ошибку/recovery, не создавать программу автоматически | upload/status/summary/resolution по шагам, bounded recovery              |
| `95A` / `95B` reports             | `Прогресс → Отчёты`                                                           | 2                           | PDF/print/share — результат анализа, не ежедневная навигация            | browser print/локальный просмотр; share/Telegram только при approved scope               | keyboard-safe controls, no fake share/Telegram controls                  |
| `96` integrations discovery       | `Профиль → Интеграции`                                                        | 2                           | источник данных и permissions не являются основным фитнес-действием     | ясно показать `не подключено` и ручной ввод                                              | одинаковая IA, platform permission — только при реальной интеграции      |
| `126` equipment scanner           | `План → Редактировать программу → Добавить упражнение → Сканировать тренажёр` | 3 focused capture           | camera context нужен только при выборе упражнения                       | открыть существующий каталог/поиск; не блокировать ручной выбор                          | capture/status/result → каталог; no camera on Today/nav                  |
| `128` nutrition label scanner     | `Питание → Добавить продукт → Сканировать пищевую ценность`                   | 2 → focused capture         | camera/recognition — вариант добавления продукта, не состояние дневника | поиск по названию или ручной ввод; editable review                                       | capture → recognition → editable review → existing amount → explicit add |
| `124B` real-user usability        | после local owner-approved build, отдельный validation gate                   | post-release                | это evidence, а не UI feature                                           | не подменять mock/demo выводами                                                          | Mobile Web/TMA/device evidence разделять                                 |
| `124C` remediation                | только после реального `124B` BLOCKER/HIGH и owner activation                 | follow-up task              | umbrella не запускает remediation сам                                   | зарегистрировать finding и дождаться решения владельца                                   | reproduce на затронутом viewport/platform                                |

## Ручные и вторичные поверхности

- Exercise catalog остаётся secondary resource: workout → exercise → technique, Plan → edit → add
  exercise, Search → exercise.
- `+` в shell открывает contextual quick-add sheet: food, water, cardio, measurement, wellbeing.
  Это shortcut к существующим flows, а не новый storage/API слой.
- `Профиль → Приложение` резервирует PWA/theme/runtime settings; `Аккаунт и безопасность` сохраняет
  текущие account/privacy actions.
- Trainer/Admin links остаются role-specific и не попадают в self-training primary nav.
