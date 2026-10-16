# Issue #867 — мобильная геометрия dock

Это локальное synthetic evidence для адресного P1 bugfix от `origin/master`, уже включающего выпущенный #865. Данные вымышленные, дата зафиксирована тестом, пользовательские и production-данные не использовались.

## Классификация расследования

| Наблюдение                                                                        | Классификация         | Основание                                                                                                                                |
| --------------------------------------------------------------------------------- | --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Browser/PWA dock получал лишний нижний отступ на iPhone-подобном `visualViewport` | **CONFIRMED → FIXED** | При `safe-area=34px` и `viewport-bottom=34px` старый расчёт давал gap `80px`; после browser-only нормализации gap `46px`.                |
| Горизонтальный overflow shell/cards на 320/360/390/393/430px                      | **NOT_REPRODUCED**    | Адресная Chromium/WebKit матрица проверила `scrollWidth <= clientWidth`; глобальный `overflow-x: hidden` не добавлялся.                  |
| Пропавший `+`, лишняя/неверная мобильная навигация                                | **ALREADY_FIXED**     | На текущем `master` сохранён утверждённый пятиэлементный dock: 4 маршрута и `Добавить`; Quick Add видим и hit-testable.                  |
| Перекрытие последнего поля/CTA после scroll и работа при клавиатуре               | **NOT_REPRODUCED**    | Существующие active-workout/TMA geometry tests и текущая shell-проверка проходят; отдельные функциональные объёмы #914/#980 не менялись. |
| Будущая композиция 4+1 из Product V14                                             | **V14_DESIGN_ONLY**   | Не реализуется в этом PR и требует отдельного owner design approval.                                                                     |

## Причина и исправление

`visualViewport` в browser surface уже отражает расстояние до физического низа viewport. Общий CSS повторно прибавлял тот же `--yfc-viewport-bottom` к `safe-area`, поэтому dock и связанные clearance/scroll-margin поднимались выше необходимого. Добавлен browser-only effective inset: из raw viewport bottom вычитается уже учтённый layout safe-area, с нижней границей `0px`. Telegram surface сохраняет прежний raw-контракт.

Изменены только общие CSS-расчёты dock/clearance/Quick Add/modal; API, backend, БД, бизнес-логика, маршруты, иконки и композиция навигации не менялись.

## Проверки

- Chromium и WebKit: 20 адресных тестов — Dark/Light × 320/360/390/393/430px.
- Проверены DOM-геометрия dock, `scrollWidth/clientWidth`, CTA `Начать тренировку`, Quick Add visibility и `elementFromPoint` hit-test.
- Existing TMA safe-area contract остаётся raw и покрывается соседними тестами.
- BEFORE/AFTER кадры: 393×844, Chromium/WebKit, Dark/Light. BEFORE — контролируемое воспроизведение старой формулы в том же synthetic runtime; AFTER — текущий CSS.
- Физические iPhone/Safari, native Telegram и VoiceOver в этой среде **NOT_VERIFIED**.

Файлы `*-geometry.json` содержат измеренные значения каждого кадра. Финальный commit SHA и exact-head CI должны быть указаны в PR после публикации ветки.

## Границы

Не затронуты #1001 и #914. #993 остаётся design-only. Merge, deploy и закрытие Issue #867 не выполняются этим изменением.
